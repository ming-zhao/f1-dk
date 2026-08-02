// One race's worth of data. Everything here is replaced wholesale by applyRace(),
// so the same file serves the standalone page (data inlined) and the multi-race
// picker (data fetched per race).
let FRAMES = [], OUTLINE = [], ROWS = [], COLOURS = {};
let PITLANE = [], PITBOX = [], LAPNUMS = [], TOTAL_LAPS = 0;
let W = 1150, H = 620, DT = 0.5, ROT = 0;
const PAD = 34;
// Track/car sizes in px. Deliberately NOT to scale: a real F1 car is ~2m wide on a
// ~12m track (~17%), which at this zoom makes the cars specks. Both are derived per
// circuit (layout.fit_for_track) so a tight track like Monaco can't overlap itself.
//
// The road is drawn at the FULL fitted width. It used to be scaled to 0.62 of it,
// which left the road NARROWER THAN TWO CARS ABREAST (measured at Melbourne: 16.1 px
// of road versus 19.3 px for two cars). That made a two-column starting grid
// impossible to draw, and side-by-side racing had nowhere to happen either.
let TRACK_W = 26, CAR_SCALE = 1;
// Cars are sized off the road width so they stay proportionate on any circuit. The
// WIDTH ratio is the load-bearing one: at 0.40 two cars side by side span 0.80 of the
// road, which leaves a lane-marking gap between them and a margin to each edge.
// Anything above 0.50 makes two abreast geometrically impossible.
const CAR_W_RATIO = 0.40, CAR_L_RATIO = 0.62;
let CAR_L = TRACK_W * CAR_L_RATIO, CAR_W = TRACK_W * CAR_W_RATIO;
const SHOW_LABELS = true;

// Fit state, recomputed whenever rotation changes.
// laneScreen/laneArcScreen are declared here (not beside drawPitLane) because
// setRotation() clears them and runs at load — `let` is not hoisted.
let cosR, sinR, minX, minY, scale, offX, offY, laneScreen = null,
    laneArcScreen = null;
const rotXY = (x, y) => [x * cosR - y * sinR, x * sinR + y * cosR];

function setRotation(rad) {
  ROT = rad;
  laneScreen = laneArcScreen = null;   // screen-space lane offsets depend on the fit
  cosR = Math.cos(ROT); sinR = Math.sin(ROT);
  // Fit on the CIRCUIT only: stray pit-lane points inflate the box and shrink
  // the track. The pit lane is adjacent, so it still lands on-canvas.
  const R = OUTLINE.map(p => rotXY(p[0], p[1]));
  const rxs = R.map(p => p[0]), rys = R.map(p => p[1]);
  minX = Math.min(...rxs); const maxX = Math.max(...rxs);
  minY = Math.min(...rys); const maxY = Math.max(...rys);
  scale = Math.min((W - 2*PAD) / (maxX - minX), (H - 2*PAD) / (maxY - minY));
  offX = (W - (maxX - minX) * scale) / 2;
  offY = (H - (maxY - minY) * scale) / 2;

  // Compass: north is +y in track coords; the canvas flips y, so negate.
  const deg = -ROT * 180 / Math.PI;
  document.getElementById('needle').setAttribute('transform', `rotate(${deg} 27 27)`);
  // Position the "N" at the needle tip so the text stays upright at any angle.
  // Place "N" at the needle tip, upright — rotating the text makes it unreadable.
  const a = (deg - 90) * Math.PI / 180;
  const lbl = document.getElementById('nlabel');
  lbl.setAttribute('x', (27 + 21.5 * Math.cos(a)).toFixed(1));
  lbl.setAttribute('y', (27 + 21.5 * Math.sin(a)).toFixed(1));
}

// Flip y: track data is y-up, canvas is y-down.
const proj = (x, y) => {
  const [rx, ry] = rotXY(x, y);
  return [offX + (rx - minX) * scale, H - (offY + (ry - minY) * scale)];
};

setRotation(ROT);

const ctx = document.getElementById('c').getContext('2d');

// Cars are sampled ~every 4 s on a full race, which is ~103 m of travel (p90 267 m,
// max 375 m). Interpolating between two such samples in a STRAIGHT LINE cuts the chord
// across corners: cars visibly leave the asphalt (measured: 52% of sampled instants
// more than half a road-width off it, worst case 107 px ≈ 7 road widths), and on a
// tight bend the chord can even point opposite to the direction of travel.
//
// Fix: describe every car as (distance along the path, lateral offset) instead of
// (x, y). Interpolating those follows the circuit's curvature, so cars stay on the road
// and always move forwards. Cheap too — the projection is precomputed once per race.
//
// Two paths matter, not one. A car is either on the circuit or in the pit lane, and
// the pit lane is a SEPARATE route that rejoins the track at both ends. Projecting a
// pitting car onto the circuit is what produced the apparent reversals: Monaco's lane
// runs antiparallel to the start straight, so a car crawling up the pit lane maps to
// an arc length running *backwards* along the track. Each path therefore gets its own
// arc-length frame, and a car is assigned to whichever it is genuinely closer to.
function makeArc(pts) {
  const cum = [0];
  for (let i = 1; i < pts.length; i++) {
    cum.push(cum[i - 1] + Math.hypot(pts[i][0] - pts[i - 1][0],
                                     pts[i][1] - pts[i - 1][1]));
  }
  return { pts, cum, len: cum[cum.length - 1] || 1 };
}

