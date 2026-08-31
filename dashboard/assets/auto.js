// Auto-sim tab: rank candidates by simulated mean.
function renderAutoResults(list) {
  autoCandidates = list;
  document.getElementById("auto-results-wrap").style.display = "";
  document.querySelector("#auto-results tbody").innerHTML = list.map((c, i) => `<tr>
    <td class="num">${i + 1}</td>
    <td>${byCode[c.cpt].name}</td>
    <td>${c.drivers.map(code => byCode[code].name).join(", ")}</td>
    <td>${byCid[c.constructor].name}</td>
    <td class="num">${fmt$(c.salaryUsed)}</td>
    <td class="num" style="font-weight:600">${c.avg.toFixed(1)}</td>
    <td class="num">${c.min.toFixed(0)}–${c.max.toFixed(0)}</td>
    <td><button onclick="loadCandidate(${i})">Load</button></td>
  </tr>`).join("");
}

// Shared by both Load buttons (Auto Simulation and AI Simulation): reuses a
// candidate's already-computed chances (e.g. from computeAiChances() after
// Stop) if present, otherwise runs a fresh analysis for this specific
// lineup, then shows it on The Chances tab.
function showChancesForCandidate(c) {
  const chances = c.chances || analyzeTopLineupChances(c, 2000);
  renderChances(c, chances);
  switchTab("chances");
}

function loadCandidate(i) {
  const c = autoCandidates[i];
  lineup.cpt = c.cpt;
  lineup.drivers = [...c.drivers];
  lineup.constructor = c.constructor;
  render();
  showChancesForCandidate(c);
}

function runAutoSim() {
  const btn = document.getElementById("auto-run-btn");
  const status = document.getElementById("auto-status");
  const SHORTLIST = 50, SIMS_PER_CANDIDATE = 1000;
  btn.disabled = true;
  status.textContent = "Searching legal combinations…";
  setTimeout(() => {
    const shortlist = findTopCandidatesByProjection(SHORTLIST);
    status.textContent = `Shortlisted ${shortlist.length} candidates by projected points — ` +
      `simulating ${SIMS_PER_CANDIDATE} races each…`;
    setTimeout(() => {
      const evaluated = shortlist.map(c => ({ ...c, ...evaluateCandidate(c, SIMS_PER_CANDIDATE) }));
      evaluated.sort((a, b) => b.avg - a.avg);
      renderAutoResults(evaluated);
      status.textContent = `Ranked ${evaluated.length} candidates by simulated average score ` +
        `(${SIMS_PER_CANDIDATE} sims each). Click Load to send a lineup to the builder.`;
      const CHANCES_SIMS = 2000;
      const chances = analyzeTopLineupChances(evaluated[0], CHANCES_SIMS);
      renderChances(evaluated[0], chances);
      btn.disabled = false;
      switchTab("chances");
    }, 10);
  }, 10);
}

// ---------- AI simulation (continuous background loop) ----------
const AI = {
  running: false, timer: null, chancesTimer: null,
  shortlist: [], reserve: [], stats: [], chances: [], visible: [], order: [],
  // fitLocked[i]: once a slot's lineup is CONFIRMED to fit the description, it is
  // locked for the rest of the run — kept and simulated, never re-evaluated out on
  // measurement noise (the Min-pick-chance bar can't change mid-run). See ai.js.
  fitLocked: [],
  // Highest "weakest pick chance" any evaluated lineup has reached this run — i.e.
  // the highest Min-pick-chance bar the data can actually satisfy. Used to tell the
  // user when their bar is set higher than any lineup this race can meet.
  bestWeakestSeen: 0,
  totalSims: 0, filteredOutCount: 0, champFailStreak: 0,
};

// CONFIDENCE RANKING. Every row is scored by a LOWER confidence bound on its
// true average — its running average minus AI_RANK_Z standard errors — and the
// table is sorted by that bound, valid lineups (clearing the 5% bar) above
// invalid ones. The lower bound is what makes the order both intuitive and calm:
//   - A freshly-swapped lineup that posted a flashy average off just a handful
//     of sims has a huge standard error, so its bound is low and it sinks to the
//     bottom until more sims confirm the average is real. (This is why a row can
//     show a higher raw average than #1 yet sit below it — its number simply
//     isn't trusted yet.)
//   - A well-sampled lineup has a tiny standard error, so its bound ≈ its
//     average and it ranks right where it deserves.
// The noisy lineups that used to jump around are precisely the ones anchored low
// by their wide error bars, so the list stays calm without freezing anything.
//
// First place is exempt from this raw sort: AI.order[0] is the reigning champion
// and only changes hands via maybePromoteChampion() (a confidence-gated test),
// never on a momentary lower-bound crossing. computeAiOrder() pins the champion
// at rank 1 and confidence-sorts the other 19 beneath it.
const AI_RANK_Z = 2; // std errors subtracted from each average to get its ranking bound
