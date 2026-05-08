/* Miles Radar — Application Logic */

const TRANSFER_SOURCES = [
  { id: 'esfera', name: 'Esfera',     color: '#dc2626', bg: 'rgba(220,38,38,0.12)'  },
  { id: 'livelo', name: 'Livelo',     color: '#7c3aed', bg: 'rgba(124,58,237,0.12)' },
];

const TRANSFER_DESTS = [
  { id: 'smiles', name: 'Smiles',     color: '#f97316', bg: 'rgba(249,115,22,0.12)' },
  { id: 'latam',  name: 'LATAM Pass', color: '#0ea5e9', bg: 'rgba(14,165,233,0.12)' },
  { id: 'azul',   name: 'TudoAzul',  color: '#2563eb', bg: 'rgba(37,99,235,0.12)'  },
];

const ACCUM_PROGRAMS = [
  { id: 'esfera', name: 'Esfera',     color: '#dc2626', bg: 'rgba(220,38,38,0.12)'  },
  { id: 'livelo', name: 'Livelo',     color: '#7c3aed', bg: 'rgba(124,58,237,0.12)' },
  { id: 'smiles', name: 'Smiles',     color: '#f97316', bg: 'rgba(249,115,22,0.12)' },
  { id: 'latam',  name: 'LATAM Pass', color: '#0ea5e9', bg: 'rgba(14,165,233,0.12)' },
  { id: 'azul',   name: 'TudoAzul',  color: '#2563eb', bg: 'rgba(37,99,235,0.12)'  },
];

// Lookup unificado para renderização de pares salvos
const ALL_PROGRAMS = [...new Map(
  [...TRANSFER_SOURCES, ...TRANSFER_DESTS].map(p => [p.id, p])
).values()];

const _UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
function isValidUserId(id) { return id && _UUID_RE.test(id); }

let userId    = localStorage.getItem('milesRadarUserId');
let userEmail = localStorage.getItem('milesRadarEmail');
let selectedAccum   = new Set();
let transferPairs   = [];
let selectedSources = new Set();
let selectedDests   = new Set();

/* ── Slots badge ── */
async function loadSlots() {
  const badge = document.getElementById('slots-badge');
  const text  = document.getElementById('slots-text');
  if (!badge || !text) return;
  try {
    const res  = await fetch('/api/preferences/slots');
    const data = await res.json();
    if (data.remaining <= 0) {
      text.textContent = 'Vagas esgotadas';
      badge.classList.add('full');
    } else {
      text.innerHTML = `<span class="slots-number">${data.remaining}</span> vaga${data.remaining === 1 ? '' : 's'} restante${data.remaining === 1 ? '' : 's'}`;
    }
  } catch {
    badge.style.display = 'none';
  }
}

/* ── Navbar scroll behavior ── */
function initNavbar() {
  const navbar = document.getElementById('navbar');
  if (!navbar) return;
  window.addEventListener('scroll', () => {
    navbar.classList.toggle('scrolled', window.scrollY > 20);
  }, { passive: true });
}

/* ── Reveal on scroll ── */
function initReveal() {
  const els = document.querySelectorAll('.reveal');
  if (!els.length) return;
  const io = new IntersectionObserver(entries => {
    entries.forEach(e => {
      if (e.isIntersecting) {
        e.target.classList.add('visible');
        io.unobserve(e.target);
      }
    });
  }, { threshold: 0.1 });
  els.forEach(el => io.observe(el));
}

/* ── Build accumulation grid ── */
function buildAccumGrid() {
  const grid = document.getElementById('accum-grid');
  if (!grid) return;
  ACCUM_PROGRAMS.forEach(p => {
    const chip = document.createElement('div');
    chip.className = 'prog-chip';
    chip.dataset.id = p.id;
    chip.style.setProperty('--prog-color', p.color);
    chip.style.setProperty('--prog-bg', p.bg);
    chip.innerHTML = `<span class="prog-dot"></span><span class="prog-name">${p.name}</span>`;
    chip.addEventListener('click', () => toggleAccum(p.id, chip));
    grid.appendChild(chip);
  });
}

/* ── Build pair wizard chips ── */
function buildPairChips() {
  const srcGrid = document.getElementById('pair-src-chips');
  const dstGrid = document.getElementById('pair-dst-chips');
  if (!srcGrid || !dstGrid) return;

  TRANSFER_SOURCES.forEach(p => {
    const chip = document.createElement('div');
    chip.className = 'prog-chip pair-chip';
    chip.dataset.id = p.id;
    chip.style.setProperty('--prog-color', p.color);
    chip.style.setProperty('--prog-bg', p.bg);
    chip.innerHTML = `<span class="prog-dot"></span><span class="prog-name">${p.name}</span>`;
    chip.addEventListener('click', () => togglePairSource(p.id, chip));
    srcGrid.appendChild(chip);
  });

  TRANSFER_DESTS.forEach(p => {
    const chip = document.createElement('div');
    chip.className = 'prog-chip pair-chip';
    chip.dataset.id = p.id;
    chip.style.setProperty('--prog-color', p.color);
    chip.style.setProperty('--prog-bg', p.bg);
    chip.innerHTML = `<span class="prog-dot"></span><span class="prog-name">${p.name}</span>`;
    chip.addEventListener('click', () => togglePairDest(p.id, chip));
    dstGrid.appendChild(chip);
  });
}

