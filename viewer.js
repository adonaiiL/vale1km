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
  };

  const PRODUCT_DEFAULTS = [
    ['rf', 'Refletividade'], ['ws', 'Ventos'], ['t2', 'Temperatura'],
    ['rh', 'Umidade relativa'], ['pr', 'Precipitação'], ['td', 'Ponto de orvalho'],
    ['fr', 'Geada / T mínima'], ['ml', 'MLCAPE'], ['mu', 'MUCAPE'],
    ['sc', 'SCP'], ['vo', 'Vorticidade 850 hPa'], ['sn', 'Neve'],
    ['sh', 'Cisalhamento'], ['hd', 'Hodomap'],
  ];
  const POINT_DEFAULTS = { A: 'Adonai', F: 'Fabrício', K: 'Kelvin' };
  const POLL_MS = 60_000;

  const esc = (value) => String(value ?? '');
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
  const fileUrl = (name, version = Date.now()) => {
    const clean = String(name || '').split(/[\\/]/).pop();
    return `resultados/${encodeURIComponent(clean)}?v=${encodeURIComponent(version)}`;
  };
  const setStatus = (text) => { $('#result-status').textContent = text; };
  const showEmpty = (text) => {
    $('#resultado-img').hidden = true;
    $('#resultado-img').removeAttribute('src');
    $('#empty-state').hidden = false;
    $('#empty-state').textContent = text;
    $('#open-image').hidden = true;
    $('#open-image').removeAttribute('href');
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
    return PRODUCT_DEFAULTS.filter(([k]) => keys.has(k)).map(([k, label]) => [k, label || manifestLabels.get(k) || k]);
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
      const button = event.target.closest(`button[data-${dataAttribute.replace(/[A-Z]/g, m => `-${m.toLowerCase()}`)}]`);
      if (!button) return;
      callback(button.dataset[dataAttribute]);
    };
  };
  const countProducts = (manifest) => (manifest.tempos || []).reduce((sum, t) =>
    sum + Object.values(t.mapas || {}).filter(Boolean).length + Object.values(t.sondagens || {}).filter(Boolean).length, 0);

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
    $('#download-sounding').hidden = state.tab !== 'sondagem';
    $('#download-all-soundings').hidden = state.tab !== 'sondagem';
    $('#download-current').hidden = state.tab === 'sondagem';
    $('#product-heading').textContent = state.tab === 'mapa' ? 'Mapa meteorológico' : `Sondagem: ${points.find(p => p[0] === state.point)?.[1] || state.point}`;

    renderChips('#pm', products, state.product, 'product', (key) => { state.product = key; render(); });
    renderChips('#pts', points, state.point, 'point', (key) => { state.point = key; render(); });

    const timeButtons = $('#tb');
    timeButtons.replaceChildren();
    manifest.tempos.forEach((entry, index) => {
      const button = document.createElement('button');
      button.type = 'button';
      button.dataset.index = String(index);
      button.className = index === state.timeIndex ? 'chip on' : 'chip';
      const b = document.createElement('b');
      b.textContent = `${fmtDate(entry.utc)} ${utcHour(entry.utc)}Z`;
      const small = document.createElement('small');
      small.textContent = `${localLabel(entry.utc)} Brasília`;
      button.append(b, small);
      timeButtons.appendChild(button);
    });
    timeButtons.onclick = (event) => {
      const button = event.target.closest('button[data-index]');
      if (!button) return;
      state.timeIndex = Number(button.dataset.index);
      render();
    };

    const entry = currentTime();
    const file = state.tab === 'mapa' ? entry?.mapas?.[state.product] : entry?.sondagens?.[state.point];
    if (!file) {
      const selected = state.tab === 'mapa' ? products.find(p => p[0] === state.product)?.[1] || state.product : points.find(p => p[0] === state.point)?.[1] || state.point;
      showEmpty(`O produto “${selected}” não foi gerado para ${entry?.utc || 'este horário'}. Escolha outro horário ou variável.`);
      $('#figure-caption').textContent = `Horário válido: ${entry?.utc || 'indisponível'} UTC.`;
      return;
    }
    // The query component changes on each render so browsers do not keep a stale PNG after a rerun.
    const url = fileUrl(file, `${state.version}-${entry.utc}-${state.tab}-${state.product}-${state.point}`);
    const image = $('#resultado-img');
    image.hidden = false;
    $('#empty-state').hidden = true;
    image.alt = state.tab === 'mapa' ? `Mapa ${state.product}, válido ${entry.utc} UTC` : `Sondagem ${state.point}, válida ${entry.utc} UTC`;
    image.onerror = () => showEmpty(`Não foi possível carregar “${file}”. A publicação pode ainda estar sendo atualizada; clique em “Verificar agora” em alguns instantes.`);
    image.src = url;
    state.currentFile = file;
    state.currentUrl = url;
    $('#open-image').hidden = false;
    $('#open-image').href = url;
    $('#figure-caption').textContent = `Válido: ${entry.utc} UTC · ${entry.brt ? `${entry.brt.replace('T', ' ')} Brasília` : `${localLabel(entry.utc)} Brasília`} · Arquivo: ${file}`;
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
      const signature = JSON.stringify({ init: manifest.init, tempos: manifest.tempos, falhas: manifest.falhas });
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
      $('#result-meta').textContent = `Inicialização ICON: ${manifest.init || 'não informada'} UTC · ${manifest.tempos.length} horários · ${countProducts(manifest)} produtos · Último horário: ${latest} UTC${changed ? ' · novos dados detectados' : ''}`;
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
    const entry = activeEntry(); downloadFile(entry?.sondagens?.[state.point]);
  });
  $('#download-all-soundings').addEventListener('click', () => {
    const entry = activeEntry();
    const files = ['A', 'F', 'K'].map(key => entry?.sondagens?.[key]).filter(Boolean);
    files.forEach((file, index) => window.setTimeout(() => downloadFile(file), index * 350));
  });
  $('#check-refresh').addEventListener('click', () => loadManifest());
  $('#tabs').addEventListener('click', (event) => {
    const button = event.target.closest('button[data-tab]');
    if (!button) return;
    state.tab = button.dataset.tab;
    render();
  });

  function populateHours() {
    const hours = Array.from({ length: 24 }, (_, h) => String(h).padStart(2, '0'));
    for (const id of ['start-hour', 'end-hour']) {
      const select = $(`#${id}`);
      select.replaceChildren(...hours.map(hour => {
        const option = document.createElement('option'); option.value = hour; option.textContent = `${hour}Z`; return option;
      }));
    }
    $('#start-hour').value = '15';
    $('#end-hour').value = '21';
  }
  const dateValue = (date) => `${date.getUTCFullYear()}-${String(date.getUTCMonth() + 1).padStart(2, '0')}-${String(date.getUTCDate()).padStart(2, '0')}`;
  function selectedWindow() {
    const date = $('#valid-date').value;
    if (!date) throw new Error('Informe o dia válido da previsão.');
    const [year, month, day] = date.split('-').map(Number);
    const startHour = Number($('#start-hour').value);
    const endHour = Number($('#end-hour').value);
    const step = Number($('#step-hour').value);
    const start = Date.UTC(year, month - 1, day, startHour);
    let end = Date.UTC(year, month - 1, day, endHour);
    if (end < start) end += 24 * 60 * 60 * 1000;
    if (step <= 0 || (end - start) / (step * 3600000) > 120) throw new Error('A janela contém horários demais. Reduza o período ou aumente o intervalo.');
    return { start: new Date(start).toISOString().slice(0, 13), end: new Date(end).toISOString().slice(0, 13), step };
  }
  async function dispatchRun(mode) {
    const output = $('#run-output');
    output.hidden = false;
    const repo = $('#repo').value.trim().replace(/^https:\/\/github\.com\//, '').replace(/\/$/, '');
    const token = $('#token').value.trim();
    const date = $('#run-date').value;
    const hour = $('#run-hour').value;
    if (!/^[^/\s]+\/[^/\s]+$/.test(repo)) { output.textContent = 'Informe o repositório no formato usuario/repositorio.'; return; }
    if (!token) { output.textContent = 'Cole um token do GitHub com permissão para iniciar workflows. Ele não é guardado pela página.'; return; }
    if (!date) { output.textContent = 'Informe a data de inicialização do ICON.'; return; }
    let window;
    try { window = selectedWindow(); } catch (error) { output.textContent = error.message; return; }
    const payload = { ref: 'main', inputs: {
      modo: mode, dominio: 'vale1km', init: `${date}T${hour}`,
      janela_ini: window.start, janela_fim: window.end, passo_h: String(window.step),
    } };
    output.textContent = 'Enviando a solicitação ao GitHub Actions…';
    try {
      const response = await fetch(`https://api.github.com/repos/${repo}/actions/workflows/vale1km.yml/dispatches`, {
        method: 'POST',
        headers: { Authorization: `Bearer ${token}`, Accept: 'application/vnd.github+json', 'X-GitHub-Api-Version': '2022-11-28', 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
      if (response.status === 204) {
        output.textContent = 'Rodada enviada com sucesso. Esta página continuará mostrando os últimos resultados e verificará automaticamente a nova publicação quando o WRF terminar.';
      } else {
        const detail = await response.text();
        output.textContent = `O GitHub respondeu HTTP ${response.status}. Verifique o nome do repositório, a permissão actions:write do token e se vale1km.yml está disponível.\n${detail.slice(0, 700)}`;
      }
    } catch (error) {
      output.textContent = `Não foi possível enviar a solicitação: ${error.message}. Abra a página publicada e confira a conexão com o GitHub.`;
    }
  }
  $('#download-icon').addEventListener('click', () => dispatchRun('baixar'));
  $('#run-wrf').addEventListener('click', () => dispatchRun('baixar_e_rodar'));

  populateHours();
  const today = new Date();
  $('#run-date').value = dateValue(today);
  const valid = new Date(Date.UTC(today.getUTCFullYear(), today.getUTCMonth(), today.getUTCDate() + 3));
  $('#valid-date').value = dateValue(valid);
  loadManifest();
  window.setInterval(() => { if (document.visibilityState === 'visible') loadManifest({ quiet: true }); }, POLL_MS);
  document.addEventListener('visibilitychange', () => { if (document.visibilityState === 'visible') loadManifest({ quiet: true }); });
})();
