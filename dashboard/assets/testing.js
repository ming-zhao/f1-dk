// Tab switching, and the Testing tab's historical backtest.
function switchTab(name) {
  for (const t of TABS) {
    document.getElementById(`tab-${t}`).style.display = t === name ? "" : "none";
    document.getElementById(`tab-${t}-btn`).classList.toggle("active", t === name);
  }
}

// ---------- Testing AI (backtest against a chosen past season) ----------
// Picks a lineup with today's rules/salaries (same search as Auto
// Simulation), then checks what it would have actually scored in every
// race of a chosen season we have real DK points for (D.raceHistory, from
// build_data.py). No fabricated money figures — real historical points
// only, compared against a cheap "field-average lineup" baseline for
// context.
const F1_FIRST_SEASON = 1950;
function populateTestingYearDropdown() {
  const sel = document.getElementById("testing-year-select");
  const availableYears = new Set(D.raceHistory.map(r => r.year));
  // Top of the list follows the DATA, not a literal. A hardcoded 2025 cap hid the
  // 2026 races already present in raceHistory, while the line above was deriving
  // the available set correctly right next to it.
  const lastSeason = Math.max(...availableYears, F1_FIRST_SEASON);
  const years = [];
  for (let y = lastSeason; y >= F1_FIRST_SEASON; y--) years.push(y);
  sel.innerHTML = years.map(y =>
    `<option value="${y}">${y}${availableYears.has(y) ? "" : " (no data fetched yet)"}</option>`
  ).join("");
  // default to the most recent season we actually have data for, else the latest year listed
  const defaultYear = years.find(y => availableYears.has(y)) || years[0];
  sel.value = String(defaultYear);
  showSeasonRaceList(true);
}

// Shows the selected season's Grand Prix calendar in order — a preview of
// what's in D.raceHistory for that year, plus a clickable dot per race so
// one can be picked out (testingSelectedRound). Selecting a race narrows
// Run test to just that one Grand Prix instead of the whole season.
let testingSelectedRound = null;
function showSeasonRaceList(resetSelection) {
  if (resetSelection) testingSelectedRound = null;
  const year = parseInt(document.getElementById("testing-year-select").value, 10);
  const races = D.raceHistory.filter(r => r.year === year).sort((a, b) => a.round - b.round);
  const container = document.getElementById("testing-season-races");
  if (!races.length) {
    container.innerHTML = `<div class="sub">No race data fetched for ${year} yet.</div>`;
    return;
  }
  container.innerHTML = `<div class="sub" style="margin-bottom:4px">${year} Grand Prix calendar (${races.length} races) — click a dot to select a race:</div>` +
    `<ul style="list-style:none;margin:0;padding:0">` +
    races.map(r => {
      const isSelected = testingSelectedRound === r.round;
      return `<li style="display:flex;align-items:center;gap:8px;padding:3px 0;cursor:pointer" onclick="selectTestingRace(${r.round})">
        <span class="testing-dot${isSelected ? " selected" : ""}"></span>
        <span${isSelected ? ' style="font-weight:600"' : ""}>Round ${r.round} — ${r.raceName}</span>
      </li>`;
    }).join("") +
    `</ul>`;
}

function selectTestingRace(round) {
  testingSelectedRound = testingSelectedRound === round ? null : round; // click again to deselect
  showSeasonRaceList(false);
}

function pickTestingLineup() {
  const shortlist = findTopCandidatesByProjection(20);
  const evaluated = shortlist.map(c => ({ ...c, ...evaluateCandidate(c, 500) }));
  evaluated.sort((a, b) => b.avg - a.avg);
  return evaluated[0];
}

function scoreLineupAtHistoricalRace(candidate, race) {
  const picks = [candidate.cpt, ...candidate.drivers];
  const hasAllDrivers = picks.every(code => race.drivers[code] !== undefined);
  const hasConstructor = race.constructors[candidate.constructor] !== undefined;
  if (!hasAllDrivers || !hasConstructor) return null;
  let score = race.drivers[candidate.cpt] * CPT_MULT;
  for (const code of candidate.drivers) score += race.drivers[code];
  score += race.constructors[candidate.constructor];
  return score;
}

function fieldAverageLineupScore(race) {
  const driverVals = Object.values(race.drivers);
  const consVals = Object.values(race.constructors);
  if (!driverVals.length || !consVals.length) return null;
  const avgD = driverVals.reduce((s, v) => s + v, 0) / driverVals.length;
  const avgC = consVals.reduce((s, v) => s + v, 0) / consVals.length;
  return avgD * CPT_MULT + avgD * 4 + avgC;
}

