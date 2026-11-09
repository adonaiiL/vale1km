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
  const GROUPS = [
    ['Tempo severo', ['rf', 'ml', 'mu', 'sc', 'sh', 'hd']],
    ['Superfície', ['t2', 'td', 'rh', 'ws', 'fr']],
    ['Precipitação', ['pr', 'sn']],
    ['Outros', ['vo']],
  ];
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
    $('#shot').hidden = true;
    $('#empty-state').hidden = false;
    $('#empty-state').textContent = text;
    $('#open-image').hidden = true;
    $('#open-image').removeAttribute('href');
    $('#pin').hidden = true;
    $('#fig').classList.remove('sond');
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
      renderParams([], []);
      fillGifSelects();
      requestAnimationFrame(fitFigure);
      return;
    }
    const products = availableProducts();
    if (state.tab === 'mapa' && products.length && !products.some(([key]) => key === state.product)) state.product = products[0][0];
    const points = soundingPoints();
    if (state.tab === 'sondagem' && points.length && !points.some(([key]) => key === state.point)) state.point = points[0][0];

    $('#tabs').querySelectorAll('button[data-tab]').forEach(btn => btn.classList.toggle('on', btn.dataset.tab === state.tab));
    $('#download-sounding').hidden = state.tab !== 'sondagem' && !state.showingPoint;
    $('#download-all-soundings').hidden = state.tab !== 'sondagem';
    $('#download-current').hidden = state.tab === 'sondagem' || state.showingPoint;
    $('#voltar-mapa').hidden = !state.showingPoint;
    $('#download-current').textContent = state.tab === 'sondagem' ? 'Baixar sondagem' : 'Baixar imagem';
    $('#ponto-box').hidden = state.tab !== 'mapa';
    fillGifSelects();
    $('#fig').classList.toggle('sond', !!state.showingPoint);
    $('#product-heading').textContent = state.showingPoint
      ? 'Sondagem do ponto'
      : (state.tab === 'mapa' ? 'Mapa' : `Sondagem: ${points.find(p => p[0] === state.point)?.[1] || state.point}`);
    renderParams(products, points);

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
      $('#shot').hidden = false;
      $('#empty-state').hidden = true;
      image.hidden = false;
      image.style.cursor = 'default';
      image.alt = `Sondagem em ${state.pick.lat.toFixed(3)}, ${state.pick.lon.toFixed(3)}`;
      image.onerror = () => showEmpty('A imagem da sondagem não abriu. Gere de novo; o arquivo precisa estar na branch sondagens.');
      image.src = state.pick.url;
      $('#pin').hidden = true;
      state.currentFile = null;
      state.currentUrl = state.pick.url;
      $('#open-image').hidden = false;
      $('#open-image').href = state.pick.url;
      $('#figure-caption').textContent = `Sondagem avulsa · ${state.pick.lat.toFixed(4)}, ${state.pick.lon.toFixed(4)} · ${entry?.utc || ''} UTC`;
      $('#ponto-coord').textContent = `${state.pick.lat.toFixed(4)} , ${state.pick.lon.toFixed(4)}`;
      requestAnimationFrame(fitFigure);
      return;
    }

    const file = state.tab === 'mapa' ? entry?.mapas?.[state.product] : entry?.sondagens?.[state.point];
    if (!file) {
      const selected = state.tab === 'mapa' ? products.find(p => p[0] === state.product)?.[1] || state.product : points.find(p => p[0] === state.point)?.[1] || state.point;
      showEmpty(`O produto “${selected}” não foi gerado para ${entry?.utc || 'este horário'}. Escolha outro horário ou variável.`);
      $('#figure-caption').textContent = `Horário válido: ${entry?.utc || 'indisponível'} UTC.`;
      requestAnimationFrame(fitFigure);
      return;
    }
    const url = fileUrl(file, `${state.version}-${entry.utc}-${state.tab}-${state.product}-${state.point}`);
    const image = $('#resultado-img');
    $('#shot').hidden = false;
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
    requestAnimationFrame(fitFigure);
  }

  function renderParams(products, points) {
    const root = $('#params');
    root.replaceChildren();
    const addGroup = (title, items, attr, chosen) => {
      if (!items.length) return;
      const section = document.createElement('section');
      section.className = 'pgroup';
      const heading = document.createElement('h3');
      heading.textContent = title;
      const box = document.createElement('div');
      box.className = 'pbtns';
      for (const [key, label] of items) {
        const button = document.createElement('button');
        button.type = 'button';
        button.className = `pbtn${key === chosen ? ' on' : ''}`;
        button.dataset[attr] = key;
        button.textContent = label;
        box.appendChild(button);
      }
      section.append(heading, box);
      root.appendChild(section);
    };
    if (state.tab === 'sondagem') {
      addGroup('Pontos', points, 'point', state.point);
      if (!points.length) root.innerHTML = '<p class="params-note">Sem sondagens nesta rodada.</p>';
      return;
    }
    const labels = new Map(products);
    const used = new Set();
    for (const [title, keys] of GROUPS) {
      const items = keys.filter(key => labels.has(key)).map(key => [key, labels.get(key)]);
      items.forEach(([key]) => used.add(key));
      addGroup(title, items, 'product', state.product);
    }
    const rest = products.filter(([key]) => !used.has(key));
    if (rest.length) addGroup('Outros', rest, 'product', state.product);
    if (!products.length) root.innerHTML = '<p class="params-note">Os parâmetros aparecem quando a rodada publicar os mapas.</p>';
  }

  function fitFigure() {
    const fig = $('#fig');
    const img = $('#resultado-img');
    if (!fig || !img) return;
    if (fig.classList.contains('sond')) {
      img.style.maxHeight = 'none';
      img.style.maxWidth = '100%';
      return;
    }
    const h = fig.clientHeight;
    const w = fig.clientWidth;
    if (h < 20 || w < 20) return;
    img.style.maxHeight = `${Math.floor(h)}px`;
    img.style.maxWidth = `${Math.floor(w)}px`;
  }

  function showSondProgress(pct, msg, kind) {
    const box = $('#sond-progress');
    box.hidden = false;
    box.classList.toggle('ok', kind === 'ok');
    box.classList.toggle('bad', kind === 'bad');
    const n = Math.max(0, Math.min(100, Math.round(pct)));
    $('#sond-progress-fill').style.width = `${n}%`;
    $('#sond-progress-track').setAttribute('aria-valuenow', String(n));
    $('#sond-progress-pct').textContent = `${n}%`;
    $('#sond-progress-label').textContent = kind === 'bad' ? 'Sondagem falhou' : kind === 'ok' ? 'Sondagem pronta' : 'Sondagem do ponto';
    $('#sond-progress-msg').textContent = msg || '';
    const note = $('#sondagem-status');
    note.hidden = false;
    note.textContent = `${n}% — ${msg || ''}`;
    requestAnimationFrame(fitFigure);
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
      const signature = JSON.stringify({ init: manifest.init, tempos: manifest.tempos, falhas: manifest.falhas, geom: manifest.geom, mapa: manifest.mapa });
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
    requestAnimationFrame(fitFigure);
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
  $('#params').addEventListener('click', (event) => {
    const button = event.target.closest('button[data-product], button[data-point]');
    if (!button) return;
    if (button.dataset.product) { state.product = button.dataset.product; state.showingPoint = false; }
    if (button.dataset.point) { state.point = button.dataset.point; state.showingPoint = false; }
    render();
  });

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
    const headers = { Accept: 'application/vnd.github+json', 'X-GitHub-Api-Version': '2022-11-28' };
    if (token) headers.Authorization = `Bearer ${token}`;
    const tick = async () => {
      if (state.pointWatch !== pedido.id) return;
      try {
        const imagem = `https://raw.githubusercontent.com/${repo}/sondagens/${pedido.nome}.png?t=${Date.now()}`;
        const imgRes = await fetch(imagem, { cache: 'no-store' });
        if (imgRes.ok) {
          const buf = await imgRes.arrayBuffer();
          const b = new Uint8Array(buf);
          const png = b.length > 1000 && b[0] === 0x89 && b[1] === 0x50 && b[2] === 0x4e && b[3] === 0x47;
          if (png) {
            if (state.pick?.objectUrl) URL.revokeObjectURL(state.pick.objectUrl);
            const url = URL.createObjectURL(new Blob([buf], { type: 'image/png' }));
            state.pick = { lat: pedido.lat, lon: pedido.lon, url, objectUrl: url };
            state.showingPoint = true;
            state.pointWatch = null;
            showSondProgress(100, 'Sondagem pronta. Ela substitui o mapa.', 'ok');
            render();
            $('#fig').scrollIntoView({ block: 'start', behavior: 'smooth' });
            return;
          }
        }
        let pct = Math.min(88, 8 + Math.round((Date.now() - pedido.t0) / 1600));
        let msg = 'Na fila do GitHub';
        const runsRes = await fetch(`https://api.github.com/repos/${repo}/actions/workflows/sondagem.yml/runs?per_page=8&event=workflow_dispatch`, { headers, cache: 'no-store' });
        if (runsRes.ok) {
          const runs = await runsRes.json();
          const run = (runs.workflow_runs || []).find(item => Date.parse(item.created_at) >= pedido.t0 - 20000);
          if (run) {
            if (run.status === 'completed' && run.conclusion && run.conclusion !== 'success') {
              state.pointWatch = null;
              showSondProgress(100, `A sondagem falhou (${run.conclusion}). Veja o log no GitHub Actions.`, 'bad');
              return;
            }
            if (run.status === 'completed' && run.conclusion === 'success') {
              const acabou = Date.parse(run.updated_at || run.created_at);
              if (Number.isFinite(acabou) && Date.now() - acabou > 180000) {
                state.pointWatch = null;
                showSondProgress(100, 'O job terminou, mas a imagem não apareceu. Veja o passo "Publicar a imagem no site" no log.', 'bad');
                return;
              }
              pct = 96;
              msg = 'Job concluído. Esperando a imagem aparecer no site…';
            } else if (run.status === 'queued' || run.status === 'waiting' || run.status === 'pending') {
              pct = 8;
              msg = 'Na fila do GitHub';
            } else {
              const jobsRes = await fetch(`https://api.github.com/repos/${repo}/actions/runs/${run.id}/jobs`, { headers, cache: 'no-store' });
              if (jobsRes.ok) {
                const jobs = await jobsRes.json();
                const steps = (jobs.jobs || [])[0]?.steps || [];
                if (steps.length) {
                  const done = steps.filter(step => step.status === 'completed').length;
                  const current = steps.find(step => step.status === 'in_progress');
                  pct = Math.min(96, Math.round((done + (current ? 0.5 : 0)) / steps.length * 100));
                  msg = current?.name || 'Gerando a sondagem';
                } else {
                  pct = Math.max(pct, 18);
                  msg = 'Iniciando a sondagem';
                }
              }
            }
          }
        }
        showSondProgress(pct, msg, '');
      } catch (error) {
        showSondProgress(Math.min(88, 8 + Math.round((Date.now() - pedido.t0) / 1600)), `Ainda lendo o GitHub (${error.message})`, '');
      }
      window.setTimeout(tick, 8000);
    };
    window.setTimeout(tick, 4000);
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
    const repo = repoName();
    const token = $('#token').value.trim();
    if (!token) { box.hidden = false; box.textContent = 'Cole o token do GitHub na caixa Nova rodada. Ele fica só nesta aba.'; return; }
    const tempo = entry.utc.replace(/\D/g, '').slice(0, 10);
    const lat = state.pick.lat.toFixed(4);
    const lon = state.pick.lon.toFixed(4);
    const nome = `sond_${tempo}_${lat}_${lon}_${Date.now().toString(36)}`;
    showSondProgress(4, 'Enviando o pedido…', '');
    $('#fig').scrollIntoView({ block: 'start', behavior: 'smooth' });
    try {
      const response = await fetch(`https://api.github.com/repos/${repo}/actions/workflows/sondagem.yml/dispatches`, {
        method: 'POST',
        headers: { Authorization: `Bearer ${token}`, Accept: 'application/vnd.github+json', 'X-GitHub-Api-Version': '2022-11-28', 'Content-Type': 'application/json' },
        body: JSON.stringify({ ref: 'main', inputs: { lat, lon, tempo, init: state.manifest?.init || '', nome } }),
      });
      if (response.status !== 204) {
        const detail = await response.text();
        box.hidden = false;
        showSondProgress(100, 'O pedido não foi aceito.', 'bad');
        box.textContent = `O GitHub respondeu HTTP ${response.status}. Confira o token e se sondagem.yml está na branch main.\n${detail.slice(0, 400)}`;
        return;
      }
    } catch (error) {
      box.hidden = false;
      showSondProgress(100, 'Não foi possível enviar.', 'bad');
      box.textContent = `Não foi possível enviar a sondagem: ${error.message}.`;
      return;
    }
    const pedido = { id: Date.now(), lat: Number(lat), lon: Number(lon), tempo, nome, t0: Date.now() };
    state.pointWatch = pedido.id;
    showSondProgress(8, `Pedido enviado para ${lat}, ${lon}. A barra acompanha o GitHub.`, '');
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
    $('#theme').textContent = theme === 'light' ? '☾' : '☀';
    $('#theme').title = theme === 'light' ? 'Tema escuro' : 'Tema claro';
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
  window.addEventListener('resize', fitFigure);
  if (window.ResizeObserver) new ResizeObserver(() => fitFigure()).observe($('#fig'));
  $('#resultado-img').addEventListener('load', () => {
    fitFigure();
    if (state.showingPoint) $('#sond-progress').hidden = true;
  });
  window.setInterval(() => { if (document.visibilityState === 'visible') loadManifest({ quiet: true }); }, POLL_MS);
  document.addEventListener('visibilitychange', () => {
    if (document.visibilityState === 'visible') loadManifest({ quiet: true });
  });

  const GIF_BITS = 12;
  const GIF_HSIZE = 5003;
  const GIF_MASKS = [0, 1, 3, 7, 15, 31, 63, 127, 255, 511, 1023, 2047, 4095, 8191, 16383, 32767, 65535];
  function lzwBytes(pixels, colorDepth) {
    const initCodeSize = Math.max(2, colorDepth);
    const gInit = initCodeSize + 1;
    const htab = new Int32Array(GIF_HSIZE);
    const codetab = new Int32Array(GIF_HSIZE);
    htab.fill(-1);
    const out = [initCodeSize];
    const accum = new Uint8Array(256);
    let curAcc = 0;
    let curBits = 0;
    let aCount = 0;
    let nBits = gInit;
    let maxcode = (1 << nBits) - 1;
    const clearCode = 1 << (gInit - 1);
    const eoi = clearCode + 1;
    let freeEnt = clearCode + 2;
    let clearFlg = false;
    let hshift = 0;
    for (let fcode = GIF_HSIZE; fcode < 65536; fcode *= 2) hshift += 1;
    hshift = 8 - hshift;
    const flush = (n) => {
      out.push(n);
      for (let i = 0; i < n; i += 1) out.push(accum[i]);
    };
    const output = (code) => {
      curAcc &= GIF_MASKS[curBits];
      if (curBits > 0) curAcc |= code << curBits;
      else curAcc = code;
      curBits += nBits;
      while (curBits >= 8) {
        accum[aCount] = curAcc & 255;
        aCount += 1;
        if (aCount >= 254) { flush(aCount); aCount = 0; }
        curAcc >>= 8;
        curBits -= 8;
      }
      if (freeEnt > maxcode || clearFlg) {
        if (clearFlg) {
          nBits = gInit;
          maxcode = (1 << nBits) - 1;
          clearFlg = false;
        } else {
          nBits += 1;
          maxcode = nBits === GIF_BITS ? (1 << nBits) : (1 << nBits) - 1;
        }
      }
      if (code === eoi) {
        while (curBits > 0) {
          accum[aCount] = curAcc & 255;
          aCount += 1;
          if (aCount >= 254) { flush(aCount); aCount = 0; }
          curAcc >>= 8;
          curBits -= 8;
        }
        if (aCount > 0) { flush(aCount); aCount = 0; }
      }
    };
    output(clearCode);
    let ent = pixels[0];
    for (let idx = 1; idx < pixels.length; idx += 1) {
      const c = pixels[idx];
      const fcode = (c << GIF_BITS) + ent;
      let i = ((c << hshift) ^ ent) % GIF_HSIZE;
      if (i < 0) i += GIF_HSIZE;
      if (htab[i] === fcode) { ent = codetab[i]; continue; }
      const disp = i === 0 ? 1 : GIF_HSIZE - i;
      while (htab[i] >= 0) {
        i -= disp;
        if (i < 0) i += GIF_HSIZE;
        if (htab[i] === fcode) { ent = codetab[i]; break; }
      }
      if (htab[i] === fcode) continue;
      output(ent);
      ent = c;
      if (freeEnt < (1 << GIF_BITS)) {
        codetab[i] = freeEnt;
        freeEnt += 1;
        htab[i] = fcode;
      } else {
        htab.fill(-1);
        freeEnt = clearCode + 2;
        clearFlg = true;
        output(clearCode);
      }
    }
    output(ent);
    output(eoi);
    out.push(0);
    return out;
  }
  function quantize(rgba, maxColors) {
    const hist = new Map();
    for (let i = 0; i < rgba.length; i += 4) {
      const r = rgba[i] & 248;
      const g = rgba[i + 1] & 248;
      const b = rgba[i + 2] & 248;
      const key = (r << 16) | (g << 8) | b;
      hist.set(key, (hist.get(key) || 0) + 1);
    }
    let colors = [];
    for (const [k, c] of hist) colors.push({ r: (k >> 16) & 255, g: (k >> 8) & 255, b: k & 255, c });
    if (!colors.length) colors = [{ r: 0, g: 0, b: 0, c: 1 }];
    const rangeOf = (box) => {
      let r0 = 255, r1 = 0, g0 = 255, g1 = 0, b0 = 255, b1 = 0, n = 0;
      for (const p of box) {
        if (p.r < r0) r0 = p.r;
        if (p.r > r1) r1 = p.r;
        if (p.g < g0) g0 = p.g;
        if (p.g > g1) g1 = p.g;
        if (p.b < b0) b0 = p.b;
        if (p.b > b1) b1 = p.b;
        n += p.c;
      }
      const rs = r1 - r0, gs = g1 - g0, bs = b1 - b0;
      let ch = 'r', span = rs;
      if (gs >= span) { ch = 'g'; span = gs; }
      if (bs >= span) { ch = 'b'; span = bs; }
      return { ch, span, n };
    };
    const boxes = [colors];
    while (boxes.length < maxColors) {
      let bi = -1, best = -1;
      for (let i = 0; i < boxes.length; i += 1) {
        if (boxes[i].length < 2) continue;
        const info = rangeOf(boxes[i]);
        const score = info.span * info.n;
        if (score > best) { best = score; bi = i; }
      }
      if (bi < 0) break;
      const box = boxes.splice(bi, 1)[0];
      const ch = rangeOf(box).ch;
      box.sort((p, q) => p[ch] - q[ch]);
      let total = 0;
      for (const p of box) total += p.c;
      let half = 0;
      let mid = box.length - 1;
      for (let i = 0; i < box.length - 1; i += 1) {
        half += box[i].c;
        if (half >= total / 2) { mid = i + 1; break; }
      }
      boxes.push(box.slice(0, mid), box.slice(mid));
    }
    const pal = [];
    for (const box of boxes) {
      let r = 0, g = 0, b = 0, c = 0;
      for (const p of box) { r += p.r * p.c; g += p.g * p.c; b += p.b * p.c; c += p.c; }
      pal.push([Math.round(r / c), Math.round(g / c), Math.round(b / c)]);
    }
    while (pal.length < maxColors) pal.push(pal[pal.length - 1] || [0, 0, 0]);
    return pal;
  }
  function applyPalette(rgba, pal) {
    const cache = new Map();
    const idx = new Uint8Array(rgba.length >> 2);
    let p = 0;
    for (let i = 0; i < rgba.length; i += 4) {
      const key = (rgba[i] << 16) | (rgba[i + 1] << 8) | rgba[i + 2];
      let c = cache.get(key);
      if (c === undefined) {
        let best = 0;
        let bestd = Infinity;
        const r = rgba[i], g = rgba[i + 1], b = rgba[i + 2];
        for (let j = 0; j < pal.length; j += 1) {
          const dr = r - pal[j][0], dg = g - pal[j][1], db = b - pal[j][2];
          const d = dr * dr + dg * dg + db * db;
          if (d < bestd) { bestd = d; best = j; if (!d) break; }
        }
        c = best;
        cache.set(key, c);
      }
      idx[p] = c;
      p += 1;
    }
    return idx;
  }
  function gifFrameBytes(rgba, w, h, delayCs) {
    const pal = quantize(rgba, 256);
    const idx = applyPalette(rgba, pal);
    const a = [
      0x21, 0xf9, 0x04, 0x08, delayCs & 255, (delayCs >> 8) & 255, 0, 0,
      0x2c, 0, 0, 0, 0, w & 255, (w >> 8) & 255, h & 255, (h >> 8) & 255, 0x87,
    ];
    for (const [r, g, b] of pal) a.push(r, g, b);
    for (const byte of lzwBytes(idx, 8)) a.push(byte);
    return Uint8Array.from(a);
  }
  function gifHeader(w, h) {
    return Uint8Array.from([
      0x47, 0x49, 0x46, 0x38, 0x39, 0x61,
      w & 255, (w >> 8) & 255, h & 255, (h >> 8) & 255, 0, 0, 0,
      0x21, 0xff, 0x0b,
      0x4e, 0x45, 0x54, 0x53, 0x43, 0x41, 0x50, 0x45, 0x32, 0x2e, 0x30,
      0x03, 0x01, 0, 0, 0,
    ]);
  }
  function concatBytes(parts) {
    let n = 0;
    for (const part of parts) n += part.length;
    const all = new Uint8Array(n);
    let offset = 0;
    for (const part of parts) { all.set(part, offset); offset += part.length; }
    return all;
  }
  async function loadBitmap(url) {
    const response = await fetch(url, { cache: 'force-cache', credentials: 'same-origin' });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const blob = await response.blob();
    if (typeof createImageBitmap === 'function') return createImageBitmap(blob);
    const img = new Image();
    const objectUrl = URL.createObjectURL(blob);
    try {
      await new Promise((resolve, reject) => {
        img.onload = resolve;
        img.onerror = () => reject(new Error('imagem inválida'));
        img.src = objectUrl;
      });
    } finally {
      URL.revokeObjectURL(objectUrl);
    }
    return img;
  }
  function sequenceFrames() {
    const times = state.manifest?.tempos || [];
    return times.map((entry, index) => {
      const file = state.tab === 'sondagem' ? entry?.sondagens?.[state.point] : entry?.mapas?.[state.product];
      return file ? { index, file, label: `${fmtDate(entry.utc)} ${utcHour(entry.utc)}Z` } : null;
    }).filter(Boolean);
  }
  function fillGifSelects() {
    const ini = $('#gif-ini');
    const fim = $('#gif-fim');
    if (!ini || !fim) return;
    const prevIni = ini.value;
    const prevFim = fim.value;
    const frames = sequenceFrames();
    ini.replaceChildren();
    fim.replaceChildren();
    for (const frame of frames) {
      for (const select of [ini, fim]) {
        const option = document.createElement('option');
        option.value = String(frame.index);
        option.textContent = frame.label;
        select.appendChild(option);
      }
    }
    if (!frames.length) return;
    ini.value = [...ini.options].some((option) => option.value === prevIni) ? prevIni : String(frames[0].index);
    fim.value = [...fim.options].some((option) => option.value === prevFim) ? prevFim : String(frames[frames.length - 1].index);
  }
  async function downloadGif() {
    const status = $('#gif-status');
    const button = $('#gif-go');
    const frames = sequenceFrames();
    if (!frames.length) { status.textContent = 'Não há imagens deste parâmetro para animar.'; return; }
    let start = Number($('#gif-ini').value);
    let end = Number($('#gif-fim').value);
    if (!Number.isFinite(start) || !Number.isFinite(end)) { status.textContent = 'Escolha a imagem inicial e a final.'; return; }
    if (end < start) [start, end] = [end, start];
    const chosen = frames.filter((frame) => frame.index >= start && frame.index <= end);
    if (!chosen.length) { status.textContent = 'Não há imagens entre esses horários.'; return; }
    const seconds = Number($('#gif-delay').value);
    if (!Number.isFinite(seconds) || seconds < 0.1 || seconds > 5) {
      status.textContent = 'O tempo por imagem fica entre 0,1 e 5 segundos.';
      return;
    }
    const delayCs = Math.max(2, Math.min(500, Math.round(seconds * 100)));
    button.disabled = true;
    $('#gif-toggle').disabled = true;
    try {
      const first = await loadBitmap(fileUrl(chosen[0].file, state.version));
      const scale = Math.min(1, 640 / Math.max(first.width, first.height));
      const w = Math.max(1, Math.round(first.width * scale));
      const h = Math.max(1, Math.round(first.height * scale));
      const canvas = document.createElement('canvas');
      canvas.width = w;
      canvas.height = h;
      const ctx = canvas.getContext('2d', { willReadFrequently: true });
      const parts = [gifHeader(w, h)];
      const paint = (bitmap) => {
        ctx.drawImage(bitmap, 0, 0, w, h);
        return ctx.getImageData(0, 0, w, h).data;
      };
      status.textContent = `Montando o GIF… 1/${chosen.length}`;
      parts.push(gifFrameBytes(paint(first), w, h, delayCs));
      first.close?.();
      for (let i = 1; i < chosen.length; i += 1) {
        status.textContent = `Montando o GIF… ${i + 1}/${chosen.length}`;
        await new Promise((resolve) => setTimeout(resolve, 0));
        const bitmap = await loadBitmap(fileUrl(chosen[i].file, state.version));
        parts.push(gifFrameBytes(paint(bitmap), w, h, delayCs));
        bitmap.close?.();
      }
      parts.push(Uint8Array.of(0x3b));
      const blob = new Blob([concatBytes(parts)], { type: 'image/gif' });
      const url = URL.createObjectURL(blob);
      const link = document.createElement('a');
      const tag = state.tab === 'sondagem' ? state.point : state.product;
      link.href = url;
      link.download = `vale1km_${tag}.gif`;
      link.rel = 'noopener';
      document.body.appendChild(link);
      link.click();
      link.remove();
      setTimeout(() => URL.revokeObjectURL(url), 8000);
      const tempo = seconds.toLocaleString('pt-BR', { maximumFractionDigits: 1 });
      status.textContent = `GIF baixado: ${chosen.length} ${chosen.length === 1 ? 'imagem' : 'imagens'}, ${tempo} s cada.`;
    } catch (error) {
      status.textContent = `Não foi possível montar o GIF (${error.message}).`;
    } finally {
      button.disabled = false;
      $('#gif-toggle').disabled = false;
    }
  }
  $('#gif-toggle').addEventListener('click', () => {
    const box = $('#gifbox');
    box.hidden = !box.hidden;
    const open = !box.hidden;
    $('#gif-toggle').setAttribute('aria-expanded', String(open));
    $('#gif-toggle').classList.toggle('on', open);
    if (open) fillGifSelects();
  });
  $('#gif-go').addEventListener('click', () => { if (!$('#gif-go').disabled) downloadGif(); });

})();
