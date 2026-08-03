// Single-race sim, sort binding, and startup wiring.
function runSim() {
  const race = simulateRace();
  simCount++;

  const picks = [];
  const cptD = race.order.find(d => d.code === lineup.cpt);
  const cptScore = scoreDriver(cptD, race);
  picks.push({ label: "CPT", name: cptD.name, mult: CPT_MULT, s: cptScore, dnf: cptD.dnf, cls: "" });
  for (const code of lineup.drivers) {
    const dd = race.order.find(d => d.code === code);
    picks.push({ label: "D", name: dd.name, mult: 1, s: scoreDriver(dd, race), dnf: dd.dnf, cls: "d" });
  }
  const cs = scoreConstructor(lineup.constructor, race);
  picks.push({ label: "CNSTR", name: byCid[lineup.constructor].name, mult: 1, s: cs, dnf: false, cls: "c" });

  const total = picks.reduce((s, p) => s + p.s.total * p.mult, 0);

  document.getElementById("total-score").textContent = total.toFixed(1);
  document.getElementById("sim-count").textContent =
    `Simulation #${simCount} · ${D.raceName} · random outcome from driver form`;

  document.querySelector("#breakdown tbody").innerHTML = picks.map(p => {
    const bonusItems = Object.entries(p.s.bonusDetail || {})
      .map(([k, v]) => `${k} +${v % 1 ? v.toFixed(2) : v}`)
      .join("<br>") || "—";
    return `<tr>
      <td><span class="slot-tag ${p.cls}">${p.label}</span>${p.name}${p.dnf ? ' <span class="dnf">DNF</span>' : ""}</td>
      <td class="num">${p.s.finish.toFixed(0)}</td>
      <td class="num ${p.s.diff > 0 ? "delta-up" : p.s.diff < 0 ? "delta-dn" : ""}">${p.s.diff > 0 ? "+" : ""}${p.s.diff.toFixed(0)}</td>
      <td style="font-size:12px;color:var(--text-secondary)">${bonusItems}</td>
      <td class="num">${p.mult !== 1 ? "×" + p.mult : ""}</td>
      <td class="num" style="font-weight:600">${(p.s.total * p.mult).toFixed(1)}</td>
    </tr>`;
  }).join("");

  const inMyLineup = new Set([lineup.cpt, ...lineup.drivers]);
  document.querySelector("#classification tbody").innerHTML = race.order.map(d => {
    const sc = scoreDriver(d, race);
    const delta = d.grid - d.finish;
    const mine = inMyLineup.has(d.code);
    return `<tr style="${mine ? "font-weight:600" : ""}">
      <td class="num"><span class="pos-badge">${d.dnf ? '<span class="dnf">DNF</span>' : "P" + d.finish}</span></td>
      <td>${teamDot(d.team)}${d.name}${mine ? " ★" : ""}</td>
      <td class="num">${d.grid}</td>
      <td class="num ${delta > 0 ? "delta-up" : delta < 0 ? "delta-dn" : ""}">${delta > 0 ? "+" + delta : delta}</td>
      <td class="num">${sc.total.toFixed(1)}</td>
    </tr>`;
  }).join("");

  document.getElementById("results").style.display = "block";
  document.getElementById("results").scrollIntoView({ behavior: "smooth" });
}

// ---------- init ----------
document.getElementById("race-name").textContent = D.raceName;
document.getElementById("race-title").textContent = "F1 DFS Lineup Simulator — " + D.raceName;

// Street-circuit banner: when the loaded race is a street circuit (STREET_CFG),
// drop a "Street circuit" tag into the empty space at the top of every tab, so
// it's clear on each tab that the street-circuit simulation is active. Shows on
// nothing when the race isn't a street circuit.
if (IS_STREET) {
  for (const id of ["tab-builder", "tab-auto", "tab-chances", "tab-ai", "tab-testing"]) {
    const panel = document.getElementById(id);
    if (!panel) continue;
    const badge = document.createElement("div");
    badge.textContent = "🧱 Street circuit — simulation adjusted for harder overtaking + safety-car chaos";
    badge.style.cssText =
      "display:inline-block;margin:0 0 14px;padding:6px 12px;border-radius:6px;" +
      "background:rgba(214,77,77,.12);color:var(--critical,#d64d4d);" +
      "border:1px solid rgba(214,77,77,.4);font-size:13px;font-weight:600;letter-spacing:.02em;";
    panel.insertBefore(badge, panel.firstChild);
  }
}

document.getElementById("sim-btn").onclick = runSim;
document.getElementById("resim-btn").onclick = runSim;
document.getElementById("clear-btn").onclick = clearLineup;
document.getElementById("auto-run-btn").onclick = runAutoSim;
document.getElementById("ai-start-btn").onclick = startAiSimulation;
document.getElementById("ai-stop-btn").onclick = stopAiSimulation;
document.getElementById("ai-min-chance").onchange = (e) => {
  // Only reachable while stopped — the dropdown is disabled during a run — so the
  // new bar simply takes effect on the next Start. No live re-check needed.
  MIN_PICK_CHANCE = parseFloat(e.target.value);
};
document.getElementById("quali-apply-btn").onclick = applyQualiGrid;
document.getElementById("quali-reset-btn").onclick = resetQualiGrid;
document.getElementById("testing-run-btn").onclick = runTestingAi;
document.getElementById("testing-year-select").onchange = () => showSeasonRaceList(true);
populateTestingYearDropdown();
function bindSort(selector, stateKey) {
  document.querySelectorAll(selector).forEach(th => {
    th.onclick = () => {
      const s = sortState[stateKey], k = th.dataset.k;
      if (s.key === k) s.asc = !s.asc; else { s.key = k; s.asc = false; }
      renderPool();
    };
  });
}
bindSort("th.sortable", "pool");
bindSort("th.csortable", "cpool");
document.getElementById("dm-close").onclick = closeDriverModal;
document.getElementById("driver-modal").onclick = (e) => {
  if (e.target.id === "driver-modal") closeDriverModal();
};
document.addEventListener("keydown", (e) => {
  if (e.key === "Escape") closeDriverModal();
});
render();
renderTyrePlans();
renderDriverPerformance();
initQualifying();

// The dashboard itself is already fully rendered by this point (render()
// etc. above run synchronously) — this overlay is purely a cosmetic pace
// car, revealing it once the car crosses the finish line rather than
// gating on any actual data/load work.
(function initSplash() {
  const overlay = document.getElementById("splash-overlay");
  const car = document.querySelector(".splash-car");
  const reveal = () => overlay.classList.add("hidden");
  car.addEventListener("animationend", reveal, { once: true });
  setTimeout(reveal, 3000); // safety net in case animationend doesn't fire
})();
