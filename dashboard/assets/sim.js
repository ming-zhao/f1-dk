// One random race outcome + DK scoring of it.
function gauss() { // Box-Muller
  let u = 0, v = 0;
  while (u === 0) u = Math.random();
  while (v === 0) v = Math.random();
  return Math.sqrt(-2 * Math.log(u)) * Math.cos(2 * Math.PI * v);
}

function simulateRace() {
  // 1) qualifying: use the manually entered real grid (Driver's Qualifying box)
  // if one has been applied, otherwise sample a grid score per driver from
  // their historical avgGrid/stdGrid and rank -> grid 1..22.
  let field;
  if (fixedGrid) {
    field = D.drivers.map(d => ({ ...d, grid: fixedGrid[d.code] }));
  } else {
    field = D.drivers.map(d => ({ ...d, gridScore: d.avgGrid + gauss() * d.stdGrid }));
    field.sort((a, b) => a.gridScore - b.gridScore);
    field.forEach((d, i) => d.grid = i + 1);
  }

  // 2) race: DNF rolls, then a pace score correlated with grid + form.
  // Street circuits (STREET_CFG, set by race name) change two things here —
  // knob 1: wGrid, how tightly finish tracks the grid (overtaking difficulty,
  // per-circuit); knob 2: a higher DNF rate plus a possible safety car that can
  // collect several cars at once. Off every other track wGrid=0.45 / dnfMult=1
  // / safetyCar=false, so this stays byte-identical to the original model.
  const wGrid = STREET_CFG ? STREET_CFG.wGrid : 0.45;
  const dnfMult = STREET_CFG ? STREET_CFG.dnfFactor : 1;
  const safetyCar = STREET_CFG ? Math.random() < STREET_CFG.pSC : false;
  for (const d of field) {
    d.dnf = Math.random() < Math.min(0.95, d.dnfRate * dnfMult);
    d.paceScore = wGrid * d.grid + (1 - wGrid) * (d.avgFinish + gauss() * d.stdFinish);
    d.lapsDone = d.dnf
      ? Math.floor(Math.random() * TOTAL_LAPS * 0.88)
      : TOTAL_LAPS;
  }
  // Correlated safety-car incident: a first-lap/restart pile-up that takes out
  // 1-3 still-running cars at once (the multi-car crash independent coin-flips
  // can't produce), biased toward cars starting further back. Then bunch the
  // field — a safety car opens a cheap-pit-stop lottery, so add extra finishing
  // noise that can shuffle track position on the restart.
  if (safetyCar) {
    const pileupPool = field.filter(d => !d.dnf && d.grid >= 5);
    if (field.filter(d => !d.dnf).length > 6) {
      const nCollected = 1 + Math.floor(Math.random() * 3); // 1..3
      for (let k = 0; k < nCollected && pileupPool.length; k++) {
        const victim = pileupPool.splice(Math.floor(Math.pow(Math.random(), 0.7) * pileupPool.length), 1)[0];
        victim.dnf = true;
        victim.lapsDone = Math.floor(Math.random() * TOTAL_LAPS * 0.7);
      }
    }
    for (const d of field) if (!d.dnf) d.paceScore += gauss() * 2.5;
  }
  const finishers = field.filter(d => !d.dnf).sort((a, b) => a.paceScore - b.paceScore);
  const dnfs = field.filter(d => d.dnf).sort((a, b) => b.lapsDone - a.lapsDone);
  const order = [...finishers, ...dnfs];
  order.forEach((d, i) => d.finish = i + 1);

  // 3) laps led: winner leads most, front-runners split the rest. On sticky
  // (high-wGrid) street tracks the leader controls even more of the race.
  const leaderLo = STREET_CFG ? Math.min(0.60, 0.45 + (STREET_CFG.wGrid - 0.45)) : 0.45;
  const leaderSpan = STREET_CFG ? 0.30 : 0.35;
  const lead = { [order[0].code]: Math.round(TOTAL_LAPS * (leaderLo + Math.random() * leaderSpan)) };
  let rest = TOTAL_LAPS - lead[order[0].code];
  for (const d of order.slice(1, 4)) {
    const take = Math.min(rest, Math.round(Math.random() * rest * 0.7));
    if (take > 0) lead[d.code] = take;
    rest -= take;
  }
  if (rest > 0) lead[order[0].code] += rest;

  // 4) fastest lap: random among top classified (widened to top 15 once a
  // safety car has scrambled strategy — a late cheap-stop softs runner can grab
  // it from further down the order).
  const flPool = order.filter(d => !d.dnf).slice(0, safetyCar ? 15 : 10);
  const flDriver = flPool[Math.floor(Math.random() * flPool.length)].code;

  return { order, lead, flDriver };
}

