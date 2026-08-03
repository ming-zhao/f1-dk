# AI Simulation — requirements

Plain-language record of what the **AI Simulation** tab
(`dashboard/index.html`) is supposed to do, as specified by the user. This is the
"what and why"; the code that implements it lives in the `// ---------- AI
simulation` section of `dashboard/index.html`. Keep this file in sync when the
behaviour changes.

## The "description" a lineup must fit

A lineup **fits the description** when it is a *valid* lineup: every driver **and**
the constructor has a solo chance **greater than** the current **Min pick chance**
bar (`MIN_PICK_CHANCE`) of hitting its best-case break. The bar is set by the
dropdown next to the "AI Simulation" title (see below).

## The three jobs, in priority order

1. **First job — find a lineup that fits the description.** Produce a valid lineup
   where every pick clears the Min pick chance bar. Invalid lineups (some pick
   below the bar) are marked not-valid and actively repaired/swapped until they
   fit. *(Code: `updateAiChances()` sets `AI.visible[i]`; `performAiSwaps()` +
   `repairFailingLineup()` fix the ones that fall short.)*

2. **Second job — find the best lineup that fits the description.** Among the
   valid lineups, the one with the highest simulated average score becomes first
   place ("the champion"). Valid lineups always rank above invalid ones. *(Code:
   `computeAiOrder()` + `maybePromoteChampion()`.)*

3. **Third job — once a lineup is found, just keep running simulations on it**
   while the other "agent" keeps building/adjusting lineups. First place is not
   thrown away; it keeps accumulating simulations continuously in the background.
   Meanwhile a separate pass keeps constructing, repairing, and swapping the other
   candidate lineups. *(Code: `aiTick()` every 400 ms keeps simulating the
   champion; the `updateAiChances()`/`performAiSwaps()` pass every 2 s is the
   "other agent" that makes/repairs lineups.)*

## Rule for keeping fitting lineups (don't change them too early)

- **When a lineup fits the requirement, don't change it — just keep running sims
  on it — until 10 lineups fit.** A lineup that already fits is never deleted or
  swapped out while fewer than 10 fit; it stays put and keeps being simulated. Only
  the slots that *don't* yet fit are worked on during this phase.
- **Once 10 lineups fit, changing is allowed.** From that point the search may
  start upgrading the weakest fitting slots toward the best (pulling better
  candidates in). If enough fitting lineups later fall below the bar so that fewer
  than 10 fit again, upgrading pauses and the search goes back to just filling.
- *(Code: `performAiSwaps()` gates its upgrade path on
  `canOptimize = fitCount >= AI_OPTIMIZE_MIN_FIT`, where `AI_OPTIMIZE_MIN_FIT = 10`.)*
- **A confirmed-fitting lineup is LOCKED for the run and can never be thrown away
  by noise.** This is the core guarantee. Whether a lineup fits is read from a
  light 300-sim chances pass, which is noisy — a lineup whose weakest pick sits
  near the bar keeps reading sub-bar by chance on later passes, and a one-time
  re-check isn't enough (a borderline lineup keeps failing the re-check too, so it
  still gets discarded). Since the Min-pick-chance bar can't change mid-run (its
  dropdown is disabled while running), a lineup's *true* fit status is fixed — only
  the estimate wobbles. So the moment a lineup is CONFIRMED fitting (a light-pass
  fit re-verified by a big reliable pass), it is locked: kept, simulated, and never
  re-evaluated out of existence for the rest of the run. A lock is only released if
  the optimize phase (10+ fit) deliberately swaps that slot for an upgrade, at which
  point the new lineup must re-earn its own lock. *(Code: `AI.fitLocked[]`, set in
  `updateAiChances()` on a confirmed fit, reset in `seedAiSlot()`; a locked slot
  stays `AI.visible = true` and skips re-evaluation.)*
- **A kept fitting lineup is ranked number one — above every lineup that does NOT
  fit — even if its average is lower than those non-fitting lineups.** A lineup
  that fits always outranks every lineup that doesn't, regardless of average, so
  whenever at least one lineup fits, rank 1 (number one) is a fitting lineup and
  never a higher-average non-fitting one. *(Code: the `displayOrder` partition in
  `renderAiResults()` lists all fitting lineups before all non-fitting ones.)*

## Rules for first place (the champion)

- **Don't change first place once it's found.** Keep running simulations on it.
- **Only change it if another lineup has a higher average.** A challenger takes
  first place solely by posting a strictly higher simulated average (it must have
  enough sims of its own first so the average is real, not a lucky flash). No
  confidence margin beyond that.
- **If first place has a pick below the bar, fix that lineup so it fits.** When the
  1st-place lineup has a driver/constructor under the Min pick chance bar (and the
  failure is confirmed, not a one-pass flicker), repair it in place — swap only the
  offending pick, keep the rest — so first place always has every pick above the
  bar. If no legal in-place repair exists, hand first place to another valid
  lineup instead.

## Min pick chance dropdown

- A dropdown sits **next to the "AI Simulation" title**, ranging **5% to 20%**.
- The chosen percent is the bar every pick must beat for a lineup to fit the
  description.
- The dropdown is **locked (disabled) while a simulation is running**, and is only
  editable when the AI simulation is **stopped**. A changed value takes effect on
  the next Start.

## Also

- **Write the given information down in a file** — this document.
