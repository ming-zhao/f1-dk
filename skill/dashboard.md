# Dashboard Skill

How to build, rebuild, and troubleshoot `dashboard/index.html`. For what the
dashboard actually does (UI, lineup rules, simulation, scoring), see
[`doc/dashboard.md`](../doc/dashboard.md) — read that first if you haven't
touched this dashboard before.

---

## Golden rule

`dashboard/data.js` is **generated** (see the "do not edit by hand" header in
the file itself). Never hand-edit it — edit `dashboard/build_data.py`, its
inputs, or `config/scoring.yaml` / `config/race_notes.yaml`, then regenerate.

## Rebuild workflow

Full refresh (new race week, or after any pipeline change):

```bash
python3 src/data/data_crawler.py   # crawl all sources -> data/raw/<source>/<year>/
python3 src/sim/dk_points.py           # DK points per driver/constructor
python3 src/data/data_crawler.py --source draftkings   # this week's salaries
python3 dashboard/build_data.py    # regenerate dashboard/data.js
```

Just changed `build_data.py`, `scoring.yaml`, or `race_notes.yaml` and the
CSVs are already fresh? Only the last step is needed:

```bash
python3 dashboard/build_data.py
```

Then reload `dashboard/index.html` in the browser (plain file, no server —
open directly, or hard-refresh if it was already open since `data.js` is
loaded via `<script src>` and browsers can cache it).

## Verifying it worked

Don't just eyeball the page — confirm `data.js` actually parses and loaded:

```bash
python3 -c "
import re, json
src = open('dashboard/data.js', encoding='utf-8').read()
m = re.search(r'const F1DATA = (.*);\s*\$', src, re.S)
data = json.loads(m.group(1))
print('drivers:', len(data['drivers']), 'constructors:', len(data['constructors']),
      'race:', data['raceName'])
"
```

In-browser check (devtools console or an automated browser tool):

```js
typeof F1DATA !== 'undefined'
  ? {drivers: F1DATA.drivers.length, constructors: F1DATA.constructors.length}
  : 'F1DATA undefined — data.js missing, failed to load, or has a syntax error'
```

**Testing UI logic (add/remove/simulate) needs a real page load, not just a
static file view.** Opening `index.html` via `file://` works for the static
sandboxed browser preview used in this project, but that preview renders
`file://` pages as a static snapshot and never executes `<script src="data.js">`
— `F1DATA` stays undefined and nothing is testable. To actually exercise the
app, serve the folder over HTTP:

```bash
python3 -m http.server 8791 --directory dashboard
```

or use the `f1-dk-dashboard` entry in `.claude/launch.json` (already
configured — `preview_start` with name `f1-dk-dashboard`). Then interact with
it for real (click buttons, or drive `addDriver()` / `remove()` from the
console) rather than trusting the code by inspection alone.

If the driver/constructor tables render empty, it's almost always one of:
`data.js` doesn't exist yet (pipeline never run), it's stale, or it failed to
parse.

## Known pitfalls

- **Client-side JS bugs are easy to miss by reading alone (fixed, watch for
  regressions):** `renderLineup()` in `index.html` called an `emptyRow()`
  helper that didn't exist, so every render threw a `ReferenceError` — the
  lineup panel never actually updated (the salary tiles you saw were just
  static HTML), the Simulate button could never enable, and there was also a
  second, broken `remove()` function later in the file silently shadowing the
  correct one via function-hoisting. Symptom reported by a user: "can't
  remove drivers." Root cause only showed up by loading the page for real
  (see the HTTP-server note above) and watching the console — reading the
  code in isolation looked plausible. If you touch `renderLineup`, `slotRow`,
  `emptyRow`, or `remove`, retest by actually adding/removing picks and
  confirming Simulate enables on a legal, in-cap lineup.