// Nearest point on `arc`, as (arc length s, signed lateral offset d, distance).
function arcProject(arc, x, y) {
  const { pts, cum } = arc;
  let bi = 0, bd = Infinity, bt = 0;
  for (let i = 0; i < pts.length - 1; i++) {
    const [ax, ay] = pts[i], [bx, by] = pts[i + 1];
    const vx = bx - ax, vy = by - ay;
    const L2 = vx * vx + vy * vy;
    let tt = L2 ? ((x - ax) * vx + (y - ay) * vy) / L2 : 0;
    tt = Math.max(0, Math.min(1, tt));
    const px_ = ax + vx * tt, py_ = ay + vy * tt;
    const dd = (x - px_) ** 2 + (y - py_) ** 2;
    if (dd < bd) { bd = dd; bi = i; bt = tt; }
  }
  const [ax, ay] = pts[bi], [bx, by] = pts[bi + 1];
  const vx = bx - ax, vy = by - ay;
  const vlen = Math.hypot(vx, vy) || 1;
  const px_ = ax + vx * bt, py_ = ay + vy * bt;
  // Signed offset: positive on the left of travel direction.
  const cross = (vx * (y - py_) - vy * (x - px_)) / vlen;
  return [cum[bi] + vlen * bt, cross, Math.sqrt(bd)];
}

// Back to x/y from (s, d). `wrap` closes the loop (the circuit); the pit lane is an
// open path, so its arc length is clamped instead of wrapped.
function arcPoint(arc, s, d, wrap) {
  const { pts, cum, len } = arc;
  s = wrap ? ((s % len) + len) % len : Math.max(0, Math.min(len, s));
  let lo = 0, hi = cum.length - 1;
  while (lo < hi - 1) {
    const mid = (lo + hi) >> 1;
    if (cum[mid] <= s) lo = mid; else hi = mid;
  }
  const [ax, ay] = pts[lo], [bx, by] = pts[Math.min(lo + 1, pts.length - 1)];
  const seg = (cum[lo + 1] ?? len) - cum[lo] || 1;
  const tt = (s - cum[lo]) / seg;
  const vx = bx - ax, vy = by - ay;
  const vlen = Math.hypot(vx, vy) || 1;
  return [ax + vx * tt - vy / vlen * d, ay + vy * tt + vx / vlen * d,
          Math.atan2(vy, vx)];
}

let TRACK_ARC = null, LANE_ARC = null;
// Kept as globals for the old names, so external checks and player.py keep working.
let TRACK_CUM = [], TRACK_LEN = 0;

function buildTrackArc() {
  TRACK_ARC = makeArc(OUTLINE);
  TRACK_CUM = TRACK_ARC.cum; TRACK_LEN = TRACK_ARC.len;
  LANE_ARC = PITLANE.length > 1 ? makeArc(PITLANE) : null;
}

// Half the drawn road, in data units. Cars are clamped to this so one can never be
// drawn off the asphalt, whatever the source data says.
const halfRoadData = () => (TRACK_W * 0.42) / (scale || 0.05);

function toTrackCoords(x, y) {
  if (!TRACK_ARC) buildTrackArc();
  const t = arcProject(TRACK_ARC, x, y);
  return [t[0], t[1]];
}

function fromTrackCoords(s, d) {
  if (!TRACK_ARC) buildTrackArc();
  const h = halfRoadData();
  return arcPoint(TRACK_ARC, s, Math.max(-h, Math.min(h, d)), true);
}

// (s, lateral, onLane) per car per frame, computed once when a race loads.
let TRACK_POS = null;
function buildTrackPositions() {
  buildTrackArc();
  // A car counts as "in the pit lane" only when the lane is clearly the better fit:
  // closer than the circuit AND far enough off the racing line that it can't just be
  // sampling noise. Measured on Monaco 2024, cars sit a median 0.1 m / p99 4.7 m from
  // the outline when on track, so 8 m is comfortably clear of that.
  const LANE_MIN = 8 * 9.8;         // metres → decimetres (the data's units)
  TRACK_POS = FRAMES.map(f => {
    const o = {};
    for (const d in f) {
      const t = arcProject(TRACK_ARC, f[d][0], f[d][1]);
      const l = LANE_ARC ? arcProject(LANE_ARC, f[d][0], f[d][1]) : null;
      o[d] = (l && l[2] < t[2] && t[2] > LANE_MIN)
        ? [l[0], l[1], 1]           // along the pit lane
        : [t[0], t[1], 0];          // along the circuit
    }
    return o;
  });

  // Unwrap each car's circuit arc length so it always increases — otherwise crossing
  // the start/finish line looks like a full lap backwards.
  //
  // Two things this must survive, both measured in the real feed:
  //   * /location glitches. 0.4% of raw samples imply an impossible speed (>120 m/s,
  //     up to 291 m/s), so a car's position can jump a few hundred metres and snap
  //     back. Unwrapping on a naive "s went down" test turns each glitch into a
  //     spurious extra lap, and the car then races a whole lap ahead forever.
  //   * Genuinely stationary cars. A red-flag queue or a pit stop holds s constant.
  // So: only add a lap when s drops by MOST of a lap (a real S/F crossing), and
  // otherwise carry the previous value forward rather than letting s go backwards.
  // The result is monotonic by construction, which is what makes motion always
  // forwards no matter how noisy the source is.
  const lap = {}, last = {};
  for (let i = 0; i < TRACK_POS.length; i++) {
    for (const d in TRACK_POS[i]) {
      const p = TRACK_POS[i][d];
      if (p[2]) continue;                       // pit lane: its own arc space
      if (last[d] === undefined) { lap[d] = 0; last[d] = p[0]; continue; }
      let s = p[0] + lap[d] * TRACK_LEN;
      // A drop of more than ~65% of a lap is a start/finish crossing, not noise.
      if (s < last[d] - TRACK_LEN * 0.65) { lap[d]++; s += TRACK_LEN; }
      // Never go backwards: a glitch or a stationary car holds its place instead.
      p[0] = last[d] = Math.max(last[d], s);
    }
  }
}

