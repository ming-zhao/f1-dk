// AI-sim tab: rank, promote, repair and re-seed lineups continuously.
function aiRankScore(i) {
  const s = AI.stats[i];
  if (!s.n) return -Infinity;
  return s.sum / s.n - AI_RANK_Z * aiSlotStdErr(i); // aiSlotStdErr = Infinity for n<2 -> -Infinity
}
function computeAiOrder() {
  const champ = AI.order[0];
  const rest = AI.shortlist.map((_, i) => i).filter(i => i !== champ).sort((a, b) => {
    if (AI.visible[a] !== AI.visible[b]) return AI.visible[a] ? -1 : 1; // valid before invalid
    return aiRankScore(b) - aiRankScore(a);                             // higher lower-bound first
  });
  AI.order = [champ, ...rest];
}

// First place holds until another TRACKED lineup posts a strictly higher
// *simulated* average — not a rosier projection, an actual simulated result.
// The rule is deliberately simple: whoever has the most average points is #1.
// We keep hammering simulations at the reigning champion forever; it only loses
// first place the moment another lineup's running average edges above its own.
//
// The one guard: DK race scores are wildly high-variance (the SAME lineup can
// score ~40 one simulated race and ~300 the next), so a freshly-swapped-in
// candidate could post a flashy average off just a handful of lucky sims. To
// make sure "higher average" means a real average and not that fluke, a
// challenger must have at least AI_PROMOTE_MIN_SIMS sims of its own before it's
// allowed to take first. Past that bar, a plain average comparison decides it.
const AI_PROMOTE_MIN_SIMS = 3000; // min sims behind BOTH lineups before first place can change hands
// The champion's "fails the 5% bar" flag comes from a light 300-sim chances pass, so it flickers
// on noise even for a genuinely valid lineup. Two defenses against that flicker dethroning it:
//   1. When the champion looks invalid, re-verify with a big AI_CHAMP_RECHECK_SIMS pass before
//      trusting it — usually the light flag was just noise and the champion is really fine.
//   2. Even after a reliable re-check, only hand first place off once the champion has failed
//      AI_CHAMP_FAIL_LIMIT consecutive chances passes (AI.champFailStreak) — a genuinely invalid
//      lineup fails every time; a borderline one occasionally clears and resets the streak.
const AI_CHAMP_FAIL_LIMIT = 3;
const AI_CHAMP_RECHECK_SIMS = 2500;
// Standard error of a slot's mean simulated score (Infinity until it has >=2 sims).
function aiSlotStdErr(i) {
  const s = AI.stats[i];
  if (s.n < 2) return Infinity;
  const mean = s.sum / s.n;
  const variance = Math.max(0, (s.sumSq - s.n * mean * mean) / (s.n - 1));
  return Math.sqrt(variance / s.n);
}
function maybePromoteChampion() {
  if (AI.order.length < 2) return;
  const champ = AI.order[0];
  const champPasses = AI.visible[champ];

  // Case 1: the champion is INVALID (fails the 5% bar). An invalid lineup must
  // not hold first place — but only once we're sure it's really invalid, not just
  // showing a noisy sub-5% flicker this pass. Wait for AI_CHAMP_FAIL_LIMIT
  // consecutive failing chances passes (AI.champFailStreak). By the time we get
  // here performAiSwaps() has already tried to REPAIR the champion in place (swap
  // its sub-5% pick, keep the rest); if that worked the champion now passes and we
  // never reach this branch. We only hand off when no legal in-place repair exists:
  // hand first place to the best valid lineup available right now (highest
  // confidence bound). A lightly-sampled valid pick still beats a confirmed-invalid
  // one. (If nothing else is valid, the champion stays put — nothing valid to show.)
  if (!champPasses) {
    if (AI.champFailStreak < AI_CHAMP_FAIL_LIMIT) return; // give a noisy flicker the benefit of the doubt
    let handoff = -1, best = -Infinity;
    for (const i of AI.order) {
      if (i === champ || !AI.visible[i]) continue;
      const sc = aiRankScore(i);
      if (sc > best) { best = sc; handoff = i; }
    }
    if (handoff !== -1) {
      AI.order = [handoff, ...AI.order.filter(i => i !== handoff)];
      AI.champFailStreak = 0; // fresh champion, reset the counter
    }
    return;
  }

  // Case 2: the champion is valid — first place holds until another valid,
  // well-sampled lineup posts a strictly HIGHER simulated average. No confidence
  // margin, no minimum gap: whoever has the most average points is #1. We only
  // require the challenger to have >= AI_PROMOTE_MIN_SIMS sims of its own, so a
  // freshly-swapped-in candidate can't steal first on a handful of lucky sims —
  // its average has to be real before a plain comparison decides it.
  if (AI.stats[champ].n < AI_PROMOTE_MIN_SIMS) return; // don't judge a barely-sampled champ
  const avgOf = i => (AI.stats[i].n ? AI.stats[i].sum / AI.stats[i].n : -Infinity);
  let bestI = -1, bestAvg = -Infinity;
  for (const i of AI.order) {
    if (i === champ || !AI.visible[i] || AI.stats[i].n < AI_PROMOTE_MIN_SIMS) continue;
    if (avgOf(i) > bestAvg) { bestI = i; bestAvg = avgOf(i); }
  }
  if (bestI === -1) return;            // no eligible challenger yet
  if (bestAvg > avgOf(champ)) {        // strictly higher average -> take first place
    AI.order = [bestI, ...AI.order.filter(i => i !== bestI)]; // dethroned champ drops to rank 2
    AI.champFailStreak = 0; // fresh champion, reset the counter
  }
}
let aiCandidates = [];

