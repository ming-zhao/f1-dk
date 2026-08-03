// Driver/constructor pool tables, lineup panel, race-intel notes.
function renderPool() {
  // Group teammates: order teams by their best driver on the sorted stat,
  // then sort the two drivers within each team by the same stat.
  const { key: sortKey, asc: sortAsc } = sortState.pool;
  const dir = sortAsc ? 1 : -1;
  const teamBest = {}, teamCount = {};
  for (const d of D.drivers) {
    const v = d[sortKey];
    if (!(d.team in teamBest) || (v - teamBest[d.team]) * dir < 0) teamBest[d.team] = v;
    teamCount[d.team] = (teamCount[d.team] || 0) + 1;
  }
  const rows = [...D.drivers].sort((a, b) => {
    if (a.team !== b.team) {
      if (teamBest[a.team] !== teamBest[b.team])
        return (teamBest[a.team] < teamBest[b.team] ? -1 : 1) * dir;
      return a.team < b.team ? -1 : 1;
    }
    return (a[sortKey] < b[sortKey] ? -1 : 1) * dir;
  });
  const left = CAP - salaryUsed();
  document.querySelector("#pool tbody").innerHTML = rows.map((d, i) => {
    const picked = inLineup(d.code);
    const cptOpen = !lineup.cpt, dOpen = lineup.drivers.length < 4;
    const cptAfford = d.salaryCpt <= left, dAfford = d.salary <= left;
    const cptDisabled = picked || !cptOpen || !cptAfford;
    const dDisabled = picked || !dOpen || !dAfford;
    // red = can't afford this driver in any slot that's still open
    const unaffordable = !picked &&
      (cptOpen || dOpen) &&
      !(cptOpen && cptAfford) && !(dOpen && dAfford);
    const newTeam = i === 0 || rows[i - 1].team !== d.team;
    const teamSpan = newTeam ? teamCount[d.team] : 0;
    const teamCell = newTeam
      ? `<td class="team-cell" rowspan="${teamSpan}">${teamDot(d.team)}${TEAM_NAMES[d.team] || d.team}</td>`
      : "";
    const rowCls = [i > 0 && newTeam ? "team-start" : "", unaffordable ? "no-afford" : ""]
      .filter(Boolean).join(" ");
    return `<tr${rowCls ? ` class="${rowCls}"` : ""}>
      ${teamCell}
      <td><span class="driver-name" onclick="showDriverModal('${d.code}')">${d.name}</span></td>
      <td class="num${!picked && cptOpen && !cptAfford ? " sal-over" : ""}">${fmt$(d.salaryCpt)}</td>
      <td class="num${!picked && dOpen && !dAfford ? " sal-over" : ""}">${fmt$(d.salary)}</td>
      <td style="white-space:nowrap">
        ${picked
          ? `<button class="ghost-x" onclick="remove('${d.code}')">✕ remove</button>`
          : `<button ${cptDisabled ? "disabled" : ""} onclick="addDriver('${d.code}',true)">CPT</button>
             <button ${dDisabled ? "disabled" : ""} onclick="addDriver('${d.code}',false)">D</button>`}
      </td>
    </tr>`;
  }).join("");

  const { key: cSortKey, asc: cSortAsc } = sortState.cpool;
  const crows = [...D.constructors].sort((a, b) =>
    (a[cSortKey] < b[cSortKey] ? -1 : 1) * (cSortAsc ? 1 : -1));
  document.querySelector("#cpool tbody").innerHTML = crows.map(c => {
    const picked = lineup.constructor === c.id;
    const cAfford = c.salary <= left;
    const unaff = !picked && !lineup.constructor && !cAfford;
    return `<tr${unaff ? ' class="no-afford"' : ""}>
      <td>${teamDot(c.id)}${c.name}</td>
      <td class="num${unaff ? " sal-over" : ""}">${fmt$(c.salary)}</td>
      <td class="num">${c.avgDk.toFixed(1)}</td>
      <td class="num">${c.maxDk.toFixed(0)}</td>
      <td class="num">${(c.bothPtsRate * 100).toFixed(0)}%</td>
      <td>${picked
        ? `<button class="ghost-x" onclick="remove(lineup.constructor)">✕ remove</button>`
        : `<button ${lineup.constructor || !cAfford ? "disabled" : ""} onclick="lineup.constructor='${c.id}';render()">CNSTR</button>`}</td>
    </tr>`;
  }).join("");
}
function renderLineup() {
  const slots = [];
  slots.push(lineup.cpt
    ? slotRow("CPT", "", byCode[lineup.cpt].name, byCode[lineup.cpt].salaryCpt, lineup.cpt)
    : emptyRow("CPT", "pick a captain"));
  for (let i = 0; i < 4; i++) {
    const c = lineup.drivers[i];
    slots.push(c
      ? slotRow("D", "d", byCode[c].name, byCode[c].salary, c)
      : emptyRow("D", "pick a driver", "d"));
  }
  slots.push(lineup.constructor
    ? slotRow("CNSTR", "c", byCid[lineup.constructor].name, byCid[lineup.constructor].salary, lineup.constructor)
    : emptyRow("CNSTR", "pick a constructor", "c"));
  document.getElementById("lineup-slots").innerHTML = slots.join("");

  const used = salaryUsed();
  const left = CAP - used;
  document.getElementById("sal-used").textContent = fmt$(used);
  const leftEl = document.getElementById("sal-left");
  leftEl.textContent = fmt$(left);
  leftEl.className = "value" + (left < 0 ? " over" : "");
  const meter = document.getElementById("sal-meter");
  meter.style.width = Math.min(100, used / CAP * 100) + "%";
  meter.className = used > CAP ? "over" : "";

  // projected: sum of avg DK pts (captain 1.5x), constructor rough proxy = 2x team drivers' avg finish pts share
  let proj = null;
  if (lineup.cpt || lineup.drivers.length) {
    proj = 0;
    if (lineup.cpt) proj += byCode[lineup.cpt].avgDk * CPT_MULT;
    for (const c of lineup.drivers) proj += byCode[c].avgDk;
    if (lineup.constructor) {
      const teamDrivers = D.drivers.filter(d => d.team === lineup.constructor);
      proj += teamDrivers.reduce((s, d) => s + d.avgDk, 0) * 0.9; // rough constructor proxy
    }
  }
  document.getElementById("proj-pts").textContent = proj === null ? "–" : proj.toFixed(0);

  const errs = lineupErrors();
  document.getElementById("lineup-warn").innerHTML =
    errs.map(e => `<div class="warn">⚠ ${e}</div>`).join("");
  document.getElementById("sim-btn").disabled = !(isComplete() && errs.length === 0);
  document.getElementById("clear-btn").disabled =
    !(lineup.cpt || lineup.drivers.length || lineup.constructor);
}
function slotRow(tag, cls, name, sal, code) {
  return `<div class="lineup-row">
    <span class="slot-tag ${cls}">${tag}</span>
    <span class="nm">${name}</span>
    <span class="sal">${fmt$(sal)}</span><button class="ghost-x" onclick="remove('${code}')">✕</button>
  </div>`;
}
function emptyRow(tag, label, cls = "") {
  return `<div class="lineup-row">
    <span class="slot-tag ${cls}">${tag}</span>
    <span class="nm empty-slot">${label}</span>
  </div>`;
}