function drawTrack() {
  ctx.beginPath();
  OUTLINE.forEach((p, i) => {
    const [x, y] = proj(p[0], p[1]);
    i ? ctx.lineTo(x, y) : ctx.moveTo(x, y);
  });
  ctx.closePath();                       // seal the lap seam
  ctx.lineJoin = ctx.lineCap = 'round';
  // Wide enough that two cars side by side are visibly side by side.
  ctx.strokeStyle = '#3d3d47'; ctx.lineWidth = TRACK_W + 4; ctx.stroke();
  ctx.strokeStyle = '#292930'; ctx.lineWidth = TRACK_W; ctx.stroke();
  // Faint centre line for a sense of racing line / width.
  ctx.setLineDash([5, 9]);
  ctx.strokeStyle = 'rgba(255,255,255,.07)'; ctx.lineWidth = 1; ctx.stroke();
  ctx.setLineDash([]);
  drawPitLane();
  drawStartMarker();
}

// Pit lane, derived from where cars actually drive during a stop (no geometry source
// exists for it). Boxes are the near-stationary points.
// The drawn pit lane is pushed sideways so it doesn't collide with the main straight
// at exaggerated road widths. Offset is CONSTANT (one track width), not scaled
// per-point: real pit lanes are parallel by construction, so a constant-offset bar
// deviates from the true centreline by only ~0.4 m at Melbourne while being immune to
// the vertex-distance noise a per-point scan introduces (a car exactly on the racing
// line can measure 8.8 m from the nearest vertex at 15-26 m spacing). This stylised
// parallel channel is also what F1's own broadcast graphics use.
// 1.9 track widths: the real lane runs alongside the start straight, so a
// smaller offset puts it underneath the grid as it forms — cars then look
// like they're queued in the pits before the race has even started.
const LANE_OFFSET = 2.6;                       // in track widths

// Perpendicular distance from p to the nearest track SEGMENT (not vertex), plus the
// outward unit normal at that point.
function nearestTrack(sx, sy, track) {
  let best = null, bd = Infinity;
  for (let k = 0; k < track.length - 1; k++) {
    const [ax, ay] = track[k], [bx, by] = track[k + 1];
    const vx = bx - ax, vy = by - ay;
    const L2 = vx * vx + vy * vy;
    let tt = L2 ? ((sx - ax) * vx + (sy - ay) * vy) / L2 : 0;
    tt = Math.max(0, Math.min(1, tt));
    const px_ = ax + vx * tt, py_ = ay + vy * tt;
    const d = Math.hypot(sx - px_, sy - py_);
    if (d < bd) { bd = d; best = [px_, py_, d]; }
  }
  return best;
}

function offsetToLane(dx, dy) {
  const track = OUTLINE.map(p => proj(p[0], p[1]));
  const [sx, sy] = proj(dx, dy);
  const near = nearestTrack(sx, sy, track);
  if (!near) return [sx, sy];
  const [tx, ty, d] = near;
  let ux = sx - tx, uy = sy - ty;
  const L = Math.hypot(ux, uy);
  if (L < 0.01) return [sx, sy];
  ux /= L; uy /= L;
  const want = TRACK_W * LANE_OFFSET;
  return [tx + ux * want, ty + uy * want];
}

function pitLaneScreen() {
  if (laneScreen) return laneScreen;
  laneScreen = PITLANE.map(p => offsetToLane(p[0], p[1]));
  return laneScreen;
}

// Arc length along the DRAWN (sideways-offset) lane, in screen space. A pitting car is
// positioned by its fraction along the real lane, so it slides along the dashed line
// you can actually see rather than along the true lane hidden under the track.
function pitLaneArc() {
  if (!laneArcScreen) laneArcScreen = makeArc(pitLaneScreen());
  return laneArcScreen;
}

function drawPitLane() {
  if (!PITLANE.length) return;
  const pts = pitLaneScreen();
  // A single line, not a road. The derived lane is a 1-D path — a sequence of
  // recorded car positions — and carries no width, so drawing it as wide asphalt
  // would be inventing information.
  ctx.beginPath();
  pts.forEach(([x, y], i) => { i ? ctx.lineTo(x, y) : ctx.moveTo(x, y); });
  ctx.setLineDash([6, 4]);
  ctx.strokeStyle = 'rgba(232,193,28,.55)';
  ctx.lineWidth = 2;
  ctx.lineCap = ctx.lineJoin = 'round';
  ctx.stroke();
  ctx.setLineDash([]);

  // Entry and exit, reproducible to a few metres across stops.
  for (const [end, label] of [[pts[0], 'in'], [pts[pts.length - 1], 'out']]) {
    if (!end) continue;
    ctx.beginPath(); ctx.arc(end[0], end[1], 2.6, 0, 6.2832);
    ctx.fillStyle = 'rgba(232,193,28,.9)'; ctx.fill();
  }

  // Pit boxes — where cars actually stop.
  for (const b of PITBOX) {
    const [x, y] = offsetToLane(b[0], b[1]);
    ctx.beginPath(); ctx.arc(x, y, 1.9, 0, 6.2832);
    ctx.fillStyle = 'rgba(232,193,28,.85)'; ctx.fill();
  }
}