function runTestingAi() {
  const btn = document.getElementById("testing-run-btn");
  const status = document.getElementById("testing-status");
  const year = parseInt(document.getElementById("testing-year-select").value, 10);
  const seasonRaces = D.raceHistory.filter(r => r.year === year).sort((a, b) => a.round - b.round);

  if (!seasonRaces.length) {
    document.getElementById("testing-results").style.display = "none";
    status.textContent = `No race data fetched for ${year} yet. Run ` +
      `"python3 src/data/data_crawler.py ${year} --source jolpica" to backfill that ` +
      `season, then "python3 src/sim/dk_points.py" and "python3 dashboard/build_data.py".`;
    return;
  }

  // If a specific race is selected, forget that race's own results while
  // picking the lineup (the picker never looks at race outcomes anyway —
  // it only sees today's driver salaries/projections) and score against
  // just that one race once picked, instead of the whole season.
  const testRaces = testingSelectedRound === null
    ? seasonRaces
    : seasonRaces.filter(r => r.round === testingSelectedRound);
  const singleRace = testingSelectedRound !== null;
  const racesTotalLabel = document.querySelector('#testing-results .tile:nth-child(1) .label');
  racesTotalLabel.textContent = singleRace ? "Race tested" : "Races that season";

  btn.disabled = true;
  status.textContent = singleRace
    ? `Forgetting Round ${testingSelectedRound}'s result and picking a lineup using today's rules…`
    : "Picking today's best lineup…";
  setTimeout(() => {
    const candidate = pickTestingLineup();
    status.textContent = singleRace
      ? `Lineup picked without looking at it — revealing what actually happened at ${testRaces[0].raceName}…`
      : `Scoring it against every ${year} race we have real results for…`;
    setTimeout(() => {
      const rows = testRaces.map(race => {
        const score = scoreLineupAtHistoricalRace(candidate, race);
        const baseline = fieldAverageLineupScore(race);
        return { race, score, baseline };
      });
      const withData = rows.filter(r => r.score !== null);
      const avgScore = withData.length
        ? withData.reduce((s, r) => s + r.score, 0) / withData.length : null;
      const beatCount = withData.filter(r => r.score > r.baseline).length;

      document.getElementById("testing-races-total").textContent = rows.length;
      document.getElementById("testing-races-data").textContent = withData.length;
      document.getElementById("testing-avg-score").textContent =
        avgScore === null ? "–" : avgScore.toFixed(1);
      document.getElementById("testing-beat-rate").textContent = withData.length
        ? `${beatCount} / ${withData.length} (${(beatCount / withData.length * 100).toFixed(0)}%)`
        : "–";
      const pickRow = (role, name, teamId, salary, extra) =>
        `<tr>
          <td style="white-space:nowrap;color:var(--text-secondary);font-size:12px">${role}</td>
          <td>${teamDot(teamId)} ${name}${extra ? ` <span class="sub">${extra}</span>` : ""}</td>
          <td class="num">${fmt$(salary)}</td>
        </tr>`;
      const driverRows =
        pickRow("CPT", byCode[candidate.cpt].name, byCode[candidate.cpt].team, byCode[candidate.cpt].salaryCpt, "1.5× pts &amp; salary") +
        candidate.drivers.map(c => pickRow("Driver", byCode[c].name, byCode[c].team, byCode[c].salary, "")).join("") +
        pickRow("Constructor", byCid[candidate.constructor].name, candidate.constructor, byCid[candidate.constructor].salary, "");
      // How many real DK points this exact lineup actually scored in the tested race(s).
      let scoredLine;
      if (singleRace) {
        const r = rows[0];
        scoredLine = r.score === null
          ? `Actually scored: <b>N/A</b> — a pick wasn't in ${r.race.raceName}'s field.`
          : `Actually scored <b style="color:var(--good-text)">${r.score.toFixed(1)}</b> pts at the ${r.race.raceName} ` +
            `<span class="sub">(a typical lineup scored ${r.baseline.toFixed(1)})</span>`;
      } else {
        scoredLine = avgScore === null
          ? `Actually scored: <b>N/A</b> — no ${year} race had full data for every pick.`
          : `Actually scored <b style="color:var(--good-text)">${avgScore.toFixed(1)}</b> pts/race on average across ${withData.length} ${year} races ` +
            `<span class="sub">(beat a typical lineup in ${beatCount} of them)</span>`;
      }
      document.getElementById("testing-lineup-summary").innerHTML =
        `<div style="border:1px solid var(--border);border-radius:10px;padding:12px 14px;background:var(--surface-1)">
          <div style="font-weight:600;margin-bottom:2px">The lineup the AI picked</div>
          <div class="sub" style="margin-bottom:10px">
            Expected <b>${candidate.avg.toFixed(1)}</b> pts/race in today's sims ·
            ${fmt$(candidate.salaryUsed)} of ${fmt$(CAP)} cap used ·
            picked from today's salaries only, never from any race's result
          </div>
          <table style="width:100%"><tbody>${driverRows}</tbody></table>
          <div style="border-top:1px solid var(--border);margin-top:10px;padding-top:10px;font-size:15px">${scoredLine}</div>
        </div>`;

      document.querySelector("#testing-table tbody").innerHTML = rows.map(r => {
        const delta = r.score !== null && r.baseline !== null ? r.score - r.baseline : null;
        return `<tr>
          <td class="num">${r.race.round}</td>
          <td>${r.race.raceName}</td>
          <td class="num">${r.score === null ? "—" : r.score.toFixed(1)}</td>
          <td class="num">${r.baseline === null ? "—" : r.baseline.toFixed(1)}</td>
          <td class="num ${delta === null ? "" : delta > 0 ? "delta-up" : delta < 0 ? "delta-dn" : ""}">
            ${delta === null ? "N/A — driver(s) not in that race's field" :
              (delta > 0 ? "+" : "") + delta.toFixed(1)}
          </td>
        </tr>`;
      }).join("");

      document.getElementById("testing-results").style.display = "";
      if (singleRace) {
        const r = rows[0];
        status.textContent = r.score === null
          ? `${r.race.raceName}: N/A — this lineup includes a driver who wasn't in that race's field.`
          : `${r.race.raceName}: this lineup would have scored ${r.score.toFixed(1)} points ` +
            `(field-average lineup scored ${r.baseline.toFixed(1)}).`;
      } else {
        status.textContent = `Tested against ${rows.length} races from the ${year} season ` +
          `(${withData.length} had full data for every pick — the rest include a driver not in ` +
          `that race's field, e.g. a rookie or a team change).`;
      }
      btn.disabled = false;
    }, 10);
  }, 10);
}

// ---------- results rendering ----------