function render() { renderPool(); renderLineup(); }

// ---------- tyre plans ----------
function renderTyrePlans() {
  const plans = (D.raceNotes && D.raceNotes.tyre_plans) || {};
  const container = document.getElementById("tyre-plans");
  const hasAny = Object.values(plans).some(notes => (notes || []).length > 0);
  if (!hasAny) {
    container.innerHTML = `<div class="sub">No tyre plan info yet for this race. Add it to
      <code>config/race_notes.yaml</code> under <code>tyre_plans</code>, then rebuild
      (<code>python3 dashboard/build_data.py</code>).</div>`;
    return;
  }
  container.innerHTML = D.constructors.map(c => {
    const notes = plans[c.id] || [];
    const body = notes.length
      ? `<ul style="margin:4px 0 0 18px;padding:0">${notes.map(n => `<li style="margin-bottom:2px">${n}</li>`).join("")}</ul>`
      : `<div class="sub" style="margin-top:2px">No plan yet</div>`;
    return `<div style="padding:8px 0;border-bottom:1px solid var(--grid-line)">
      <div style="font-weight:600">${teamDot(c.id)}${c.shortName || c.name}</div>
      ${body}
    </div>`;
  }).join("");
}

// ---------- driver performance ----------
function renderDriverPerformance() {
  const perf = (D.raceNotes && D.raceNotes.driver_performance) || {};
  const container = document.getElementById("driver-performance");
  const hasAny = Object.values(perf).some(notes => (notes || []).length > 0);
  if (!hasAny) {
    container.innerHTML = `<div class="sub">No practice performance notes yet for this race. Add it to
      <code>config/race_notes.yaml</code> under <code>driver_performance</code>, then rebuild
      (<code>python3 dashboard/build_data.py</code>).</div>`;
    return;
  }
  container.innerHTML = D.drivers.map(d => {
    const notes = perf[d.code] || [];
    const body = notes.length
      ? `<ul style="margin:4px 0 0 18px;padding:0">${notes.map(n => `<li style="margin-bottom:2px">${n}</li>`).join("")}</ul>`
      : `<div class="sub" style="margin-top:2px">No notes yet</div>`;
    return `<div style="padding:8px 0;border-bottom:1px solid var(--grid-line)">
      <div style="font-weight:600">${teamDot(d.team)}${d.name}</div>
      ${body}
    </div>`;
  }).join("");
}

// ---------- driver stats modal ----------
function showDriverModal(code) {
  const d = byCode[code];
  document.getElementById("dm-logo").src = `logos/${d.team}.png`;
  document.getElementById("dm-logo").alt = TEAM_NAMES[d.team] || d.team;
  document.getElementById("dm-name").textContent = d.name;
  document.getElementById("dm-team").textContent = TEAM_NAMES[d.team] || d.team;
  const stats = [
    ["CPT salary", fmt$(d.salaryCpt)],
    ["D salary", fmt$(d.salary)],
    ["Avg DK pts", d.avgDk.toFixed(1)],
    ["Races", d.races],
    ["Avg finish", `${d.avgFinish.toFixed(1)} ± ${d.stdFinish.toFixed(1)}`],
    ["Avg grid", `${d.avgGrid.toFixed(1)} ± ${d.stdGrid.toFixed(1)}`],
    ["DNF rate", `${(d.dnfRate * 100).toFixed(0)}%`],
  ];
  document.getElementById("dm-stats").innerHTML = stats.map(([label, value]) =>
    `<div><div class="label">${label}</div><div class="value">${value}</div></div>`
  ).join("");
  document.getElementById("driver-modal").classList.add("open");
}
function closeDriverModal() {
  document.getElementById("driver-modal").classList.remove("open");
}

// ---------- race simulation ----------