// Start/finish: an arrow set OFF to the side of the track, pointing at the line and
// showing travel direction — a dot sitting on the track reads as a stray car.
function drawStartMarker() {
  const [sx, sy] = proj(OUTLINE[0][0], OUTLINE[0][1]);
  const j = Math.min(6, OUTLINE.length - 1);
  const [nx, ny] = proj(OUTLINE[j][0], OUTLINE[j][1]);
  let dx = nx - sx, dy = ny - sy;
  const len = Math.hypot(dx, dy) || 1;
  dx /= len; dy /= len;
  const px_ = -dy, py_ = dx;             // normal, to offset clear of the track

  ctx.beginPath();                        // line across the track
  ctx.moveTo(sx + px_ * TRACK_W * 0.55, sy + py_ * TRACK_W * 0.55);
  ctx.lineTo(sx - px_ * TRACK_W * 0.55, sy - py_ * TRACK_W * 0.55);
  ctx.strokeStyle = '#e10600'; ctx.lineWidth = 2.5; ctx.stroke();

  const ox = sx + px_ * (TRACK_W * 0.5 + 14);   // arrowhead, clear of the asphalt
  const oy = sy + py_ * (TRACK_W * 0.5 + 14);
  ctx.save();
  ctx.translate(ox, oy);
  ctx.rotate(Math.atan2(dy, dx));
  ctx.beginPath();
  ctx.moveTo(7, 0); ctx.lineTo(-4, 5); ctx.lineTo(-4, -5);
  ctx.closePath();
  ctx.fillStyle = '#e10600'; ctx.fill();
  ctx.restore();

  ctx.font = '600 9px -apple-system, sans-serif';
  ctx.fillStyle = '#e10600';
  ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
  ctx.fillText('S/F', sx + px_ * (TRACK_W * 0.5 + 28),
                      sy + py_ * (TRACK_W * 0.5 + 28));
}

// A tiny F1 car: nose, sidepods, wings, wheels. Drawn with a dark outline and a
// bright highlight so the team colour reads clearly against the dark track — a flat
// fill at this size looked washed out.
function drawCar(x, y, heading, colour, hot, code) {
  ctx.save();
  ctx.translate(x, y);
  ctx.rotate(heading);
  const L = CAR_L, Wd = CAR_W;

  if (hot) {                                  // contact / battle halo
    ctx.beginPath(); ctx.arc(0, 0, L * 0.85, 0, 6.2832);
    ctx.fillStyle = 'rgba(255,90,60,.32)'; ctx.fill();
    ctx.strokeStyle = 'rgba(255,120,90,.75)'; ctx.lineWidth = 1.2; ctx.stroke();
  }

  // Drop shadow lifts the car off the asphalt.
  ctx.shadowColor = 'rgba(0,0,0,.75)';
  ctx.shadowBlur = 4; ctx.shadowOffsetY = 1;

  ctx.fillStyle = '#08080a';                   // tyres
  const tw = Wd * 0.30, tl = L * 0.26;
  for (const [tx, ty] of [[-L*0.30, -Wd*0.52], [-L*0.30, Wd*0.52],
                          [ L*0.28, -Wd*0.46], [ L*0.28, Wd*0.46]]) {
    ctx.beginPath(); ctx.rect(tx - tl/2, ty - tw/2, tl, tw); ctx.fill();
  }
  ctx.shadowBlur = 0; ctx.shadowOffsetY = 0;

  // Body, nose forward (+x).
  ctx.beginPath();
  ctx.moveTo(L * 0.52, 0);
  ctx.lineTo(L * 0.10, -Wd * 0.26);
  ctx.lineTo(-L * 0.42, -Wd * 0.30);
  ctx.lineTo(-L * 0.50, 0);
  ctx.lineTo(-L * 0.42, Wd * 0.30);
  ctx.lineTo(L * 0.10, Wd * 0.26);
  ctx.closePath();
  // Vertical gradient: lit top edge, shaded bottom — reads as a 3D body.
  const g = ctx.createLinearGradient(0, -Wd * 0.5, 0, Wd * 0.5);
  g.addColorStop(0, shade(colour, 1.45));
  g.addColorStop(0.45, colour);
  g.addColorStop(1, shade(colour, 0.62));
  ctx.fillStyle = g; ctx.fill();
  ctx.strokeStyle = 'rgba(0,0,0,.85)'; ctx.lineWidth = 1.1; ctx.stroke();

  ctx.fillStyle = '#f2f2f5';                   // front + rear wings
  ctx.fillRect(L * 0.40, -Wd * 0.42, L * 0.08, Wd * 0.84);
  ctx.fillRect(-L * 0.56, -Wd * 0.36, L * 0.08, Wd * 0.72);

  ctx.fillStyle = 'rgba(255,255,255,.85)';     // halo / cockpit glint
  ctx.beginPath(); ctx.arc(-L * 0.02, 0, Wd * 0.13, 0, 6.2832); ctx.fill();

  ctx.restore();

  // Driver code beside the car, so you can tell who's who without the tower.
  if (SHOW_LABELS) {
    ctx.font = '700 8px -apple-system, sans-serif';
    ctx.textAlign = 'center'; ctx.textBaseline = 'bottom';
    ctx.strokeStyle = 'rgba(0,0,0,.9)'; ctx.lineWidth = 2.5;
    ctx.strokeText(code, x, y - CAR_W * 0.75);
    ctx.fillStyle = colour;
    ctx.fillText(code, x, y - CAR_W * 0.75);
  }
}

