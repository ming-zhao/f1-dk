// Per-pick probability analysis and its explanation.
function analyzeTopLineupChances(candidate, n) {
  const picks = [
    { role: "CPT", code: candidate.cpt, mult: CPT_MULT },
    ...candidate.drivers.map(code => ({ role: "D", code, mult: 1 })),
  ];
  const totalHistory = {}; // per pick: every simulated total (finish + all bonuses combined)
  picks.forEach(p => totalHistory[p.code] = []);
  const consTotalHistory = [];
  const scoreHistory = [];
  let best = null;

  for (let i = 0; i < n; i++) {
    const race = simulateRace();
    const pickResults = picks.map(p => {
      const d = race.order.find(x => x.code === p.code);
      const sc = scoreDriver(d, race);
      const total = sc.total * p.mult;
      totalHistory[p.code].push(total);
      return {
        role: p.role, code: p.code, name: d.name, finish: d.finish, grid: d.grid,
        dnf: d.dnf, bonusDetail: sc.bonusDetail, total,
      };
    });
    const cs = scoreConstructor(candidate.constructor, race);
    consTotalHistory.push(cs.total);
    const consResult = {
      name: byCid[candidate.constructor].name, bonusDetail: cs.bonusDetail, total: cs.total,
      cars: race.order.filter(d => d.team === candidate.constructor)
        .map(d => ({ name: d.name, finish: d.finish, dnf: d.dnf })),
    };
    const total = pickResults.reduce((s, p) => s + p.total, 0) + cs.total;
    scoreHistory.push(total);
    if (!best || total > best.total) best = { total, picks: pickResults, constructor: consResult };
  }

  // Solo probability = how often, across all n runs, that pick's own total
  // (finish points + every bonus combined) was at least as good as it was in
  // the best run — not just the finish position on its own. This is what
  // "Chance (solo)" actually reports, so it lines up with the finish +
  // bonuses shown for that pick, not one or the other in isolation.
  for (const p of best.picks) {
    p.prob = totalHistory[p.code].filter(v => v >= p.total).length / n;
  }
  best.constructor.prob = consTotalHistory.filter(v => v >= best.constructor.total).length / n;
  best.combinedProb = scoreHistory.filter(s => s >= best.total).length / n;
  best.n = n;
  return best;
}

// Plain-language explanation of *why* the combined percent came out the way
// it did: which requirement is the biggest bottleneck, and whether the real
// (correlated) combined chance ran higher or lower than naively multiplying
// every pick's solo chance together would predict.
function buildChancesExplanation(best) {
  const solo = [
    ...best.picks.map(p => ({ label: `${p.role === "CPT" ? "Captain " : ""}${p.name}`, prob: p.prob })),
    { label: `${best.constructor.name} (constructor)`, prob: best.constructor.prob },
  ];
  const sorted = [...solo].sort((a, b) => a.prob - b.prob);
  const bottleneck = sorted[0];
  const easiest = sorted[sorted.length - 1];

  const bottleneckLine = `The toughest single requirement is <b>${bottleneck.label}</b>, which only ` +
    `happens in <b>${(bottleneck.prob * 100).toFixed(1)}%</b> of simulations on its own — that's the ` +
    `biggest reason the full outcome is rare. The easiest part is <b>${easiest.label}</b> at ` +
    `${(easiest.prob * 100).toFixed(1)}%.`;

  const naiveProduct = solo.reduce((p, s) => p * s.prob, 1);
  let corrLine;
  if (naiveProduct <= 0) {
    corrLine = `Multiplying every pick's solo chance together would predict essentially a 0% chance of ` +
      `all of them lining up at once. The simulated combined chance came out to ` +
      `${(best.combinedProb * 100).toFixed(2)}% instead — real races don't treat each pick as an ` +
      `independent coin flip: qualifying and race pace are shared across the field, so a strong ` +
      `session tends to lift several of your picks at once, not just one.`;
  } else {
    const naivePct = naiveProduct * 100;
    const naiveStr = naivePct < 0.01 ? "under 0.01%" : naivePct.toFixed(2) + "%";
    const ratio = best.combinedProb / naiveProduct;
    const relation = ratio > 1.15 ? "notably higher than" : ratio < 0.85 ? "notably lower than" : "close to";
    corrLine = `If every pick's chance were independent, multiplying them all together would predict ` +
      `about ${naiveStr}. The simulated combined chance is ${(best.combinedProb * 100).toFixed(2)}%, ` +
      `which is ${relation} that naive estimate — picks aren't independent in the simulation (grid ` +
      `position, race pace, and DNFs are all drawn relative to the same field each run), so they tend ` +
      `to move together rather than each needing to beat the odds on its own.`;
  }

  const qualify = (prob) => prob >= 0.40 ? "a fairly ordinary result for them, nothing that needs luck"
    : prob >= 0.15 ? "a solidly good day, but well within their normal range"
    : "a real stretch — this is one of the less likely parts of the outcome";

  const pickLines = best.picks.map(p => {
    const stats = byCode[p.code];
    const bonusPart = Object.keys(p.bonusDetail || {}).length
      ? ` + ${Object.keys(p.bonusDetail).join(", ")}` : "";
    return `<li style="margin-bottom:6px"><b>${p.role === "CPT" ? "Captain " : ""}${p.name}</b> ` +
      `scored ${p.total.toFixed(1)} pts in this run (finish P${p.finish}${bonusPart}). Matching or ` +
      `beating that happens in <b>${(p.prob * 100).toFixed(1)}%</b> of the ${best.n.toLocaleString()} ` +
      `simulations for them — their underlying numbers are an average finish of P${stats.avgFinish.toFixed(1)} ` +
      `(±${stats.stdFinish.toFixed(1)}) from an average grid of P${stats.avgGrid.toFixed(1)}, with a ` +
      `${(stats.dnfRate * 100).toFixed(0)}% DNF rate — so this is ${qualify(p.prob)}.</li>`;
  });
  const c = best.constructor;
  const consBonusPart = Object.keys(c.bonusDetail || {}).length
    ? ` + ${Object.keys(c.bonusDetail).join(", ")}` : "";
  const consCarsPart = c.cars.map(car => `${car.name} P${car.finish}${car.dnf ? " (DNF)" : ""}`).join(", ");
  pickLines.push(`<li style="margin-bottom:6px"><b>${c.name}</b> (constructor) scored ` +
    `${c.total.toFixed(0)} pts in this run (${consCarsPart}${consBonusPart}). Matching or beating that ` +
    `happens in <b>${(c.prob * 100).toFixed(1)}%</b> of simulations for this team — ` +
    `${qualify(c.prob)}.</li>`);

  const perPickHeader = `<div class="sub" style="margin-top:12px;margin-bottom:4px">Per pick, in plain terms:</div>`;
  const perPickList = `<ul style="margin:0 0 0 18px;padding:0">${pickLines.join("")}</ul>`;

  return `<div class="sub">${bottleneckLine}</div><div class="sub" style="margin-top:8px">${corrLine}</div>` +
    perPickHeader + perPickList;
}

