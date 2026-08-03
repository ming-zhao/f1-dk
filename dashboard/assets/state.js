// Lineup state, salary cap maths, DK roster rules, street-circuit config.
"use strict";
const D = F1DATA;
const CAP = D.salaryCap;
const CPT_MULT = D.captainMultiplier;
const SC_D = D.scoring.driver;
const SC_C = D.scoring.constructor;
const TOTAL_LAPS = D.totalLaps;

// ---------- street-circuit modeling ----------
// A "street circuit" is really two independent effects (see doc/simulation-
// technical.md, Method 2): (1) wGrid — how tightly finishing order tracks the
// starting grid, i.e. how hard it is to overtake, which is PER-CIRCUIT, not a
// blanket street trait; and (2) walls with no run-off -> higher DNF rate plus a
// likely safety car that can collect several cars at once, which every street
// circuit shares. Keyed off the race name so it switches itself ON automatically
// whenever the dashboard is rebuilt for one of these races and stays OFF (a pure
// no-op — see simulateRace) everywhere else. Add a race here to extend the list.
const STREET_CIRCUITS = {
  "Monaco Grand Prix":        { wGrid: 0.80, pSC: 0.90, dnfFactor: 1.5 }, // ~10-12 overtakes/race, grid ≈ finish
  "Singapore Grand Prix":     { wGrid: 0.68, pSC: 0.95, dnfFactor: 1.7 }, // SC in every race 2008-2023, high attrition
  "Azerbaijan Grand Prix":    { wGrid: 0.42, pSC: 0.55, dnfFactor: 1.5 }, // Baku: long straight -> lots of passing despite walls
  "Las Vegas Grand Prix":     { wGrid: 0.42, pSC: 0.55, dnfFactor: 1.4 }, // ~60-82 overtakes/race
  "Saudi Arabian Grand Prix": { wGrid: 0.45, pSC: 0.65, dnfFactor: 1.6 }, // Jeddah Corniche: very fast street circuit
};
// Match ignoring any trailing year ("Monaco Grand Prix 2026" -> "Monaco Grand Prix").
const STREET_CFG = (() => {
  const name = Object.keys(STREET_CIRCUITS).find(k => D.raceName.includes(k));
  return name ? { name, ...STREET_CIRCUITS[name] } : null;
})();
const IS_STREET = STREET_CFG !== null;

const TEAM_NAMES = Object.fromEntries(
  D.constructors.map(c => [c.id, c.shortName || c.name]));

// ---------- state ----------
const lineup = { cpt: null, drivers: [], constructor: null }; // codes / constructor id
let simCount = 0;
const sortState = {
  pool: { key: "salaryCpt", asc: false },
  cpool: { key: "salary", asc: false },
};

const byCode = Object.fromEntries(D.drivers.map(d => [d.code, d]));
const byCid = Object.fromEntries(D.constructors.map(c => [c.id, c]));

// Driver's Qualifying: manually-entered real grid, overriding simulated
// qualifying everywhere once applied. qualiOrder defaults to the predicted
// order (by avgGrid) until the real classification is entered.
let qualiOrder = [...D.drivers].sort((a, b) => a.avgGrid - b.avgGrid).map(d => d.code);
const qualiPenalties = {}; // code -> penalty places
let fixedGrid = null; // null = simulated qualifying; else {code: gridPos}

// ---------- lineup logic ----------
function salaryUsed() {
  let s = 0;
  if (lineup.cpt) s += byCode[lineup.cpt].salaryCpt;
  for (const c of lineup.drivers) s += byCode[c].salary;
  if (lineup.constructor) s += byCid[lineup.constructor].salary;
  return s;
}
function lineupErrors() {
  const errs = [];
  const used = salaryUsed();
  if (used > CAP) errs.push(`Over the cap by $${(used - CAP).toLocaleString()}.`);
  // DK rule: cannot roster 2 drivers AND the constructor from the same team
  if (lineup.constructor) {
    const all = [lineup.cpt, ...lineup.drivers].filter(Boolean);
    const sameTeam = all.filter(c => byCode[c].team === lineup.constructor);
    if (sameTeam.length >= 2) {
      errs.push(`DK rule: can't take 2 drivers AND the constructor from the same team (${byCid[lineup.constructor].name}).`);
    }
  }
  return errs;
}
function isComplete() {
  return lineup.cpt && lineup.drivers.length === 4 && lineup.constructor;
}
function inLineup(code) {
  return lineup.cpt === code || lineup.drivers.includes(code);
}
function addDriver(code, asCpt) {
  if (inLineup(code)) return;
  if (asCpt) { if (lineup.cpt) return; lineup.cpt = code; }
  else { if (lineup.drivers.length >= 4) return; lineup.drivers.push(code); }
  render();
}
function remove(code) {
  if (lineup.cpt === code) lineup.cpt = null;
  else if (code === lineup.constructor) lineup.constructor = null;
  else lineup.drivers = lineup.drivers.filter(c => c !== code);
  render();
}
function clearLineup() {
  lineup.cpt = null;
  lineup.drivers = [];
  lineup.constructor = null;
  render();
}

// ---------- rendering ----------
function fmt$(n) { return "$" + n.toLocaleString(); }
function teamDot(team) {
  return `<img class="team-logo" src="logos/${team}.png" alt="${TEAM_NAMES[team] || team}" title="${TEAM_NAMES[team] || team}">`;
}