const AI_TICK_BATCH = 150;
function aiTick() {
  for (let i = 0; i < AI.shortlist.length; i++) {
    const c = AI.shortlist[i];
    const s = AI.stats[i];
    for (let j = 0; j < AI_TICK_BATCH; j++) {
      const score = simulateCandidateScore(c, simulateRace());
      s.n++;
      s.sum += score;
      s.sumSq += score * score;
      if (score < s.min) s.min = score;
      if (score > s.max) s.max = score;
    }
  }
  AI.totalSims += AI.shortlist.length * AI_TICK_BATCH;
  renderAiResults();
}

// Renders whatever's currently in aiCandidates (does not recompute avg/min/max
// — callers that need fresh numbers from AI.stats do that before calling this).
function renderAiTable() {
  document.getElementById("ai-results-wrap").style.display = "";
  document.querySelector("#ai-results tbody").innerHTML = aiCandidates.map((c, i) => {
    const chancesCell = c.chances
      ? `${c.chances.total.toFixed(1)} pts best case<br>` +
        `<span style="color:var(--text-secondary)">${(c.chances.combinedProb * 100).toFixed(2)}% chance of this or better</span>` +
        (c.passes ? "" : `<br><span style="color:var(--critical)">⚠ needs a &lt;${(MIN_PICK_CHANCE * 100).toFixed(0)}% break from some pick</span>`)
      : `<span class="sub">—</span>`;
    return `<tr${c.passes ? "" : ' style="opacity:.6"'}>
    <td class="num">${i + 1}</td>
    <td>${byCode[c.cpt].name}</td>
    <td>${c.drivers.map(code => byCode[code].name).join(", ")}</td>
    <td>${byCid[c.constructor].name}</td>
    <td class="num">${fmt$(c.salaryUsed)}</td>
    <td class="num" style="font-weight:600">${c.avg.toFixed(1)}</td>
    <td class="num">${c.min.toFixed(0)}–${c.max.toFixed(0)}</td>
    <td class="num">${c.n.toLocaleString()}</td>
    <td style="font-size:12px">${chancesCell}</td>
    <td>${AI.running ? "" : `<button onclick="loadAiCandidate(${i})">Load</button>`}</td>
  </tr>`;
  }).join("");
}