function renderChances(candidate, best) {
  document.getElementById("chances-intro").innerHTML =
    `Based on ${best.n.toLocaleString()} simulations of this lineup — ` +
    `<b>${byCode[candidate.cpt].name}</b> (CPT), ` +
    `${candidate.drivers.map(c => byCode[c].name).join(", ")}, ` +
    `<b>${byCid[candidate.constructor].name}</b> — here's the single highest-scoring outcome ` +
    `found, what it takes to get there, and how likely each part is.`;

  const rows = best.picks.map(p => {
    const bonusItems = Object.keys(p.bonusDetail || {}).join(", ") || "—";
    return `<tr>
      <td><span class="slot-tag ${p.role === "D" ? "d" : ""}">${p.role}</span>${p.name}${p.dnf ? ' <span class="dnf">DNF</span>' : ""}</td>
      <td>Finish P${p.finish} or better (grid P${p.grid})</td>
      <td style="font-size:12px;color:var(--text-secondary)">${bonusItems}</td>
      <td class="num" style="font-weight:600">${(p.prob * 100).toFixed(1)}%</td>
    </tr>`;
  }).join("");

  const c = best.constructor;
  const carsLine = c.cars.map(car => `${car.name} P${car.finish}${car.dnf ? " (DNF)" : ""}`).join(", ");
  const consBonusItems = Object.keys(c.bonusDetail || {}).join(", ") || "—";
  const consRow = `<tr>
    <td><span class="slot-tag c">CNSTR</span>${c.name}</td>
    <td>${carsLine} (${c.total.toFixed(0)}+ constructor pts)</td>
    <td style="font-size:12px;color:var(--text-secondary)">${consBonusItems}</td>
    <td class="num" style="font-weight:600">${(c.prob * 100).toFixed(1)}%</td>
  </tr>`;

  document.getElementById("chances-body").innerHTML = `
    <div class="tiles" style="grid-template-columns:repeat(2,1fr)">
      <div class="tile"><div class="label">Best-case score found</div><div class="value">${best.total.toFixed(1)}</div></div>
      <div class="tile"><div class="label">Chance of this outcome or better</div><div class="value">${(best.combinedProb * 100).toFixed(2)}%</div></div>
    </div>
    <table style="margin-top:14px">
      <thead><tr><th>Pick</th><th>What has to happen</th><th>Key bonuses in this run</th><th class="num">Chance (solo)</th></tr></thead>
      <tbody>${rows}${consRow}</tbody>
    </table>
    <div class="sub" style="margin-top:10px">"Chance (solo)" is how often that pick alone hits its required
      result across all ${best.n.toLocaleString()} simulations. "Chance of this outcome or better" is the
      combined probability of the whole lineup scoring at least this well in one race — picks aren't
      independent (grid and race pace are correlated across the field), so the solo chances don't simply
      multiply together into that number.</div>
  `;

  document.getElementById("chances-why-body").innerHTML = buildChancesExplanation(best);
}

let autoCandidates = [];