- **Stale `data.js` served after a rebuild, even on a fresh tab/server restart:** if you rebuild
  `data.js` mid-session and the sandboxed browser preview keeps serving the old content (check
  with `JSON.stringify(Object.keys(D.raceNotes))` or similar — compare against the actual file),
  a plain reload or even stopping/restarting the `preview_start` server on the *same port* isn't
  guaranteed to bust it. Changing the port in `.claude/launch.json` and restarting forces a
  genuinely fresh load. A direct `curl`/`Bash` fetch of the file will show the correct fresh
  content even while the browser tool is still stale — don't let that fool you into thinking the
  file itself is wrong.
- **Windows encoding bug (fixed, watch for regressions):** `build_data.py`
  writes `data.js` with `Path.write_text(...)`. Always pass
  `encoding="utf-8"` explicitly — without it, Windows defaults to cp1252 and
  non-ASCII characters (e.g. the em dash in the header comment) get written
  as invalid bytes, corrupting the file.
- **No Python on a fresh machine:** the pipeline needs Python 3 +
  `pandas`, `pyyaml`, `requests`. There's no `requirements.txt` yet — install
  those three manually if missing.
- **`data/` and `dashboard/data.js` are gitignored.** They're always
  generated locally, never pulled from git — don't go looking for them in
  history.
- **Stale `race_notes.yaml`:** `build_data.py` warns (doesn't fail) if
  `config/race_notes.yaml`'s `race:` field doesn't match the current DK
  salary file's competition name. Update it for the current race, or ignore
  the warning if notes aren't ready yet.
- **Missing driver/team mappings:** `build_data.py` prints
  `WARNING: unmapped driver/team skipped` for any DK salary row it can't map
  via `NAME_TO_CODE` / `DK_ABBREV_TO_ID` / `TEAMS` in `src/util/common.py` (e.g. a
  rookie or a new team abbreviation DK uses). Fix by adding the mapping in
  `src/util/common.py`, not by patching `data.js`.

## Editing the dashboard UI itself

`dashboard/index.html` is a single self-contained file: `<style>` block,
static markup, then a `<script>` with all app logic (state, rendering, race
simulation, DK scoring). No build step, no bundler, no framework — edit the
file directly and reload.

- Keep new driver/constructor fields flowing through `build_data.py`'s
  `payload` dict if the UI needs new data — don't invent fields client-side
  that aren't in `data.js`.
- Scoring math must mirror `config/scoring.yaml` — if scoring rules change,
  update the yaml (source of truth) and confirm `SC_D` / `SC_C` usage in the
  script still lines up; don't hardcode point values in the HTML/JS.
- Re-read `doc/dashboard.md` and update it if you change lineup rules, the
  simulation model, or the scoring breakdown — keep the two in sync.

## Viewing a race replay

**Open `dashboard/replay.html`. That's it — double-click it, no server.**

It reads `data/replay/index.js` and the per-race payloads beside it. If it says no
replays are built yet, build some:

```bash
script/replay_data_builder.sh            # a couple of sample races
script/replay_data_builder.sh 2025 1     # one specific race
script/replay_data_builder.sh 2025       # every crawled round of a season
```

### Why the payloads are `.js`, not `.json`

`fetch()` is blocked on a `file://` origin (opaque origin, so CORS denies it) but a
`<script>` tag is exempt. So each payload is written as `window.REPLAY_RACE = {...}`
and loaded by injecting a script tag. Same reason `dashboard/index.html` has always
worked by double-clicking — it loads `data.js` through a script tag.

The page used to `fetch()` JSON, so double-clicking it gave a blank screen and it had
to be served over HTTP. That was a bug, not a constraint.

Trade-off: a script tag reports nothing until it has run, so a slow ~3 MB load shows
`loading…` with no percentage.

`--standalone` still exists and inlines one race into a ~3 MB self-contained file:

```bash
python3 src/vis/track_replay.py 2025 1 --full --standalone
```

That is now only useful for emailing a single race as one file; it's gitignored.