// Nothing gets hidden — all AI_DISPLAY_SIZE = 20 tracked lineups are always
// shown, ordered by confidence (see computeAiOrder): valid lineups first, then
// by lower confidence bound, so well-proven lineups rise and lightly-sampled
// noisy ones sink until they earn their spot. Rank 1 is pinned to the reigning
// champion and only changes hands via maybePromoteChampion() — a confidence-
// gated test — never on a momentary crossing of the noisy running averages.
function renderAiResults() {
  maybePromoteChampion(); // let a proven-better lineup take rank 1 first
  computeAiOrder();       // then confidence-sort the rest beneath the champion
  const enriched = AI.shortlist.map((c, i) => ({ ...c, avg: AI.stats[i].sum / AI.stats[i].n,
    min: AI.stats[i].min, max: AI.stats[i].max, n: AI.stats[i].n, chances: AI.chances[i],
    passes: AI.visible[i] }));
  // DISPLAY ORDER. GUARANTEE: a lineup that fits the description always ranks
  // above every lineup that doesn't — even when the fitting lineup's average is
  // LOWER. So whenever at least one lineup fits, rank 1 ("number one") is a
  // fitting lineup, never a higher-average non-fitting one. Every lineup that
  // doesn't fit (invalid — some pick below the bar) is forced to the bottom.
  // computeAiOrder() already sorts the non-champion rows valid-before-invalid; the
  // one case it leaves an invalid lineup up top is a champion pinned at rank 1 that
  // has momentarily fallen below the bar. Partitioning here (valid rows keep their
  // ranked order, invalid rows fall beneath them) drops that invalid champion to
  // the bottom too. This is DISPLAY-ONLY — AI.order still tracks the champion
  // (order[0]) for the promotion/repair machinery, so once first place is repaired
  // back to valid it returns to the top of the table.
  const displayOrder = [
    ...AI.order.filter(i => AI.visible[i]),
    ...AI.order.filter(i => !AI.visible[i]),
  ];
  aiCandidates = displayOrder.map(i => enriched[i]);
  renderAiTable();
  const belowBarCount = aiCandidates.filter(c => !c.passes).length;
  const countNote = belowBarCount
    ? ` ${belowBarCount} of ${aiCandidates.length} currently need an almost-impossible ` +
      `(<${(MIN_PICK_CHANCE * 100).toFixed(0)}%) result from some pick — sorted to the bottom, ` +
      `not hidden.`
    : "";
  const swapNote = AI.filteredOutCount
    ? ` Swapped in ${AI.filteredOutCount} fresh candidate${AI.filteredOutCount === 1 ? "" : "s"} this pass.`
    : "";
  const fitCount = aiCandidates.length - belowBarCount;
  const phaseNote = AI.running
    ? (fitCount <= AI_OPTIMIZE_MIN_FIT
        ? ` Filling: ${fitCount}/${aiCandidates.length} lineups fit the description (locked in) — need more than ${AI_OPTIMIZE_MIN_FIT} before optimizing.`
        : ` ${fitCount}/${aiCandidates.length} lineups fit the description (more than ${AI_OPTIMIZE_MIN_FIT}) — now upgrading the weakest toward the best.`)
    : "";
  document.getElementById("ai-status").textContent = AI.running
    ? `Simulating ${AI.shortlist.length} candidate lineups continuously — ` +
      `${AI.totalSims.toLocaleString()} total simulations so far.${phaseNote}${countNote}${swapNote} ` +
      `Click Stop when you've seen enough.`
    : `Stopped after ${AI.totalSims.toLocaleString()} total simulations.${countNote}${swapNote}`;
}