// Lighten (>1) or darken (<1) a #rrggbb colour.
function shade(hex, f) {
  const m = /^#?([a-f\d]{2})([a-f\d]{2})([a-f\d]{2})$/i.exec(hex);
  if (!m) return hex;
  const c = [1, 2, 3].map(i => Math.max(0, Math.min(255,
    Math.round(parseInt(m[i], 16) * f))));
  return `rgb(${c[0]},${c[1]},${c[2]})`;
}

// Write only on change — reassigning textContent every frame causes visible flicker.
const _txt = {};
function setText(id, s) {
  if (_txt[id] === s) return;
  _txt[id] = s;
  const el = document.getElementById(id);
  if (el) el.textContent = s;
}

// The wheel-to-wheel readout needs markup (the leading digit gets the halo), so it
// can't go through setText. Same change-guard though: writing innerHTML every frame
// is what made the banner flicker in the first place.
let _battles = null;
function setBattles(s, halo) {
  const key = s + ' ' + (halo ? 1 : 0);
  if (_battles === key) return;
  _battles = key;
  const el = document.getElementById('battles');
  if (!el) return;
  const m = halo && /^(\d+)( .*)$/.exec(s);
  // Escaping isn't needed — `s` is either a literal or a number plus fixed text —
  // but building it from a match keeps the digit and the rest strictly separate.
  el.innerHTML = m ? `<span class="halo">${m[1]}</span>${m[2]}` : s;
}

// Numeric gaps get a '+'; lapped cars already read like "4 LAPS".
const fmt = v => v == null ? '' : (/^[0-9.]+$/.test(v) ? '+' + v : v);

// The tower is built ONCE and then updated in place. Re-rendering innerHTML every
// frame (60ms) is what made it strobe: every row's DOM was destroyed and rebuilt
// 16x/second. Now each driver owns a persistent <tr> that we reorder and retext.
const rowEls = new Map();
const tbody = document.getElementById('slots');

// One persistent <tr> per driver, rebuilt only when the driver set changes (i.e.
// when a different race is loaded). This markup is the single source of truth for
// a tower row — it used to be duplicated in player.py and desynced.
function buildTower() {
  tbody.innerHTML = '';
  rowEls.clear();
  for (const d of Object.keys(COLOURS).sort()) {
    const tr = document.createElement('tr');
    tr.innerHTML =
      `<td class="pos"></td>` +
      `<td class="bar"><i style="background:${COLOURS[d] || '#999'}"></i></td>` +
      `<td><span class="drv"><span class="code">${d}</span>` +
      `<span class="num"></span></span></td>` +
      `<td class="arrow"></td>` +
      `<td class="gap lead"></td><td class="gap int"></td>` +
      `<td class="tyrecell"></td><td class="flag"></td>`;
    rowEls.set(d, tr);
    tbody.appendChild(tr);
  }
}

// Movement highlights persist for a few FRAMES so they're readable. Measuring this
// in race-milliseconds was wrong: at 4 s/frame (a full race) a 1200 ms hold expired
// before its own frame rendered, so no arrow ever appeared.
const HOLD_FRAMES = 4;
let lastOrder = null, marks = new Map();

function updateTower(rows, frameIdx) {
  const order = rows.map(r => r.d);

  if (lastOrder) {
    rows.forEach((r, idx) => {
      const was = lastOrder.indexOf(r.d);
      if (was > -1 && was !== idx) marks.set(r.d, { move: was - idx, at: frameIdx });
    });
  }

  rows.forEach((r, idx) => {
    const tr = rowEls.get(r.d);
    if (!tr) return;
    if (tbody.children[idx] !== tr) tbody.insertBefore(tr, tbody.children[idx]);

    // Row tint flashes briefly on the frame a place actually changes hands; the
    // arrow itself is the persistent grid-relative total (below).
    const mark = marks.get(r.d);
    const fresh = mark && (frameIdx - mark.at) < HOLD_FRAMES;
    tr.className = (r.out != null ? 'retired'
                    : fresh ? (mark.move > 0 ? 'gained' : 'lost') : '');

    tr.children[0].textContent = idx + 1;
    tr.children[2].querySelector('.num').textContent = r.n;

    // Cells 4-6 are the only ones whose shape changes between a running and a
    // retired car, so name them — index arithmetic here is what broke when the
    // +/- column was inserted at index 3.
    const lead = tr.children[4], intv = tr.children[5], tyre = tr.children[6];

    if (r.out != null) {
      // "retired lap 40" measures ~74px and the Leader column is 66px, so at
      // colspan 1 the note was clipped mid-word. Span Leader+Int+Tyre
      // (66+58+50 = 174px) and hide the two cells it swallows: every other column
      // still takes its width from the <colgroup>, so nothing shifts sideways when
      // a car drops out.
      lead.colSpan = 3;
      intv.style.display = tyre.style.display = 'none';
      tr.children[3].innerHTML = '';
      lead.textContent = `retired lap ${r.out}`;
      tr.children[7].innerHTML = '<span class="out">OUT</span>';
      return;
    }
    // Rows are persistent and reused, so a car rendered as retired in an earlier
    // frame has to be put back to the plain 8-cell layout when we scrub backwards.
    if (lead.colSpan !== 1) {
      lead.colSpan = 1;
      intv.style.display = tyre.style.display = '';
    }

    // Places gained/lost since the start — persistent, so it's readable. A transient
    // arrow shown only on the frame of a pass is invisible: at 4 s/frame barely 1% of
    // frames contain one. This is what a broadcast shows.
    const dl = r.delta;
    // Always show a value — a blank cell is ambiguous, "0" says "same as the grid".
    tr.children[3].innerHTML =
      (dl === null || dl === undefined) ? '<span class="flat">–</span>'
      : dl === 0 ? '<span class="flat">0</span>'
      : `<span class="${dl > 0 ? 'up' : 'down'}">${dl > 0 ? '▲' : '▼'}` +
        `${Math.abs(dl)}</span>`;

    lead.textContent = idx === 0 ? '—' : fmt(r.g);
    intv.textContent = idx === 0 ? '' : fmt(r.i);
    tyre.innerHTML = r.c
      ? `<span class="tyre ${r.c}">${r.c}</span>` +
        (r.a != null ? ` <span class="age">${r.a}</span>` : '') : '';
    tr.children[7].innerHTML = r.p ? '<span class="pit">PIT</span>' : '';
  });

  // Any driver absent from this frame's order (no timing yet) sinks to the bottom.
  for (const [d, tr] of rowEls) if (!order.includes(d)) tbody.appendChild(tr);
  if (order.length) lastOrder = order;
}

