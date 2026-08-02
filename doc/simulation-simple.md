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
see what each new approach is trying to fix and how it works.