// Runs a dedicated chances analysis (same engine as The Chances tab) for
// every candidate currently in AI.shortlist, marks any whose best-case
// outcome needs an almost-impossible (<5% solo chance) result from some
// pick or the constructor as not-visible, then hands off to
// performAiSwaps() to replace weak slots from the reserve pool — the
// displayed count always stays at 20, nothing just disappears. Runs on two
// cadences: a light/fast pass every few seconds while running (so the list
// keeps improving live, not just at the end), and one precise, full-size
// pass on Stop.
// The viability bar every pick must clear: a lineup is only "valid" (shown above
// the invalid ones, allowed to hold first place) when EVERY driver and the
// constructor has at least this solo chance of its best-case break. Driven live
// by the "Min pick chance" dropdown next to the AI Simulation title — raise it and
// the next chances pass repairs/swaps any lineup (the champion included) whose
// weakest pick now falls short, so first place always has every pick above the bar.
let MIN_PICK_CHANCE = 0.05;
function updateAiChances(simsPerCandidate) {
  const prevFit = AI.visible.slice(); // whether each slot fit the description last pass
  for (let i = 0; i < AI.shortlist.length; i++) {
    const chances = analyzeTopLineupChances(AI.shortlist[i], simsPerCandidate);
    AI.chances[i] = chances;
    const probs = [...chances.picks.map(p => p.prob), chances.constructor.prob];
    let fits = probs.every(p => p >= MIN_PICK_CHANCE);
    // FLICKER GUARD — the fix for fitting lineups disappearing. A lineup that
    // ALREADY fits the description must never be thrown away over one noisy pass
    // (see doc/ai-simulation-requirements.md: fitting lineups are kept, not
    // deleted/swapped). So if a slot fit last pass but this light 300-sim estimate
    // reads sub-bar, re-verify it with a much bigger, more reliable chances pass
    // before believing it. Only a CONFIRMED failure is allowed to mark it
    // not-fitting — which is the only thing that lets performAiSwaps() repair or
    // replace it. This is the same protection the champion always had, now every
    // fitting lineup gets it, so none vanishes on measurement noise.
    if (!fits && prevFit[i]) {
      const rc = analyzeTopLineupChances(AI.shortlist[i], AI_CHAMP_RECHECK_SIMS);
      AI.chances[i] = rc;
      const rprobs = [...rc.picks.map(p => p.prob), rc.constructor.prob];
      fits = rprobs.every(p => p >= MIN_PICK_CHANCE);
    }
    AI.visible[i] = fits;
  }
  // Champion fail-streak for maybePromoteChampion()'s debounce. The champion's fit
  // flag is already flicker-guarded above whenever it fit last pass; the only gap
  // is a champion freshly installed this session and NOT fitting last pass, so
  // re-verify that one case here too before its dethrone clock starts on noise.
  const champ = AI.order[0];
  if (champ != null && AI.visible[champ] === false && !prevFit[champ]) {
    const cc = analyzeTopLineupChances(AI.shortlist[champ], AI_CHAMP_RECHECK_SIMS);
    AI.chances[champ] = cc;
    const probs = [...cc.picks.map(p => p.prob), cc.constructor.prob];
    AI.visible[champ] = probs.every(p => p >= MIN_PICK_CHANCE);
  }
  if (champ != null && AI.visible[champ] === false) AI.champFailStreak++;
  else AI.champFailStreak = 0;
  performAiSwaps();
  renderAiResults();
}