// ── Starting grid ────────────────────────────────────────────────────────────
// The recorded feed contains NO grid formation. Measured on Melbourne 2025 at the
// pre-race frames, all 20 cars sit within 0.1 m of the racing line, strung out
// single-file with 5-87 m gaps: /location is simply too coarse (and the cars are
// stationary in a queue) to show the staggered two-column formation you see on TV.
// Monaco 2024 is worse — a lap-1 red flag means its "grid" frames are cars queued
// in the PIT LANE.
//
// So the slots are drawn from the SPORTING REGULATIONS instead, and populated with
// the real starting order from the timing feed (ROWS[0], which is genuine: NOR, PIA,
// VER, RUS matches the actual 2025 Melbourne grid). Geometry is idealised; who
// stands where is real. That split is deliberate — inventing plausible-looking
// telemetry would be worse than an honestly stylised formation.
//
// Real grids are staggered: each car sits ~8 m behind the one ahead and on the
// opposite side of the centreline, giving the classic zigzag.
//
// Spacing is measured in DRAWN CAR LENGTHS, not in metres. The cars are deliberately
// ~10x oversized so they're visible at all (see CAR_W_RATIO), so the regulation 8 m
// is self-inconsistent here: at Melbourne 8 m is 4.3 px on screen while a drawn car
// is 16 px long, which packed the whole grid into an overlapping heap (measured:
// 3.5 px between the PIA and RUS centres). Scaling the formation to the cars keeps
// the shape of a real grid at a size you can actually read.
// Both constants are sized against the DRAWN CAR, not the road, because the cars are
// what has to stay legible:
//  * step 0.85 car lengths put consecutive cars 11.2 px apart when a car is 13.1 px
//    long, so every car overlapped the one behind and the zigzag closed into a solid
//    line. A step below 1.0 cannot be read as separate cars; 1.5 leaves half a car of
//    asphalt between rows, which is what a real grid looks like from above.
//  * lateral 0.24 of road width gave a 5.1 px offset against an 8.5 px-wide car, so
//    the two columns overlapped on the centreline and read as single file. The offset
//    now scales with the car's WIDTH, so the columns are always clear of each other.
const GRID_STEP_CARS = 1.5;      // longitudinal step per position, in car lengths
const GRID_LATERAL_CARS = 0.62;  // offset from centreline, in car widths

// Grid slot for the car in position `pos` (1-based), as (arc length, lateral offset)
// in the circuit's arc-length space — the same space cars are animated in, so a car
// can be blended from its slot into its first recorded position with no special case.
function gridSlot(pos, startS) {
  const side = (pos % 2 === 1) ? -1 : 1;         // pole on the racing-line side
  const px = scale || 0.05;                       // px per data unit
  // Slots extend BACKWARDS from the start line. Arc length is wrapped by arcPoint,
  // so a grid that reaches back past the lap seam still lands on the right asphalt.
  const step = (CAR_L * GRID_STEP_CARS) / px;    // one position, in data units
  // Keep the columns a car-width apart, but never wider than the asphalt: on a narrow
  // circuit the road caps it, so cars stay on the track rather than on the barriers.
  const lat = Math.min(halfRoadData() * 0.55,
                       (CAR_W * GRID_LATERAL_CARS) / px);
  return [startS - (pos - 1) * step, side * lat];
}

// Arc length of the start/finish line. OUTLINE[0] is the S/F point by construction
// (circuit.py orders the official map from there), so this is 0 — computed rather
// than assumed so a future reordering of the outline can't silently break the grid.
function startLineS() {
  if (!TRACK_ARC) buildTrackArc();
  return arcProject(TRACK_ARC, OUTLINE[0][0], OUTLINE[0][1])[0];
}

// Where every car sits on the grid, keyed by driver code, in (s, lateral, onLane)
// form matching TRACK_POS. Built from the starting order, so a car with no timing
// row (rare) simply keeps its recorded position.
let GRID_POS = null;
function buildGrid() {
  GRID_POS = null;
  const rows = ROWS[0] || [];
  if (!rows.length) return;
  const startS = startLineS();
  const g = {};
  rows.forEach((r, i) => { g[r.d] = [...gridSlot(i + 1, startS), 0]; });
  GRID_POS = g;
}

