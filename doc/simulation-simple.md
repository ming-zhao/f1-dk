# Simulation — Plain-Language Version

> **Audience label: FOR A HIGH SCHOOLER.** This explains the same thing as
> [simulation-technical.md](simulation-technical.md), just without assuming you know the code.

## The big idea

In this fantasy game you build a "lineup": you pick 1 Captain, 4 Drivers, and 1 Constructor
(the team that builds the car). You earn points based on how those picks do in a real F1 race.

The problem: you have to lock in your lineup *before* the race happens, so you don't know what
will actually occur. **Simulating** is our way of guessing. The computer invents one believable
race — who starts where, who finishes where, who crashes out, who leads laps, who sets the
fastest lap — and then scores your lineup using the real DraftKings scoring rules.

One made-up race isn't very useful, because racing is unpredictable. So we run the simulation
**thousands of times.** Each run is a little different, and together they show you the *range*
of things that could happen (great day, average day, disaster day) instead of a single guess.

> This is NOT the same as the "Testing AI" tab. That one uses races that *already happened* to
> check how a lineup would have scored. Simulation is for races that **haven't happened yet.**

## How one simulated race is built (5 steps)

The computer knows some season averages for each driver — like "on average this driver
qualifies around 5th," "usually finishes around 7th," "crashes/breaks down about 12% of the
time." It uses those averages, plus some randomness, to build a race:

1. **Starting grid (qualifying).** Each driver gets a starting spot near their usual qualifying
   position, nudged up or down a bit at random. The better the score, the closer to the front
   they start.
   - *Shortcut:* if you already typed in the *real* starting grid (because qualifying actually
     happened), the computer skips the guessing and just uses the real grid.
2. **Who breaks down (DNF).** Each driver gets a random "did they finish?" roll based on how
   often they normally have problems. Note: each driver is rolled separately, so the sim won't
   model a single crash taking out three cars at once.
3. **Finishing order.** For everyone who finished, the computer mixes two things — where they
   started and how they usually finish — leaning a bit more on their usual finishing habit.
   That decides the final running order. Drivers who broke down are placed at the back, ordered
   by roughly how far they got before stopping.
4. **Laps led.** The winner leads most of the race (somewhere between 45% and 80% of the laps),
   and the next few finishers split up the rest. Nobody outside the top 4 leads any laps.
5. **Fastest lap.** Picked at random from the top 10 finishers. Right now even a slow-but-
   finished 10th-place driver has the same chance as the leader — it's just luck of the draw.

## Why we do it this way

The main reason: this method is **fast**. It's simple enough that the computer can run it tens
of thousands of times in a second, which is exactly what's needed when the "Auto/AI" mode tries
tons of different lineups to find good ones. It also does a decent job of capturing how much
each driver bounces around from race to race, and it happily uses the real grid when you have it.

## What it's NOT good at yet (things we might improve later)

- **No "everyone has a bad day together."** In real life, rain or a big first-lap crash makes
  lots of drivers finish badly at once. Our sim treats each driver's bad luck separately.
- **No track personality.** Some tracks (like Monaco) barely let anyone overtake, so where you
  start ≈ where you finish. Others (like Monza) reward passing. The sim treats every track the
  same right now.
- **No real qualifying rounds.** Real qualifying has knockout rounds (Q1/Q2/Q3). We just make
  one quick guess for the grid instead.
- **No weather.** We even have weather notes saved, but the sim ignores them.
- **No tire strategy.** Same story — we track tire plans, but the sim doesn't use them.
- **Fastest lap and laps-led are basically luck**, not based on real speed.

## Room to grow

Right now there's just this one method. As we invent better ones, we'll add them here so you can
see what each new approach is trying to fix and how it works. Here's the first idea we're
planning.

## A future idea: simulating a street circuit (not built yet)

A **street circuit** is a race on normal city roads closed off for the weekend — Monaco,
Singapore, Baku, Las Vegas, Jeddah. The walls are right at the edge of the track, so there's no
grass or gravel to catch a car that makes a mistake. You slide off, you hit a wall.

The surprising thing when you look at the data: street circuits are **not all the same.** Two
totally different things are going on, and the simulator should handle them separately.

### 1. How hard it is to pass — depends on the exact track, not just "it's a street race"

- **Monaco is the single hardest place to overtake in all of F1** — only about **10–12 passes**
  happen in an entire race. It's so tight that where you *start* is basically where you
  *finish*. (The last time anyone passed *for the lead* on track was 1996!)
- **Singapore** is almost as tough.
- **BUT Baku, Jeddah, and Las Vegas are also street circuits and have TONS of passing**, because
  they have long straights where cars can slipstream by. Las Vegas had about **82 passes** in
  one race in 2023.
- So "street circuit" by itself tells you nothing about how much passing there'll be — you have
  to know the specific track.

### 2. How often something goes wrong — this part IS the same for all street circuits

Because the walls are so close, drivers crash more. A crash brings out the **safety car** (a
slow car that leads the pack around while marshals clean up the mess). The numbers:

- On a dry day, a street circuit brings out the safety car about **65%** of the time, versus
  only about **30%** at a normal track.
- **Singapore** brought out the safety car in *every single race* for 16 years straight
  (2008–2023).
- More crashes also means more cars **don't finish** (DNF).

### So we'd add two "dials" to the simulator

**Dial 1 — "where you start = where you finish."** For hard-to-pass tracks like Monaco, we'd
make the *starting grid* count for a lot more when deciding the finishing order — so qualifying
matters way more than usual. For easy-passing tracks like Baku or Las Vegas, we'd leave it about
normal.

**Dial 2 — "expect chaos."** For every street race we'd (a) raise everyone's chance of not
finishing, and (b) roll the dice on a safety car. If the safety car comes out, we'd let it take
out a couple of cars *at once* (a real pile-up — the current sim only ever crashes cars one at a
time, on their own), and shuffle the finishing order a bit, because a safety car lets drivers
make cheap pit stops and jump ahead of each other. That shuffle is exactly why street races are
so unpredictable — and why picking a surprise driver can pay off big in fantasy.

**Is this built yet?** Yes — it's now in the dashboard. It turns itself **on automatically**
whenever the loaded race is a street circuit (Monaco, Singapore, Baku, Las Vegas, Jeddah) and
stays completely off everywhere else, so a normal track behaves exactly like before. When it's
on, a red "Street circuit" tag shows at the top of every tab so you know the adjusted simulation
is running. Each track has its own two dial settings (Monaco is the stickiest and most chaotic;
Baku/Las Vegas pass easily but still crash a lot).

*(Numbers above come from public F1 stats: [Monaco overtakes](https://racingnews365.com/how-often-are-overtakes-at-the-monaco-grand-prix),
[2024 overtakes per race](https://www.threads.com/@f1statsguru/post/DENKaKHSOGC),
[Singapore safety cars](https://en.wikipedia.org/wiki/Marina_Bay_Street_Circuit),
[safety-car probability by track type](https://odds2win.bet/motorsports-betting/safety-car-betting/).)*