/* ── Toggle source chip (multi-select) ── */
function togglePairSource(id, chip) {
  if (selectedSources.has(id)) {
    selectedSources.delete(id);
    chip.classList.remove('selected');
  } else {
    selectedSources.add(id);
    chip.classList.add('selected');
  }
  updateAddPairButton();
}

/* ── Toggle destination chip (multi-select) ── */
function togglePairDest(id, chip) {
  if (selectedDests.has(id)) {
    selectedDests.delete(id);
    chip.classList.remove('selected');
  } else {
    selectedDests.add(id);
    chip.classList.add('selected');
  }
  updateAddPairButton();
}

/* ── Show/hide add button ── */
function updateAddPairButton() {
  const row = document.getElementById('pair-add-row');
  if (!row) return;
  row.style.display = (selectedSources.size > 0 && selectedDests.size > 0) ? 'block' : 'none';
}

/* ── Toggle accumulation chip ── */
function toggleAccum(id, chip) {
  if (selectedAccum.has(id)) {
    selectedAccum.delete(id);
    chip.classList.remove('selected');
  } else {
    selectedAccum.add(id);
    chip.classList.add('selected');
  }
}

/* ── Add all combinations from selected sources × dests ── */
function addPair() {
  if (selectedSources.size === 0 || selectedDests.size === 0) return;

  selectedSources.forEach(src => {
    selectedDests.forEach(dst => {
      if (src !== dst && !transferPairs.some(p => p.source === src && p.dest === dst)) {
        transferPairs.push({ source: src, dest: dst });
      }
    });
  });

  renderPairs();

  // Reset wizard
  selectedSources.clear();
  selectedDests.clear();
  document.querySelectorAll('.pair-chip').forEach(c => c.classList.remove('selected'));
  document.getElementById('pair-add-row').style.display = 'none';
}

/* ── Remove transfer pair ── */
function removePair(idx) {
  transferPairs.splice(idx, 1);
  renderPairs();
}

/* ── Render pairs list ── */
function renderPairs() {
  const list = document.getElementById('pairs-list');
  if (!list) return;
  list.innerHTML = '';

  if (transferPairs.length === 0) {
    list.innerHTML = '<span class="pairs-empty">Nenhum par adicionado.</span>';
    return;
  }

  transferPairs.forEach((pair, idx) => {
    const srcName = ALL_PROGRAMS.find(p => p.id === pair.source)?.name ?? pair.source;
    const dstName = ALL_PROGRAMS.find(p => p.id === pair.dest)?.name   ?? pair.dest;
    const tag = document.createElement('div');
    tag.className = 'pair-tag';
    tag.innerHTML = `${srcName} → ${dstName}<button class="pair-tag-remove" onclick="removePair(${idx})" title="Remover">×</button>`;
    list.appendChild(tag);
  });
}

/* ── Handle registration submit ── */
async function handleRegisterSubmit() {
  const nameInput  = document.getElementById('name-input');
  const emailInput = document.getElementById('email-input');
  const phoneInput = document.getElementById('phone-input');
  const errorEl    = document.getElementById('email-error');
  const btn        = document.getElementById('btn-continue');

  const name  = nameInput.value.trim();
  const email = emailInput.value.trim().toLowerCase();
  const phone = phoneInput.value.trim();

  errorEl.textContent = '';

  if (!name) {
    errorEl.textContent = 'Informe seu nome.';
    nameInput.focus();
    return;
  }
  if (!email || !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) {
    errorEl.textContent = 'Digite um e-mail válido.';
    emailInput.focus();
    return;
  }
  if (!phone || phone.length < 7) {
    errorEl.textContent = 'Informe um número de telefone válido.';
    phoneInput.focus();
    return;
  }

  btn.disabled = true;
  btn.innerHTML = '<span class="spinner"></span>';

  try {
    const res = await fetch('/api/preferences/register', {
      method:  'POST',
      headers: { 'Content-Type': 'application/json' },
      body:    JSON.stringify({ name, email, phone }),
    });

    if (!res.ok) {
      const detail = await res.json().catch(() => ({}));
      throw new Error(detail?.detail ?? 'Erro desconhecido');
    }

    const data = await res.json();
    userId    = data.user_id;
    userEmail = email;
    localStorage.setItem('milesRadarUserId', data.user_id);
    localStorage.setItem('milesRadarEmail',  email);

    showPrefsStep(email);
    if (!data.is_new) loadPreferences();

  } catch (e) {
    errorEl.textContent = e.message || 'Erro ao conectar. Verifique sua conexão e tente novamente.';
    console.error(e);
  } finally {
    btn.disabled = false;
    btn.textContent = 'Continuar';
  }
}