// Keeps the displayed 20 at a constant count while continuously improving
// it: any slot that's either failing the 5% chance filter, or whose
// simulated avg has fallen below the next-best untried reserve candidate's
// projected value, gets evicted and replaced. The replacement is seeded
// with an immediate batch of sims + a chances check so it isn't shown blank
// for a tick. Reserve is pre-sorted by projection (from
// findTopCandidatesByProjection), so `.shift()` always pulls the best
// remaining untried candidate.
// Swaps candidate.chances[i]'s worst-performing pick (lowest solo chance —
// driver or constructor) for the strongest legal alternative not already in
// the lineup, keeping everything else the same: same captain/drivers/
// constructor except the one problem slot. Returns a new candidate object,
// or null if no legal (cap-fitting, DK same-team-rule-legal) replacement
// exists for that slot. This is a repair, not a fresh pick — .proj is
// carried over from the original as an approximation rather than
// recomputed, since it's only used as a rough ordering hint elsewhere.
function repairFailingLineup(candidate, chances) {
  const entries = chances.picks.map(p => ({ code: p.code, role: p.role, prob: p.prob, isDriver: true }));
  entries.push({ code: candidate.constructor, role: "CNSTR", prob: chances.constructor.prob, isDriver: false });
  entries.sort((a, b) => a.prob - b.prob);
  const worst = entries[0];
  const currentDriverCodes = [candidate.cpt, ...candidate.drivers];

  if (!worst.isDriver) {
    const driverSalaryTotal = byCode[candidate.cpt].salaryCpt +
      candidate.drivers.reduce((s, c) => s + byCode[c].salary, 0);
    const budget = CAP - driverSalaryTotal;
    const alt = D.constructors.find(c => {
      if (c.id === candidate.constructor || c.salary > budget) return false;
      const sameTeam = currentDriverCodes.filter(code => byCode[code].team === c.id).length;
      return sameTeam < 2;
    });
    if (!alt) return null;
    return {
      cpt: candidate.cpt, drivers: [...candidate.drivers], constructor: alt.id,
      salaryUsed: driverSalaryTotal + alt.salary, proj: candidate.proj,
    };
  }

  const isCpt = worst.role === "CPT";
  const otherDriverCodes = currentDriverCodes.filter(c => c !== worst.code);
  const otherSalary = otherDriverCodes.reduce((s, c) =>
    s + (c === candidate.cpt ? byCode[c].salaryCpt : byCode[c].salary), 0);
  const budget = CAP - byCid[candidate.constructor].salary - otherSalary;
  const alt = D.drivers
    .filter(d => !currentDriverCodes.includes(d.code))
    .sort((a, b) => b.avgDk - a.avgDk)
    .find(d => {
      const slotSalary = isCpt ? d.salaryCpt : d.salary;
      if (slotSalary > budget) return false;
      const newTeams = [...otherDriverCodes.map(c => byCode[c].team), d.team];
      return newTeams.filter(t => t === candidate.constructor).length < 2;
    });
  if (!alt) return null;

  const newCpt = isCpt ? alt.code : candidate.cpt;
  const newDrivers = isCpt ? candidate.drivers : candidate.drivers.map(c => c === worst.code ? alt.code : c);
  const newSalary = (isCpt ? alt.salaryCpt : byCode[newCpt].salaryCpt) +
    newDrivers.reduce((s, c) => s + byCode[c].salary, 0) + byCid[candidate.constructor].salary;
  return { cpt: newCpt, drivers: newDrivers, constructor: candidate.constructor, salaryUsed: newSalary, proj: candidate.proj };
}

// Re-simulates + re-checks chances for whatever candidate now occupies slot
// i (freshly repaired or freshly pulled from reserve), so it's never shown
// blank/stale for a tick.
function seedAiSlot(i, incoming) {
  AI.shortlist[i] = incoming;
  const s = { n: 0, sum: 0, sumSq: 0, min: Infinity, max: -Infinity };
  for (let j = 0; j < AI_TICK_BATCH; j++) {
    const score = simulateCandidateScore(incoming, simulateRace());
    s.n++; s.sum += score; s.sumSq += score * score;
    if (score < s.min) s.min = score;
    if (score > s.max) s.max = score;
  }
  AI.stats[i] = s;
  const chances = analyzeTopLineupChances(incoming, AI_LIVE_CHANCES_SIMS);
  AI.chances[i] = chances;
  const probs = [...chances.picks.map(p => p.prob), chances.constructor.prob];
  AI.visible[i] = probs.every(p => p >= MIN_PICK_CHANCE);
}