function draw(cur) {
  const idx = Math.floor(cur);
  const frac = cur - idx;
  ctx.clearRect(0, 0, W, H);
  drawTrack();

  // Blend the two nearest frames ALONG THE PATH each car is on, so motion follows the
  // circuit's curvature instead of cutting chords across corners.
  if (!TRACK_POS) buildTrackPositions();
  const j = Math.min(idx + 1, FRAMES.length - 1);
  const p0 = TRACK_POS[idx] || {}, p1 = TRACK_POS[j] || p0;
  const rows = ROWS[idx] || [];
  const order = rows.map(r => r.d);
  const preRace = (typeof LAPNUMS !== 'undefined') && LAPNUMS[idx] === 0;

  // Screen position + heading per car. Cars on the circuit are placed in track arc
  // space (clamped to the asphalt); cars in the pit lane are placed along the DRAWN
  // lane, which is already offset clear of the track. Heading comes back in screen
  // space so the two paths can be blended directly.
  const lane = LANE_ARC ? pitLaneArc() : null;
  const place = (p) => {
    if (p[2] && lane) {                      // in the pit lane
      const q = arcPoint(lane, (p[0] / (LANE_ARC.len || 1)) * lane.len, 0, false);
      return [q[0], q[1], q[2]];             // already screen space
    }
    const q = fromTrackCoords(p[0], p[1]);   // [x, y, heading], on the asphalt
    const [sx, sy] = proj(q[0], q[1]);
    return [sx, sy, -q[2] - ROT];            // data heading → screen heading
  };
  // On the grid, substitute the regulation slot for the recorded position (see
  // gridSlot). The LAST pre-race frame blends slot -> recorded position, so the cars
  // roll off the grid onto the racing line instead of teleporting on the green light.
  if (preRace && !GRID_POS) buildGrid();
  const nextRacing = preRace && LAPNUMS[j] !== 0;
  const grid = (d, p) => (GRID_POS && GRID_POS[d]) ? GRID_POS[d] : p;

  const screen = {}, head = {};
  for (const d in p0) {
    let a = p0[d], b = p1[d] || a;
    if (preRace) {
      a = grid(d, a);
      // Mid-grid: hold the slot. Final pre-race frame: ease across to the real
      // position, so the transition into racing is continuous.
      b = nextRacing ? (p1[d] || a) : grid(d, b);
    }
    let x, y, h;
    if (a[2] === b[2]) {
      // Same path: interpolate ALONG it, so motion follows the curvature.
      const q = place([a[0] + (b[0] - a[0]) * frac,
                       a[1] + (b[1] - a[1]) * frac, a[2]]);
      x = q[0]; y = q[1]; h = q[2];
    } else {
      // Entering or leaving the pit lane: the two samples live in different arc
      // spaces, so blend the two SCREEN positions instead. A car crossing between
      // lane and track really does cut across, and matching both endpoints exactly
      // is what keeps the motion continuous rather than popping on the switch frame.
      // Ease it so the car leaves and arrives along its path rather than sliding
      // linearly off the asphalt halfway through.
      const A = place(a), B = place(b);
      const e = frac * frac * (3 - 2 * frac);
      x = A[0] + (B[0] - A[0]) * e;
      y = A[1] + (B[1] - A[1]) * e;
      h = Math.atan2(B[1] - A[1], B[0] - A[0]);   // face the way it's sliding
    }
    screen[d] = [x, y];
    head[d] = h;
  }
  const codes = Object.keys(screen);

  // Flag cars running within a car-length of each other: real wheel-to-wheel
  // battles and contact. These are recorded positions, so nothing is staged —
  // what's highlighted actually happened.
  // On the grid every car is parked within a car length of another, so the halo
  // would flag the whole field as "battling". It only means something once racing.
  const close = new Set();
  if (!preRace) for (let a = 0; a < codes.length; a++) {
    for (let b = a + 1; b < codes.length; b++) {
      const p = screen[codes[a]], q = screen[codes[b]];
      if (Math.hypot(p[0] - q[0], p[1] - q[1]) < CAR_L * 1.15) {
        close.add(codes[a]); close.add(codes[b]);
      }
    }
  }

  // Draw leaders last so they sit on top where cars overlap.
  const seq = order.length ? order.slice().reverse() : codes;
  for (const d of seq) {
    const p = screen[d]; if (!p) continue;
    // head[] is already a screen-space angle (place() converts).
    drawCar(p[0], p[1], head[d] || 0, COLOURS[d] || '#999', close.has(d), d);
  }
  // The count marks cars running within ~1 car length — real wheel-to-wheel battles
  // and contact. Nothing is staged: these are recorded positions. The number itself
  // wears the canvas halo, which is what "haloed" used to have to say in words.
  //
  // Always rendered, including at 0: an empty string let the control bar reflow as
  // battles came and went (measured: the seek bar jumped 1012 → 1040 px). The width
  // is fixed in CSS, so the text can't push anything sideways either.
  setBattles(preRace ? 'grid forming' : `${close.size} cars wheel-to-wheel`,
             !preRace);

  updateTower(rows, idx);
  const ln = (typeof LAPNUMS !== 'undefined') ? LAPNUMS[idx] : null;
  setText('lap', ln === 0 ? 'grid \u00b7 pre-race'
                : ln ? `lap ${ln} / ${TOTAL_LAPS || '?'}` : 'lap \u2013');
  // Elapsed RACE time (not wall-clock playback time), as m:ss — a full race reaches
  // ~105 min, which is unreadable in raw seconds.
  const secs = idx * DT;
  setText('clock', `${Math.floor(secs / 60)}:${String(Math.floor(secs % 60)).padStart(2, '0')}`);
  document.getElementById('seek').value = idx;
}

