// Candidate lineup enumeration and evaluation.
function findTopCandidatesByProjection(K, maxPerCpt = 5, maxPerCons = 5) {
  const bestBySquad = new Map();
  for (const cons of D.constructors) {
    const budget = CAP - cons.salary;
    if (budget < 0) continue;
    for (const five of fiveCombos(D.drivers)) {
      let sameTeam = 0;
      for (const dr of five) if (dr.team === cons.id) sameTeam++;
      if (sameTeam >= 2) continue;
      const squadKey = five.map(dr => dr.code).sort().join(",");
      for (let capIdx = 0; capIdx < 5; capIdx++) {
        const cpt = five[capIdx];
        let salary = cpt.salaryCpt;
        let proj = cpt.avgDk * CPT_MULT;
        let ok = true;
        for (let j = 0; j < 5; j++) {
          if (j === capIdx) continue;
          salary += five[j].salary;
          if (salary > budget) { ok = false; break; }
          proj += five[j].avgDk;
        }
        if (!ok) continue;
        const existing = bestBySquad.get(squadKey);
        if (!existing || proj > existing.proj) {
          bestBySquad.set(squadKey, {
            cpt: cpt.code,
            drivers: five.filter((_, j) => j !== capIdx).map(dr => dr.code),
            constructor: cons.id,
            salaryUsed: salary + cons.salary,
            proj,
          });
        }
      }
    }
  }

  const pool = [...bestBySquad.values()].sort((a, b) => b.proj - a.proj);
  const greedySelect = (capCpt, capCons) => {
    const picks = [];
    const cptCount = {}, consCount = {};
    for (const c of pool) {
      if (picks.length >= K) break;
      if ((cptCount[c.cpt] || 0) >= capCpt) continue;
      if ((consCount[c.constructor] || 0) >= capCons) continue;
      picks.push(c);
      cptCount[c.cpt] = (cptCount[c.cpt] || 0) + 1;
      consCount[c.constructor] = (consCount[c.constructor] || 0) + 1;
    }
    return picks;
  };
  // If the caps are too tight to fill K slots from the available pool (e.g. a
  // very small legal pool), relax them a little at a time rather than
  // dropping diversity entirely.
  let selected = greedySelect(maxPerCpt, maxPerCons);
  for (let relax = 1; selected.length < K && relax <= pool.length; relax++) {
    selected = greedySelect(maxPerCpt + relax, maxPerCons + relax);
  }
  return selected;
}

function simulateCandidateScore(candidate, race) {
  const cptD = race.order.find(d => d.code === candidate.cpt);
  let total = scoreDriver(cptD, race).total * CPT_MULT;
  for (const code of candidate.drivers) {
    total += scoreDriver(race.order.find(d => d.code === code), race).total;
  }
  total += scoreConstructor(candidate.constructor, race).total;
  return total;
}

function evaluateCandidate(candidate, n) {
  let sum = 0, min = Infinity, max = -Infinity;
  for (let i = 0; i < n; i++) {
    const s = simulateCandidateScore(candidate, simulateRace());
    sum += s;
    if (s < min) min = s;
    if (s > max) max = s;
  }
  return { avg: sum / n, min, max };
}

// Runs a dedicated batch of sims for one lineup, finds its single highest-
// scoring outcome, and — using the *same* batch — empirically estimates how
// often each pick alone hits its required result, and how often the whole
// lineup scores at least that well.