// For a slot currently failing the bar, first tries to repair it in place
// (swap just its worst pick, keep the rest — see repairFailingLineup()) rather
// than throwing the whole lineup out for an unrelated one from reserve. Reserve
// is only used as a fallback when no legal in-place repair exists — or, ONCE MORE
// THAN AI_OPTIMIZE_MIN_FIT (10) slots fit the description, to opportunistically
// upgrade an already-fitting slot whose avg has fallen behind the best untried
// reserve pick. That upgrade path is gated on the fill phase (canOptimize): until
// more than 10 lineups fit, every fitting lineup is left untouched.
function performAiSwaps() {
  const changedSlots = [];
  const champion = AI.order[0]; // the reigning first-place lineup — never evicted for an unproven reserve pick
  // Two phases. FILLING: until MORE THAN AI_OPTIMIZE_MIN_FIT (10) slots hold a
  // lineup that fits the description (clears the Min-pick-chance bar), every
  // lineup that already fits is locked in place and never changed — we only ever
  // work the slots that don't yet fit. OPTIMIZING: once more than 10 fit, we
  // start upgrading the weakest fitting slots toward the best. If enough later
  // drop below the bar, canOptimize goes false again and we pause upgrading to
  // go re-fill first.
  const fitCount = AI.visible.filter(Boolean).length;
  const canOptimize = fitCount > AI_OPTIMIZE_MIN_FIT;
  const worstFirst = AI.shortlist.map((_, i) => i).sort((a, b) => {
    if (AI.visible[a] !== AI.visible[b]) return AI.visible[a] ? 1 : -1; // not-visible = worst
    const avgA = AI.stats[a].n ? AI.stats[a].sum / AI.stats[a].n : -Infinity;
    const avgB = AI.stats[b].n ? AI.stats[b].sum / AI.stats[b].n : -Infinity;
    return avgA - avgB;
  });
  for (const i of worstFirst) {
    // The reigning first-place slot is normally left completely untouched so it
    // keeps piling up sims — never evicted for an unproven reserve upgrade, and
    // not reseeded on a noisy one-pass 5%-bar flicker (that would wipe its sims
    // and knock it out of first). The ONE exception: if first place genuinely has
    // a pick below the 5% bar, a sub-5% driver/constructor shouldn't sit at rank 1,
    // so we try to change the lineup so it fits. Only once the failure is confirmed
    // (AI_CHAMP_FAIL_LIMIT consecutive fails — the same debounce Case 1 uses, not a
    // lone flicker) we repair it IN PLACE: swap just the offending pick, keep the
    // rest, and the fixed lineup stays champion. If no legal in-place repair exists
    // we leave it intact for maybePromoteChampion() to hand first place to another
    // valid lineup. We never evict the champion to an unproven reserve pick.
    if (i === champion) {
      if (!AI.visible[i] && AI.champFailStreak >= AI_CHAMP_FAIL_LIMIT) {
        const repaired = repairFailingLineup(AI.shortlist[i], AI.chances[i]);
        if (repaired) {
          seedAiSlot(i, repaired);
          changedSlots.push(i);
          AI.champFailStreak = 0; // fixed lineup, fresh start — no longer a failing champ
        }
      }
      continue;
    }
    if (!AI.visible[i]) {
      const repaired = repairFailingLineup(AI.shortlist[i], AI.chances[i]);
      if (repaired) {
        seedAiSlot(i, repaired);
        changedSlots.push(i);
        continue;
      }
      if (AI.reserve.length) {
        seedAiSlot(i, AI.reserve.shift());
        changedSlots.push(i);
      }
      continue;
    }
    // This slot already fits the description. Leave it alone until more than 10
    // fit — only then do we upgrade the weakest fitting slots toward the best.
    if (!canOptimize) continue;
    if (!AI.reserve.length) continue;
    const avg = AI.stats[i].n ? AI.stats[i].sum / AI.stats[i].n : -Infinity;
    if (AI.reserve[0].proj > avg) {
      seedAiSlot(i, AI.reserve.shift());
      changedSlots.push(i);
    }
  }
  AI.filteredOutCount = changedSlots.length;
  // No manual reordering here: the next renderAiResults() recomputes the whole
  // confidence order (computeAiOrder), so any slot that just got a fresh lineup
  // lands wherever its (initially wide) confidence bound puts it — near the
  // bottom until it accumulates sims.
}