// ---------- DK scoring ----------
function scoreDriver(d, race) {
  const finishPts = SC_D.finishing_position[d.finish] ?? 0;
  const diffPts = (d.grid - d.finish) * SC_D.place_differential_per_position;
  const detail = {};
  if (race.flDriver === d.code) detail["Fastest lap"] = SC_D.fastest_lap;
  const led = race.lead[d.code] || 0;
  if (led > 0) detail[`Led ${led} laps`] = led * SC_D.laps_led_per_lap;
  if (d.lapsDone >= TOTAL_LAPS * 0.9) detail["Classified"] = SC_D.classified_finish;
  const mate = race.order.find(o => o.team === d.team && o.code !== d.code);
  if (mate && d.finish < mate.finish) detail["Beat teammate"] = SC_D.defeated_teammate;
  const bonus = Object.values(detail).reduce((s, v) => s + v, 0);
  return {
    finish: finishPts, diff: diffPts, bonus, bonusDetail: detail,
    total: finishPts + diffPts + bonus,
  };
}
function scoreConstructor(cid, race) {
  const cars = race.order.filter(d => d.team === cid);
  let finish = 0;
  for (const car of cars) finish += SC_C.finishing_position[car.finish] ?? 0;
  const detail = {};
  if (cars.some(c => c.code === race.flDriver)) detail["Fastest lap"] = SC_C.fastest_lap;
  const led = cars.reduce((s, c) => s + (race.lead[c.code] || 0), 0);
  if (led > 0) detail[`Led ${led} laps`] = led * SC_C.laps_led_per_lap;
  if (cars.length === 2 && cars.every(c => c.lapsDone >= TOTAL_LAPS * 0.9))
    detail["Both classified"] = SC_C.both_cars_classified;
  if (cars.length === 2 && cars.every(c => c.finish <= 10))
    detail["Both in points"] = SC_C.both_cars_in_points;
  if (cars.length === 2 && cars.every(c => c.finish <= 3))
    detail["Both on podium"] = SC_C.both_cars_on_podium;
  const bonus = Object.values(detail).reduce((s, v) => s + v, 0);
  return { finish, diff: 0, bonus, bonusDetail: detail, total: finish + bonus };
}

// ---------- auto simulation (lineup optimizer) ----------
function* fiveCombos(arr) {
  const n = arr.length;
  for (let a = 0; a < n; a++)
    for (let b = a + 1; b < n; b++)
      for (let c = b + 1; c < n; c++)
        for (let d = c + 1; d < n; d++)
          for (let e = d + 1; e < n; e++)
            yield [arr[a], arr[b], arr[c], arr[d], arr[e]];
}

// Search every legal (cap + same-team-rule) combo. Lineups are deduped by
// driver squad (the 5 people picked, regardless of who's captain) so the
// shortlist doesn't fill up with near-duplicates that only swap the
// constructor or captain — only the best-projected variant of each unique
// squad survives. Individual drivers can still reappear across different
// squads; only the exact same 5-person group is deduped.
//
// On top of that, the final shortlist is picked greedily (highest projection
// first) while capping how many times any one captain or constructor can
// appear (maxPerCpt / maxPerCons) — otherwise the single best-avgDk driver
// tends to be the optimal captain for nearly every squad, and the single
// best-value constructor for nearly every budget, so the list would read as
// "same captain/constructor, different drivers" instead of genuinely varied.
