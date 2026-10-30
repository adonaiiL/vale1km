'use strict';
(() => {
  const $ = (selector) => document.querySelector(selector);
  const state = {
    manifest: null,
    signature: '',
    version: Date.now(),
    tab: 'mapa',
    product: 'rf',
    point: 'A',
    timeIndex: 0,
    currentFile: null,
    currentUrl: null,
    loading: false,
    lastChecked: null,
    pick: null,
    showingPoint: false,
    pointWatch: null,
  };

  const PRODUCT_DEFAULTS = [
    ['rf', 'Refletividade'], ['ws', 'Ventos'], ['t2', 'Temperatura'],
    ['rh', 'Umidade'], ['pr', 'Precipitação'], ['td', 'Ponto de orvalho'],
    ['fr', 'Geada'], ['ml', 'MLCAPE'], ['mu', 'MUCAPE'],
    ['sc', 'SCP'], ['vo', 'Vorticidade'], ['sn', 'Neve'],
    ['sh', 'Cisalhamento'], ['hd', 'Hodomapa'],
  ];
  const POINT_DEFAULTS = { A: 'Adonai', F: 'Fabrício', K: 'Kelvin', Ko: 'Komprão' };
  const NO_CLICK = new Set(['sn', 'sh']);
  // Caixa do PNG 2295×1904 enquanto o manifesto ainda não traz "mapa" (rodadas antigas).
  const MAPA_FALLBACK = {
    w: 2295, h: 1904, ax: [20, 196, 1985, 1521.08],
    ext: [-49.560245, -48.689875, -27.131733, -26.536598],
  };
  const POLL_MS = 60_000;
  const PROGRESS_MS = 90_000;

  const esc = (value) => String(value ?? '');
  const repoName = () => $('#repo').value.trim().replace(/^https:\/\/github\.com\//, '').replace(/\/$/, '') || 'adonaiiL/vale1km';
  const fmtDate = (isoHour) => {
    const date = parseHour(isoHour);
    if (!date) return esc(isoHour);
    return new Intl.DateTimeFormat('pt-BR', { timeZone: 'UTC', day: '2-digit', month: '2-digit' }).format(date);
  };
  const parseHour = (value) => {
    if (!value) return null;
    const normalized = /Z$/.test(value) ? value : `${value}:00:00Z`;
    const date = new Date(normalized);
    return Number.isNaN(date.getTime()) ? null : date;
  };
  const utcHour = (value) => {
    const date = parseHour(value);
    return date ? String(date.getUTCHours()).padStart(2, '0') : '--';
  };
  const localLabel = (value) => {
    const date = parseHour(value);
    if (!date) return '--';
    return new Intl.DateTimeFormat('pt-BR', {
      timeZone: 'America/Sao_Paulo', day: '2-digit', month: '2-digit',
      hour: '2-digit', minute: '2-digit', hour12: false,
    }).format(date);
  };
  const isoHour = (date) => date.toISOString().slice(0, 13);
  const fileUrl = (name, version = Date.now()) => {
    const clean = String(name || '').split(/[\\/]/).pop();
    return `resultados/${encodeURIComponent(clean)}?v=${encodeURIComponent(version)}`;
  };
  const setStatus = (text) => { $('#result-status').textContent = text; };
  const showEmpty = (text) => {
    $('#resultado-img').removeAttribute('src');
    $('#stage').hidden = true;
    $('#empty-state').hidden = false;
    $('#empty-state').textContent = text;
    $('#open-image').hidden = true;
    $('#open-image').removeAttribute('href');
    $('#pin').hidden = true;
    state.currentFile = null;
    state.currentUrl = null;
  };
  const currentTime = () => {
    const times = state.manifest?.tempos || [];
    if (!times.length) return null;
    state.timeIndex = Math.max(0, Math.min(state.timeIndex, times.length - 1));
    return times[state.timeIndex];
  };
  const availableProducts = () => {
    const times = state.manifest?.tempos || [];
    const keys = new Set();
    for (const t of times) for (const [k, v] of Object.entries(t.mapas || {})) if (v) keys.add(k);
    const manifestLabels = new Map((state.manifest?.parametros || []).map(p => [p.chave, p.rotulo]));
    return PRODUCT_DEFAULTS.filter(([k]) => keys.has(k)).map(([k, label]) => [k, manifestLabels.get(k) || label || k]);
  };
  const soundingPoints = () => {
    const configured = state.manifest?.pontos || {};
    const keys = new Set();
    for (const t of state.manifest?.tempos || []) for (const [k, v] of Object.entries(t.sondagens || {})) if (v) keys.add(k);
    return [...keys].map(k => [k, configured[k]?.nome || POINT_DEFAULTS[k] || k]);
  };
  const renderChips = (container, items, chosen, dataAttribute, callback) => {
    const element = $(container);
    element.replaceChildren();
    for (const [key, label] of items) {
      const button = document.createElement('button');
      button.type = 'button';
      button.className = `chip${key === chosen ? ' on' : ''}`;
      button.dataset[dataAttribute] = key;
      button.textContent = label;
      element.appendChild(button);
    }
    element.onclick = (event) => {
      const button = event.target.closest('button');
      if (!button || !button.dataset[dataAttribute]) return;
      callback(button.dataset[dataAttribute]);
    };
  };
  const countProducts = (manifest) => (manifest.tempos || []).reduce((sum, t) =>
    sum + Object.values(t.mapas || {}).filter(Boolean).length + Object.values(t.sondagens || {}).filter(Boolean).length, 0);
  const mapaGeom = () => {
    const g = state.manifest?.geom;
    if (g && g.lon0 != null && g.lon1 != null) {
      return { w: g.W, h: g.H, ax: [g.x0, g.y0, g.w, g.h], ext: [g.lon0, g.lon1, g.lat0, g.lat1] };
    }
    if (state.manifest?.mapa?.ext) return state.manifest.mapa;
    return MAPA_FALLBACK;
  };
  const clickable = () => state.tab === 'mapa' && !state.showingPoint && !NO_CLICK.has(state.product);

  function placePin() {
    const pin = $('#pin');
    const mapa = mapaGeom();
    if (!state.pick || !clickable()) { pin.hidden = true; return; }
    const [lon0, lon1, lat0, lat1] = mapa.ext;
    const [ax, ay, aw, ah] = mapa.ax;
    const fx = (state.pick.lon - lon0) / (lon1 - lon0);
    const fy = (lat1 - state.pick.lat) / (lat1 - lat0);
    if (fx < 0 || fx > 1 || fy < 0 || fy > 1) { pin.hidden = true; return; }
    pin.hidden = false;
    pin.style.left = `${((ax + fx * aw) / mapa.w) * 100}%`;
    pin.style.top = `${((ay + fy * ah) / mapa.h) * 100}%`;
  }

  function render() {
    const manifest = state.manifest;
    if (!manifest || !Array.isArray(manifest.tempos) || !manifest.tempos.length) {
      showEmpty('O manifesto foi lido, mas ainda não há horários de previsão para exibir.');
      $('#tb').replaceChildren();
      return;
    }
    const products = availableProducts();
    if (state.tab === 'mapa' && products.length && !products.some(([key]) => key === state.product)) state.product = products[0][0];
    const points = soundingPoints();
    if (state.tab === 'sondagem' && points.length && !points.some(([key]) => key === state.point)) state.point = points[0][0];

    $('#tabs').querySelectorAll('button[data-tab]').forEach(btn => btn.classList.toggle('on', btn.dataset.tab === state.tab));
    $('#pm').hidden = state.tab !== 'mapa';
    $('#pts').hidden = state.tab !== 'sondagem';
    $('#download-sounding').hidden = state.tab !== 'sondagem' && !state.showingPoint;
    $('#download-all-soundings').hidden = state.tab !== 'sondagem';
    $('#download-current').hidden = state.tab === 'sondagem' || state.showingPoint;
    $('#voltar-mapa').hidden = !state.showingPoint;
    $('#ponto-box').hidden = state.tab !== 'mapa';
    $('#product-heading').textContent = state.showingPoint
      ? 'Sondagem do ponto marcado'
      : (state.tab === 'mapa' ? 'Mapa meteorológico' : `Sondagem: ${points.find(p => p[0] === state.point)?.[1] || state.point}`);

    renderChips('#pm', products, state.product, 'product', (key) => { state.product = key; state.showingPoint = false; render(); });
    renderChips('#pts', points, state.point, 'point', (key) => { state.point = key; state.showingPoint = false; render(); });

    const timeButtons = $('#tb');
    timeButtons.replaceChildren();
    let lastDay = '';
    manifest.tempos.forEach((entry, index) => {
      const day = fmtDate(entry.utc);
      if (day !== lastDay) {
        lastDay = day;
        const label = document.createElement('span');
        label.className = 'dia';
        label.textContent = day;
        timeButtons.appendChild(label);
      }
      const button = document.createElement('button');
      button.type = 'button';
      button.dataset.index = String(index);
      button.className = index === state.timeIndex ? 'chip on' : 'chip';
      const b = document.createElement('b');
      b.textContent = `${utcHour(entry.utc)}Z`;
      const small = document.createElement('small');
      small.textContent = localLabel(entry.utc).split(' ').slice(-1)[0] || '';
      button.append(b, small);
      timeButtons.appendChild(button);
    });
    const activeChip = timeButtons.querySelector('button.chip.on');
    if (activeChip) activeChip.scrollIntoView({ inline: 'center', block: 'nearest' });

    const entry = currentTime();
    const atual = $('#hora-atual');
    atual.replaceChildren();
    const titulo = document.createElement('b');
    titulo.textContent = entry ? `${fmtDate(entry.utc)} ${utcHour(entry.utc)}Z` : '—';
    const sub = document.createElement('small');
    sub.textContent = entry ? `${localLabel(entry.utc)} Brasília` : 'horário válido';
    atual.append(titulo, sub);

    if (state.showingPoint && state.pick?.url) {
      const image = $('#resultado-img');
      $('#stage').hidden = false;
      $('#empty-state').hidden = true;
      image.hidden = false;
      image.style.cursor = 'default';
      image.alt = `Sondagem em ${state.pick.lat.toFixed(3)}, ${state.pick.lon.toFixed(3)}`;
      image.onerror = () => showEmpty('A sondagem foi gerada, mas a imagem ainda não abriu. Tente de novo em alguns segundos.');
      image.src = state.pick.url;
      $('#pin').hidden = true;
      state.currentFile = null;
      state.currentUrl = state.pick.url;
      $('#open-image').hidden = false;
      $('#open-image').href = state.pick.url;
      $('#figure-caption').textContent = `Sondagem avulsa · ${state.pick.lat.toFixed(4)}, ${state.pick.lon.toFixed(4)} · ${entry?.utc || ''} UTC`;
      $('#ponto-coord').textContent = `${state.pick.lat.toFixed(4)} , ${state.pick.lon.toFixed(4)}`;
      return;
    }

    const file = state.tab === 'mapa' ? entry?.mapas?.[state.product] : entry?.sondagens?.[state.point];
    if (!file) {
      const selected = state.tab === 'mapa' ? products.find(p => p[0] === state.product)?.[1] || state.product : points.find(p => p[0] === state.point)?.[1] || state.point;
      showEmpty(`O produto “${selected}” não foi gerado para ${entry?.utc || 'este horário'}. Escolha outro horário ou variável.`);
      $('#figure-caption').textContent = `Horário válido: ${entry?.utc || 'indisponível'} UTC.`;
      return;
    }
    const url = fileUrl(file, `${state.version}-${entry.utc}-${state.tab}-${state.product}-${state.point}`);
    const image = $('#resultado-img');
    $('#stage').hidden = false;
    $('#empty-state').hidden = true;
    image.hidden = false;
    image.style.cursor = clickable() ? 'crosshair' : 'default';
    image.alt = state.tab === 'mapa' ? `Mapa ${state.product}, válido ${entry.utc} UTC` : `Sondagem ${state.point}, válida ${entry.utc} UTC`;
    image.onerror = () => showEmpty(`Não foi possível carregar “${file}”. A publicação pode ainda estar sendo atualizada; clique em “Verificar agora” em alguns instantes.`);
    image.src = url;
    state.currentFile = file;
    state.currentUrl = url;
    $('#open-image').hidden = false;
    $('#open-image').href = url;
    $('#figure-caption').textContent = `Válido: ${entry.utc} UTC · ${entry.brt ? `${entry.brt.replace('T', ' ')} Brasília` : `${localLabel(entry.utc)} Brasília`} · ${file}`;
    const hint = NO_CLICK.has(state.product)
      ? 'Este mosaico não aceita clique. Abra refletividade, temperatura ou outro mapa simples para marcar o ponto.'
      : 'Toque dentro do mapa para marcar o ponto. A sondagem usa a última rodada e leva alguns minutos.';
    $('#ponto-hint').textContent = hint;
    if (state.pick) {
      $('#ponto-coord').textContent = `${state.pick.lat.toFixed(4)} , ${state.pick.lon.toFixed(4)}`;
      $('#ponto-lat').value = state.pick.lat.toFixed(4);
      $('#ponto-lon').value = state.pick.lon.toFixed(4);
    }
    placePin();
  }

  async function loadManifest({ quiet = false } = {}) {
    if (state.loading) return;
    state.loading = true;
    if (!quiet && !state.manifest) setStatus('Carregando resultados publicados…');
    try {
      const response = await fetch(`resultados/manifest.json?_=${Date.now()}`, { cache: 'no-store', credentials: 'same-origin' });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const manifest = await response.json();
      if (!manifest || !Array.isArray(manifest.tempos)) throw new Error('Formato do manifesto inesperado');
      const signature = JSON.stringify({ init: manifest.init, tempos: manifest.tempos, falhas: manifest.falhas, mapa: manifest.mapa });
      const changed = signature !== state.signature;
      if (changed) {
        const oldUtc = currentTime()?.utc;
        state.manifest = manifest;
        state.signature = signature;
        state.version = Date.now();
        const preservedIndex = oldUtc ? manifest.tempos.findIndex(t => t.utc === oldUtc) : -1;
        state.timeIndex = preservedIndex >= 0 ? preservedIndex : Math.max(0, manifest.tempos.length - 1);
        render();
      } else if (!state.manifest) {
        state.manifest = manifest;
        render();
      }
      state.lastChecked = new Date();
      const latest = manifest.tempos.at(-1)?.utc || 'horário não informado';
      setStatus(`Dados atualizados ${state.lastChecked.toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' })}`);
      $('#result-meta').textContent = `Inicialização ICON: ${manifest.init || 'não informada'} UTC · ${manifest.tempos.length} horários · ${countProducts(manifest)} produtos · Último: ${latest} UTC${changed ? ' · novos dados' : ''}`;
      $('#auto-status').textContent = changed ? 'Nova publicação detectada' : 'Consulta automática a cada 60 s';
    } catch (error) {
      console.error('Falha lendo resultados Vale1Km:', error);
      if (!state.manifest) showEmpty('Não foi possível encontrar resultados publicados. Confira se a pasta resultados/ contém manifest.json.');
      setStatus(`Não foi possível atualizar (${error.message}).`);
      $('#auto-status').textContent = 'Nova tentativa automática em 60 s';
    } finally {
      state.loading = false;
    }
  }

  function showProgress(data) {
    const box = $('#run-progress');
    if (!data || typeof data.pct !== 'number') { box.hidden = true; return; }
    box.hidden = false;
    box.classList.toggle('ok', data.status === 'concluido');
    box.classList.toggle('bad', data.status === 'erro');
    const pct = Math.max(0, Math.min(100, data.pct));
    $('#run-progress-fill').style.width = `${pct}%`;
    $('#run-progress-track').setAttribute('aria-valuenow', String(pct));
    $('#run-progress-pct').textContent = `${pct}%`;
    const label = data.status === 'erro' ? 'Rodada falhou' : data.status === 'concluido' ? 'Rodada concluída' : 'Rodada no GitHub';
    $('#run-progress-label').textContent = label;
    const quando = data.atualizado ? ` · ${data.atualizado.replace('T', ' ').replace('Z', ' UTC')}` : '';
    $('#run-progress-msg').textContent = `${data.msg || 'Sem mensagem'}${quando}`;
  }

  async function loadProgress() {
    const repo = repoName();
    if (!/^[^/\s]+\/[^/\s]+$/.test(repo)) return;
    const headers = { Accept: 'application/vnd.github+json', 'X-GitHub-Api-Version': '2022-11-28' };
    const token = $('#token').value.trim();
    if (token) headers.Authorization = `Bearer ${token}`;
    try {
      const response = await fetch(`https://api.github.com/repos/${repo}/releases/tags/vale1km`, { headers, cache: 'no-store' });
      if (response.status === 404) { $('#run-progress').hidden = true; return; }
      if (!response.ok) return;
      const release = await response.json();
      const data = JSON.parse(release.body || '');
      if (data && typeof data === 'object') showProgress(data);
    } catch {
      /* release ainda sem JSON ou limite da API: mantém o último estado */
    }
  }

  const downloadFile = (file) => {
    if (!file) return;
    const link = document.createElement('a');
    link.href = fileUrl(file, `${state.version}-${Date.now()}`);
    link.download = String(file).split(/[\\/]/).pop();
    link.rel = 'noopener';
    document.body.appendChild(link);
    link.click();
    link.remove();
  };
  const activeEntry = () => currentTime();
  $('#download-current').addEventListener('click', () => {
    const entry = activeEntry(); downloadFile(entry?.mapas?.[state.product]);
  });
  $('#download-sounding').addEventListener('click', () => {
    if (state.showingPoint && state.pick?.url) {
      const link = document.createElement('a');
      link.href = state.pick.url; link.target = '_blank'; link.rel = 'noopener';
      document.body.appendChild(link); link.click(); link.remove();
      return;
    }
    const entry = activeEntry(); downloadFile(entry?.sondagens?.[state.point]);
  });
  $('#download-all-soundings').addEventListener('click', () => {
    const entry = activeEntry();
    const files = Object.values(entry?.sondagens || {}).filter(Boolean);
    files.forEach((file, index) => window.setTimeout(() => downloadFile(file), index * 350));
  });
  $('#check-refresh').addEventListener('click', () => { loadManifest(); loadProgress(); });
  $('#tabs').addEventListener('click', (event) => {
    const button = event.target.closest('button[data-tab]');
    if (!button) return;
    state.tab = button.dataset.tab;
    state.showingPoint = false;
    render();
  });
  $('#tb').addEventListener('click', (event) => {
    const button = event.target.closest('button[data-index]');
    if (!button) return;
    state.timeIndex = Number(button.dataset.index);
    state.showingPoint = false;
    render();
  });
  const shiftTime = (delta) => {
    const times = state.manifest?.tempos || [];
    if (!times.length) return;
    state.timeIndex = Math.max(0, Math.min(times.length - 1, state.timeIndex + delta));
    state.showingPoint = false;
    render();
  };
  $('#hora-prev').addEventListener('click', () => shiftTime(-1));
  $('#hora-next').addEventListener('click', () => shiftTime(1));
  $('#voltar-mapa').addEventListener('click', () => { state.showingPoint = false; render(); });

  $('#resultado-img').addEventListener('click', (event) => {
    if (!clickable()) return;
    const mapa = mapaGeom();
    const rect = event.currentTarget.getBoundingClientRect();
    if (!rect.width || !rect.height) return;
    const px = ((event.clientX - rect.left) / rect.width) * mapa.w;
    const py = ((event.clientY - rect.top) / rect.height) * mapa.h;
    const [ax, ay, aw, ah] = mapa.ax;
    if (px < ax || px > ax + aw || py < ay || py > ay + ah) {
      $('#ponto-coord').textContent = 'Toque dentro da área do mapa';
      return;
    }
    const [lon0, lon1, lat0, lat1] = mapa.ext;
    const lon = lon0 + ((px - ax) / aw) * (lon1 - lon0);
    const lat = lat1 - ((py - ay) / ah) * (lat1 - lat0);
    state.pick = { lat, lon, url: null };
    state.showingPoint = false;
    $('#ponto-coord').textContent = `${lat.toFixed(4)} , ${lon.toFixed(4)}`;
    $('#ponto-lat').value = lat.toFixed(4);
    $('#ponto-lon').value = lon.toFixed(4);
    placePin();
  });

  function populateHours() {
    const hours = Array.from({ length: 24 }, (_, h) => String(h).padStart(2, '0'));
    const select = $('#start-hour');
    select.replaceChildren(...hours.map(hour => {
      const option = document.createElement('option'); option.value = hour; option.textContent = `${hour}Z`; return option;
    }));
    select.value = '15';
  }
  const dateValue = (date) => `${date.getUTCFullYear()}-${String(date.getUTCMonth() + 1).padStart(2, '0')}-${String(date.getUTCDate()).padStart(2, '0')}`;
  function durationHours() {
    if ($('#duracao').value === 'custom') {
      const n = Number($('#duracao-custom').value);
      if (!Number.isFinite(n)) throw new Error('Informe a duração em horas.');
      return n;
    }
    return Number($('#duracao').value);
  }
  function selectedWindow() {
    const date = $('#valid-date').value;
    if (!date) throw new Error('Informe o início da janela válida.');
    const [year, month, day] = date.split('-').map(Number);
    const startHour = Number($('#start-hour').value);
    const step = Number($('#step-hour').value);
    const hours = durationHours();
    if (hours < 3 || hours > 120) throw new Error('A duração precisa ficar entre 3 e 120 horas.');
    const start = Date.UTC(year, month - 1, day, startHour);
    const end = start + hours * 3600000;
    const initDate = $('#run-date').value;
    if (!initDate) throw new Error('Informe a inicialização do ICON.');
    const [iy, im, id] = initDate.split('-').map(Number);
    const init = Date.UTC(iy, im - 1, id, Number($('#run-hour').value));
    if (start < init) throw new Error('A janela começa antes da inicialização do ICON.');
    const lead = (end - init) / 3600000;
    const limite = Number($('#run-hour').value) % 12 === 0 ? 180 : 120;
    if (lead > limite) throw new Error(`Essa janela termina em +${lead.toFixed(0)} h, e o ICON das ${$('#run-hour').value}Z só vai até +${limite} h.`);
    if (step <= 0 || hours / step > 120) throw new Error('São horários demais para plotar. Aumente o intervalo dos mapas.');
    return { start: isoHour(new Date(start)), end: isoHour(new Date(end)), step, hours };
  }
  function refreshWindowSummary() {
    const el = $('#janela-resumo');
    try {
      const window = selectedWindow();
      const maps = Math.floor(window.hours / window.step) + 1;
      const aviso = window.hours >= 36 ? ' O GitHub pode encerrar a rodada ao completar 6 h de execução.' : '';
      el.textContent = `De ${window.start.replace('T', ' ')}Z até ${window.end.replace('T', ' ')}Z (${window.hours} h, ${maps} mapas).${aviso}`;
    } catch (error) {
      el.textContent = error.message;
    }
  }
  async function dispatchRun(mode, extraInputs = {}) {
    const output = mode === 'sondagem' ? $('#sondagem-status') : $('#run-output');
    output.hidden = false;
    const repo = repoName();
    const token = $('#token').value.trim();
    const date = $('#run-date').value;
    const hour = $('#run-hour').value;
    if (!/^[^/\s]+\/[^/\s]+$/.test(repo)) { output.textContent = 'Informe o repositório no formato usuario/repositorio.'; return false; }
    if (!token) { output.textContent = 'Cole o token do GitHub na caixa Nova rodada. Ele não é guardado pela página.'; return false; }
    if (!date && mode !== 'sondagem') { output.textContent = 'Informe a data de inicialização do ICON.'; return false; }
    let window;
    try { window = selectedWindow(); }
    catch (error) {
      if (mode === 'sondagem' && state.manifest?.init) {
        const tempos = state.manifest.tempos || [];
        window = { start: tempos[0]?.utc || state.manifest.init, end: tempos.at(-1)?.utc || state.manifest.init, step: 1 };
      } else { output.textContent = error.message; return false; }
    }
    const init = state.manifest?.init && mode === 'sondagem' ? state.manifest.init : `${date}T${hour}`;
    const payload = { ref: 'main', inputs: {
      modo: mode, dominio: 'vale1km', init,
      janela_ini: window.start, janela_fim: window.end, passo_h: String(window.step),
      ...extraInputs,
    } };
    output.textContent = 'Enviando a solicitação ao GitHub Actions…';
    try {
      const response = await fetch(`https://api.github.com/repos/${repo}/actions/workflows/vale1km.yml/dispatches`, {
        method: 'POST',
        headers: { Authorization: `Bearer ${token}`, Accept: 'application/vnd.github+json', 'X-GitHub-Api-Version': '2022-11-28', 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
      if (response.status === 204) {
        if (mode !== 'sondagem') {
          output.textContent = `Rodada enviada (${window.hours || ''} h). A barra no topo acompanha o andamento; os mapas entram aqui quando a publicação terminar.`;
          loadProgress();
        }
        return true;
      }
      const detail = await response.text();
      output.textContent = `O GitHub respondeu HTTP ${response.status}. Confira o token (permissão actions) e se vale1km.yml está na branch main.\n${detail.slice(0, 700)}`;
      return false;
    } catch (error) {
      output.textContent = `Não foi possível enviar a solicitação: ${error.message}.`;
      return false;
    }
  }

  async function pollPointSounding(pedido) {
    const repo = repoName();
    const token = $('#token').value.trim();
    const headers = { Accept: 'application/vnd.github+json', 'X-GitHub-Api-Version': '2022-11-28', Authorization: `Bearer ${token}` };
    const box = $('#sondagem-status');
    const tick = async () => {
      if (state.pointWatch !== pedido.id) return;
      try {
        const response = await fetch(`https://api.github.com/repos/${repo}/releases/tags/vale1km`, { headers, cache: 'no-store' });
        if (!response.ok) {
          box.textContent = 'Pedido enviado. Esperando o GitHub publicar a sondagem…';
        } else {
          const release = await response.json();
          const asset = (release.assets || []).find(item => item.name === `${pedido.nome}.png`);
          if (asset) {
            const url = `${asset.browser_download_url}?t=${encodeURIComponent(asset.updated_at || Date.now())}`;
            state.pick = { lat: pedido.lat, lon: pedido.lon, url };
            state.showingPoint = true;
            state.pointWatch = null;
            box.textContent = 'Sondagem pronta.';
            render();
            return;
          }
          box.textContent = 'Gerando a sondagem no GitHub. Isso leva alguns minutos; a imagem entra aqui sozinha.';
        }
      } catch (error) {
        box.textContent = `Ainda não deu para ler a sondagem (${error.message}).`;
      }
      window.setTimeout(tick, 15000);
    };
    window.setTimeout(tick, 8000);
  }

  $('#gerar-sondagem').addEventListener('click', async () => {
    const latN = Number($('#ponto-lat').value);
    const lonN = Number($('#ponto-lon').value);
    if (Number.isFinite(latN) && Number.isFinite(lonN)) state.pick = { ...(state.pick || {}), lat: latN, lon: lonN, url: null };
    if (!state.pick || !Number.isFinite(state.pick.lat) || !Number.isFinite(state.pick.lon)) {
      $('#sondagem-status').hidden = false;
      $('#sondagem-status').textContent = 'Toque no mapa ou digite a latitude e a longitude.';
      return;
    }
    const entry = currentTime();
    if (!entry?.utc) { $('#sondagem-status').hidden = false; $('#sondagem-status').textContent = 'Não há horário válido selecionado.'; return; }
    const box = $('#sondagem-status');
    box.hidden = false;
    const repo = repoName();
    const token = $('#token').value.trim();
    if (!token) { box.textContent = 'Cole o token do GitHub na caixa Nova rodada. Ele fica só nesta aba.'; return; }
    const tempo = entry.utc.replace(/\D/g, '').slice(0, 10);
    const lat = state.pick.lat.toFixed(4);
    const lon = state.pick.lon.toFixed(4);
    const nome = `sond_${tempo}_${lat}_${lon}`;
    box.textContent = 'Enviando o pedido de sondagem…';
    try {
      const response = await fetch(`https://api.github.com/repos/${repo}/actions/workflows/sondagem.yml/dispatches`, {
        method: 'POST',
        headers: { Authorization: `Bearer ${token}`, Accept: 'application/vnd.github+json', 'X-GitHub-Api-Version': '2022-11-28', 'Content-Type': 'application/json' },
        body: JSON.stringify({ ref: 'main', inputs: { lat, lon, tempo, init: state.manifest?.init || '', nome } }),
      });
      if (response.status !== 204) {
        const detail = await response.text();
        box.textContent = `O GitHub respondeu HTTP ${response.status}. Confira o token e se sondagem.yml está na branch main.\n${detail.slice(0, 400)}`;
        return;
      }
    } catch (error) {
      box.textContent = `Não foi possível enviar a sondagem: ${error.message}.`;
      return;
    }
    const pedido = { id: Date.now(), lat: Number(lat), lon: Number(lon), tempo, nome };
    state.pointWatch = pedido.id;
    box.textContent = `Pedido enviado para ${lat}, ${lon} em ${entry.utc}Z. A imagem aparece aqui quando o GitHub terminar.`;
    pollPointSounding(pedido);
  });

  $('#download-icon').addEventListener('click', () => dispatchRun('baixar'));
  $('#run-wrf').addEventListener('click', () => dispatchRun('baixar_e_rodar'));
  $('#duracao').addEventListener('change', () => {
    $('#duracao-custom').hidden = $('#duracao').value !== 'custom';
    refreshWindowSummary();
  });
  for (const id of ['run-date', 'run-hour', 'valid-date', 'start-hour', 'duracao-custom', 'step-hour']) {
    $(`#${id}`).addEventListener('input', refreshWindowSummary);
    $(`#${id}`).addEventListener('change', refreshWindowSummary);
  }

  populateHours();
  const remember = (key, value) => {
    try { return value === undefined ? sessionStorage.getItem(key) : sessionStorage.setItem(key, value); }
    catch { return null; }
  };
  const fromHost = location.hostname.endsWith('github.io')
    ? `${location.hostname.split('.')[0]}/${(location.pathname.split('/').filter(Boolean)[0] || '')}` : '';
  $('#repo').value = remember('rp') || (/^[^/\s]+\/[^/\s]+$/.test(fromHost) ? fromHost : 'adonaiiL/vale1km');
  $('#token').value = remember('tk') || '';
  $('#repo').addEventListener('change', () => remember('rp', $('#repo').value.trim()));
  $('#token').addEventListener('change', () => remember('tk', $('#token').value.trim()));
  const applyTheme = (theme) => {
    document.documentElement.dataset.theme = theme;
    $('#theme').textContent = theme === 'light' ? 'Tema escuro' : 'Tema claro';
    remember('theme', theme);
  };
  $('#theme').addEventListener('click', () => applyTheme(document.documentElement.dataset.theme === 'light' ? 'dark' : 'light'));
  applyTheme(remember('theme') || 'dark');
  const today = new Date();
  $('#run-date').value = dateValue(today);
  const valid = new Date(Date.UTC(today.getUTCFullYear(), today.getUTCMonth(), today.getUTCDate() + 1));
  $('#valid-date').value = dateValue(valid);
  refreshWindowSummary();
  loadManifest();
  const scheduleProgress = async () => {
    if (document.visibilityState === 'visible') await loadProgress();
    const wait = $('#token').value.trim() ? 20000 : PROGRESS_MS;
    window.setTimeout(scheduleProgress, wait);
  };
  scheduleProgress();
  window.setInterval(() => { if (document.visibilityState === 'visible') loadManifest({ quiet: true }); }, POLL_MS);
  document.addEventListener('visibilitychange', () => {
    if (document.visibilityState === 'visible') loadManifest({ quiet: true });
  });
})();