function loadAiCandidate(i) {
  const c = aiCandidates[i];
  lineup.cpt = c.cpt;
  lineup.drivers = [...c.drivers];
  lineup.constructor = c.constructor;
  render();
  showChancesForCandidate(c);
}

const AI_DISPLAY_SIZE = 20;         // always exactly this many lineups shown
const AI_OPTIMIZE_MIN_FIT = 10;     // keep fitting lineups locked until MORE THAN this many fit, then start upgrading
const AI_POOL_SIZE = 200;           // extra 180 held in reserve to swap in as needed
const AI_LIVE_CHANCES_SIMS = 300;   // light pass, re-run every few seconds while running
const AI_FINAL_CHANCES_SIMS = 1000; // precise pass, run once on Stop

function startAiSimulation() {
  if (AI.running) return;
  AI.running = true;
  document.getElementById("ai-start-btn").disabled = true;
  document.getElementById("ai-stop-btn").disabled = false;
  document.getElementById("ai-min-chance").disabled = true; // locked while running — only editable when stopped
  document.getElementById("ai-status").textContent = "Searching legal combinations…";
  setTimeout(() => {
    const pool = findTopCandidatesByProjection(AI_POOL_SIZE);
    AI.shortlist = pool.slice(0, AI_DISPLAY_SIZE);
    AI.reserve = pool.slice(AI_DISPLAY_SIZE);
    AI.stats = AI.shortlist.map(() => ({ n: 0, sum: 0, sumSq: 0, min: Infinity, max: -Infinity }));
    AI.chances = AI.shortlist.map(() => null);
    AI.visible = AI.shortlist.map(() => true); // reassessed by the first chances pass
    AI.order = AI.shortlist.map((_, i) => i); // pool is already projection-sorted
    AI.totalSims = 0;
    AI.filteredOutCount = 0;
    AI.champFailStreak = 0;
    aiTick();
    AI.timer = setInterval(aiTick, 400);
    updateAiChances(AI_LIVE_CHANCES_SIMS);
    AI.chancesTimer = setInterval(() => updateAiChances(AI_LIVE_CHANCES_SIMS), 2000);
  }, 10);
}

function stopAiSimulation() {
  if (!AI.running) return;
  AI.running = false;
  clearInterval(AI.timer);
  AI.timer = null;
  clearInterval(AI.chancesTimer);
  AI.chancesTimer = null;
  document.getElementById("ai-start-btn").disabled = false;
  document.getElementById("ai-stop-btn").disabled = true;
  document.getElementById("ai-min-chance").disabled = false; // stopped — the bar can be changed again
  document.getElementById("ai-status").textContent =
    `Stopped after ${AI.totalSims.toLocaleString()} total simulations — computing final chances for each lineup…`;
  setTimeout(() => {
    updateAiChances(AI_FINAL_CHANCES_SIMS);
  }, 10);
}

// ---------- Driver's Qualifying (real grid entry) ----------
// Applies grid penalties on top of a qualifying order the same way real F1
// penalties work: a penalized driver's target rank is qualPos + penalty
// places; ties (including a non-penalized driver landing on the same target
// rank as a penalized one) are broken by original qualifying order via
// Array.sort's stability.
