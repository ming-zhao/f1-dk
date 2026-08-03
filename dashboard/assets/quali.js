// Qualifying/grid entry, penalties, and persistence.
function computeGrid(order, penalties) {
  const ranked = order.map((code, i) => ({ code, key: (i + 1) + (penalties[code] || 0) }));
  ranked.sort((a, b) => a.key - b.key);
  const grid = {};
  ranked.forEach((r, i) => grid[r.code] = i + 1);
  return grid;
}

function renderQualiTable() {
  const preview = computeGrid(qualiOrder, qualiPenalties);
  document.querySelector("#quali-table tbody").innerHTML = qualiOrder.map((code, i) => {
    const d = byCode[code];
    const penalty = qualiPenalties[code] || 0;
    return `<tr>
      <td class="num">${i + 1}</td>
      <td>${teamDot(d.team)}${d.name}</td>
      <td class="num"><input type="number" min="0" max="30" value="${penalty}"
        style="width:48px" onchange="setQualiPenalty('${code}', this.value)"></td>
      <td class="num">${preview[code]}</td>
      <td style="white-space:nowrap">
        <button ${i === 0 ? "disabled" : ""} onclick="moveQualiRow('${code}',-1)">▲</button>
        <button ${i === qualiOrder.length - 1 ? "disabled" : ""} onclick="moveQualiRow('${code}',1)">▼</button>
      </td>
    </tr>`;
  }).join("");
}

function moveQualiRow(code, dir) {
  const i = qualiOrder.indexOf(code);
  const j = i + dir;
  if (j < 0 || j >= qualiOrder.length) return;
  [qualiOrder[i], qualiOrder[j]] = [qualiOrder[j], qualiOrder[i]];
  renderQualiTable();
  persistQualiEdit();
}

function setQualiPenalty(code, value) {
  qualiPenalties[code] = Math.max(0, parseInt(value, 10) || 0);
  renderQualiTable();
  persistQualiEdit();
}

// Called after any table edit. If a real grid is currently applied, re-apply so
// the live grid never goes stale relative to the table (and re-saves); if not,
// just persist the pending order/penalties so edits survive a reload too.
function persistQualiEdit() {
  if (fixedGrid) applyQualiGrid();
  else saveQualiState();
}

function applyQualiGrid() {
  fixedGrid = computeGrid(qualiOrder, qualiPenalties);
  saveQualiState();
  document.getElementById("quali-status").textContent =
    "Applied and saved — every simulation (Simulate race, Auto/AI Simulation, The Chances) now " +
    "uses this real grid, and it stays this way (even after a reload) until you change it again.";
}

function resetQualiGrid() {
  fixedGrid = null;
  saveQualiState();
  document.getElementById("quali-status").textContent =
    "Using simulated qualifying (randomized each run) — the default, until you Apply a real grid.";
}

// The grid you set persists across reloads in localStorage, keyed per race, so
// it stays exactly as you left it until you change it another way (Apply a
// different grid, or "Use simulated grid"). A different race = different key =
// its own saved grid, falling back to race_notes/simulated when none is saved.
// Wrapped in try/catch because a bare file:// origin can refuse storage.
const GRID_STORE_KEY = "f1dk_grid_" + D.raceName;
function saveQualiState() {
  try {
    localStorage.setItem(GRID_STORE_KEY, JSON.stringify({
      order: qualiOrder, penalties: qualiPenalties, applied: fixedGrid !== null,
    }));
  } catch (e) { /* storage unavailable — persistence just no-ops */ }
}
function loadQualiState() {
  try {
    const raw = localStorage.getItem(GRID_STORE_KEY);
    return raw ? JSON.parse(raw) : null;
  } catch (e) { return null; }
}

// If config/race_notes.yaml -> qualifying.order has been filled in (real
// post-qualifying classification), load it and apply it automatically — no
// manual reordering/clicking needed. Any driver missing from that list (e.g.
// a data mismatch) is appended in predicted order so nothing goes missing.
// Falls back to the normal simulated-qualifying default otherwise.
function initQualifying() {
  // A grid you previously set (saved per race) wins over everything else, so it
  // stays the way you left it until you change it again.
  const saved = loadQualiState();
  if (saved && saved.order && saved.order.length) {
    const known = saved.order.filter(code => byCode[code]);
    const missing = D.drivers.map(d => d.code).filter(code => !known.includes(code));
    qualiOrder = [...known, ...missing];
    for (const k in qualiPenalties) delete qualiPenalties[k];
    Object.assign(qualiPenalties, saved.penalties || {});
    renderQualiTable();
    if (saved.applied) applyQualiGrid(); else resetQualiGrid();
    return;
  }
  const q = D.raceNotes && D.raceNotes.qualifying;
  if (q && q.order && q.order.length) {
    const known = q.order.filter(code => byCode[code]);
    const missing = D.drivers.map(d => d.code).filter(code => !known.includes(code));
    qualiOrder = [...known, ...missing];
    Object.assign(qualiPenalties, q.penalties || {});
    renderQualiTable();
    applyQualiGrid();
  } else {
    renderQualiTable();
    resetQualiGrid();
  }
}

const TABS = ["builder", "auto", "chances", "ai"];
function switchTab(name) {
  for (const t of TABS) {
    document.getElementById(`tab-${t}`).style.display = t === name ? "" : "none";
    document.getElementById(`tab-${t}-btn`).classList.toggle("active", t === name);
  }
}