let playing = true, speed = 1, raf = null, lastTs = null, cursor = 0;

// Playback is normalised to a FIXED WALL-CLOCK DURATION, not to real race speed: 1x
// runs the whole replay in PLAY_SECONDS regardless of how long the race actually was.
// So 1x = 10 min, 0.5x = 20 min, 2x = 5 min, 4x = 2.5 min — and a 78-lap Monaco and a
// 57-lap Melbourne both take the same time to watch. Real speed would be ~105 min.
//
// Rendering is decoupled from the data rate: requestAnimationFrame draws at ~60 fps and
// draw() interpolates between the two nearest samples, so advancing the cursor slowly
// still looks smooth even though positions are only sampled every DT seconds.
const PLAY_SECONDS = 600;

function tick(ts) {
  raf = requestAnimationFrame(tick);
  if (lastTs === null) lastTs = ts;
  const dtMs = Math.min(ts - lastTs, 250);   // clamp, so a tab switch can't jump
  lastTs = ts;
  if (!playing || !FRAMES.length) { return; }
  // Frames per wall-clock second to finish the replay in PLAY_SECONDS at 1x.
  const rate = (FRAMES.length - 1) / PLAY_SECONDS;
  cursor += (dtMs / 1000) * speed * rate;
  if (cursor >= FRAMES.length - 1) cursor -= FRAMES.length - 1;
  draw(cursor);
}

function setSpeed(mult) { speed = mult; }

document.getElementById('play').onclick = e => {
  playing = !playing; e.target.textContent = playing ? 'Pause' : 'Play';
};
document.getElementById('seek').oninput = e => {
  playing = false; document.getElementById('play').textContent = 'Play';
  lastOrder = null; marks.clear(); cursor = +e.target.value; draw(cursor);
};
document.getElementById('speed').onchange = e => setSpeed(+e.target.value);

// Load one race's data into the page. Everything per-race is set here — which is why
// the standalone page and the multi-race picker can share this file unchanged.
function applyRace(d) {
  FRAMES = d.frames; OUTLINE = d.outline; ROWS = d.rows;
  COLOURS = d.colours; PITLANE = d.pitlane; PITBOX = d.pitbox;
  W = d.w; H = d.h; DT = d.dt;
  LAPNUMS = d.lapNums || []; TOTAL_LAPS = d.totalLaps || 0;
  TRACK_W = d.trackw || 26; CAR_SCALE = d.carscale || 1;
  CAR_L = TRACK_W * CAR_L_RATIO; CAR_W = TRACK_W * CAR_W_RATIO;
  const cv = document.getElementById('c');
  cv.width = W; cv.height = H;
  buildTower();                     // this race's driver set
  laneScreen = laneArcScreen = null; TRACK_POS = null; GRID_POS = null;
  setRotation(d.rot);
  document.getElementById('seek').max = Math.max(0, FRAMES.length - 1);
  lastOrder = null; marks.clear(); cursor = 0;
  draw(0);
}

// ── Bootstrap ───────────────────────────────────────────────────────────────
// The page carries one JSON blob. Either it holds the race itself (standalone), or
// it asks for the race picker, which fetches its payloads on demand. That single
// `if` is the whole difference between the two pages.
const CONFIG = JSON.parse(document.getElementById('replay-data').textContent);

let INDEX = [], current = null;

function fillRaces(year) {
  const races = INDEX.filter(r => r.year === year)
                     .sort((a, b) => a.round - b.round);
  const sel = document.getElementById('pickRace');
  sel.innerHTML = races.map(r =>
    `<option value="${r.file}">R${r.round} · ${r.location}</option>`).join('');
  return races[0];
}

// Where the picker looks for payloads, as a URL path relative to the page. page.py
// supplies it, so the data location can move without editing this file.
const DATA_DIR = (CONFIG.dataDir || 'replays').replace(/\/$/, '') + '/';

async function loadRace(file) {
  document.getElementById('meta').textContent = 'loading…';
  const d = await (await fetch(DATA_DIR + file)).json();
  current = d;
  applyRace(d);
  // Lap X/Y lives in its own header slot (updated per frame by draw()), so the meta
  // line only carries what doesn't change during playback.
  document.getElementById('meta').textContent =
    `${d.running} running · ${d.retired} retired` +
    (d.full ? '' : ` · laps ${d.fromLap}–${d.fromLap + d.laps - 1}`);
}

async function startPicker() {
  INDEX = await (await fetch(DATA_DIR + 'index.json')).json();
  if (!INDEX.length) {
    document.getElementById('meta').textContent =
      'No replays yet — run: python3 src/vis/track_replay.py 2025 1';
    return;
  }
  const years = [...new Set(INDEX.map(r => r.year))].sort();
  document.getElementById('pickYear').innerHTML =
    years.map(y => `<option value="${y}">${y}</option>`).join('');
  const first = fillRaces(years[0]);
  await loadRace(first.file);
  raf = requestAnimationFrame(tick);

  document.getElementById('pickYear').onchange = async e => {
    const r = fillRaces(+e.target.value);
    if (r) await loadRace(r.file);
  };
  document.getElementById('pickRace').onchange = e => loadRace(e.target.value);
}

if (CONFIG.mode === 'picker') {
  startPicker();
} else {
  applyRace(CONFIG.race);
  raf = requestAnimationFrame(tick);
}