/* ── Load preferences from server and show step 2 (used from email link) ── */
async function loadAndShowPrefs() {
  try {
    const res = await fetch(`/api/preferences/${userId}`);
    if (!res.ok) {
      userId = null;
      localStorage.removeItem('milesRadarUserId');
      return;
    }
    const data = await res.json();
    if (data.email) {
      userEmail = data.email;
      localStorage.setItem('milesRadarEmail', data.email);
    }
    showPrefsStep(data.email || userId);
    loadPreferences();
  } catch (e) {
    console.error('Erro ao carregar perfil:', e);
  }
}

/* ── Load existing preferences ── */
async function loadPreferences() {
  try {
    const res = await fetch(`/api/preferences/${userId}`);
    if (!res.ok) return;

    const data = await res.json();

    transferPairs = (data.transfer_pairs ?? []).filter(p => p.source && p.dest);
    renderPairs();

    selectedAccum = new Set(data.accumulation_programs ?? []);
    document.querySelectorAll('#accum-grid .prog-chip').forEach(chip => {
      chip.classList.toggle('selected', selectedAccum.has(chip.dataset.id));
    });

  } catch (e) {
    console.error('Erro ao carregar preferências:', e);
  }
}

/* ── Save preferences ── */
async function savePreferences() {
  if (!isValidUserId(userId)) return;

  const btn       = document.getElementById('btn-save');
  const successEl = document.getElementById('save-success');
  const errorEl   = document.getElementById('save-error');

  successEl.classList.remove('show');
  errorEl.classList.remove('show');
  btn.disabled = true;
  btn.innerHTML = '<span class="spinner"></span> Salvando…';

  const allPrograms = new Set([
    ...transferPairs.flatMap(p => [p.source, p.dest]),
    ...selectedAccum,
  ]);

  const payload = {
    monitored_programs:    [...allPrograms],
    transfer_pairs:        transferPairs,
    accumulation_programs: [...selectedAccum],
  };

  try {
    const res = await fetch(`/api/preferences/${userId}`, {
      method:  'PUT',
      headers: { 'Content-Type': 'application/json' },
      body:    JSON.stringify(payload),
    });

    if (!res.ok) {
      const detail = await res.json().catch(() => ({}));
      throw new Error(detail?.detail ?? 'Erro ao salvar');
    }

    successEl.classList.add('show');
    successEl.scrollIntoView({ behavior: 'smooth', block: 'nearest' });

  } catch (e) {
    errorEl.textContent = e.message ?? 'Erro ao salvar. Tente novamente.';
    errorEl.classList.add('show');
    console.error(e);
  } finally {
    btn.disabled = false;
    btn.textContent = 'Salvar Preferências';
  }
}

/* ── Show preferences step ── */
function showPrefsStep(email) {
  document.getElementById('step-email').style.display = 'none';
  document.getElementById('step-prefs').style.display = 'block';
  document.getElementById('user-email-display').textContent = email;
}

/* ── Reset (go back to step 1) ── */
function resetEmail() {
  localStorage.removeItem('milesRadarUserId');
  localStorage.removeItem('milesRadarEmail');
  userId = null;
  userEmail = null;

  document.getElementById('step-email').style.display = 'block';
  document.getElementById('step-prefs').style.display = 'none';
  document.getElementById('name-input').value  = '';
  document.getElementById('email-input').value = '';
  document.getElementById('phone-input').value = '';
  document.getElementById('email-error').textContent = '';

  transferPairs = [];
  selectedAccum  = new Set();
  selectedSources.clear();
  selectedDests.clear();
  renderPairs();
  document.querySelectorAll('.prog-chip').forEach(c => c.classList.remove('selected'));
  const addRow = document.getElementById('pair-add-row');
  if (addRow) addRow.style.display = 'none';
  document.getElementById('save-success').classList.remove('show');
  document.getElementById('save-error').classList.remove('show');
}

/* ── Scroll to form ── */
function scrollToForm() {
  document.getElementById('form-anchor').scrollIntoView({ behavior: 'smooth' });
}

/* ── Bootstrap ── */
function init() {
  initNavbar();
  initReveal();
  loadSlots();
  buildAccumGrid();
  buildPairChips();

  const params   = new URLSearchParams(window.location.search);
  const uidParam = params.get('user_id');
  if (uidParam && isValidUserId(uidParam)) {
    userId = uidParam;
    localStorage.setItem('milesRadarUserId', uidParam);
  }

  if (isValidUserId(userId) && userEmail) {
    showPrefsStep(userEmail);
    loadPreferences();
  } else if (isValidUserId(userId) && !userEmail) {
    loadAndShowPrefs();
  }

  document.getElementById('phone-input').addEventListener('keydown', e => {
    if (e.key === 'Enter') handleRegisterSubmit();
  });
  document.getElementById('email-input').addEventListener('keydown', e => {
    if (e.key === 'Enter') handleRegisterSubmit();
  });
}

document.addEventListener('DOMContentLoaded', init);
