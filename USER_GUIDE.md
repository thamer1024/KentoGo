# KentoGo user guide

<p><a href="japanese/USER_GUIDE.md">日本語のユーザーガイドはこちら</a></p>

This guide shows how to play with KentoGo, what each screen does, what happens when you change a
setting, and what to change when KentoGo is slow. The values in brackets are the values at the first
start. The names are those of the English screens.

## Contents

- [Your first day with KentoGo](#your-first-day-with-kentogo)
- [A day of practice](#a-day-of-practice)
- [Mistake problems](#mistake-problems)
- [Local fight problems](#local-fight-problems)
- [Look through games](#look-through-games)
- [Territory counting](#territory-counting)
- [Analyze games with KataGo](#analyze-games-with-katago)
- [Analyze games with AI](#analyze-games-with-ai)
- [Report](#report)
- [The settings](#the-settings)
- [When KentoGo is slow](#when-kentogo-is-slow)
- [Making the practice easier or harder](#making-the-practice-easier-or-harder)

## Your first day with KentoGo

You need KaTrain with its KataGo (KentoGo uses the same KataGo), and some games of your own as SGF
files. Then:

1. **Start KentoGo.** At the first start, KentoGo copies the paths of KataGo and its model from
   KaTrain's settings. A dialog shows KataGo loading; you can close it and go on.
2. **Tell KentoGo where your games are and who you are.** Open ☰ > "General and Engine Settings":
   - "Games folder": the folder of your SGF files.
   - "My names": the names you use in your games (such as your name on a Go server), separated by
     commas. KentoGo uses them to know which color is yours. Games played against the AI in KaTrain
     are recognized without them, but games from a Go server need them.
   Press "Update Settings".
3. **Fit KataGo to your computer.** Open ☰ > "Recommended settings". Choose your kind of computer and
   press "Use". If you do not know it, press "Measure": KentoGo measures KataGo's speed and sets the
   values from it. (See "When KentoGo is slow" if it is still slow.)
4. **Analyze your games.** Press "Analyze games with KataGo" on the top screen, keep the games that
   are checked, and press "Analyze the N chosen games". A game takes about two minutes. Games already
   analyzed in KaTrain can be used as they are, but only the games analyzed by KentoGo give local
   fight problems.
5. **Solve your first problems.** Back on the top screen, press "Mistake problems", then "Start".
6. **Try a local fight.** Press "Local fight problems (life and death, boundaries)" on the top
   screen.

If "Mistake problems" says there are no problems, press "Show the games that give no problems" on
its start screen: it tells why for each game (for example, the game is not analyzed, or your name is
not in "My names").

## A day of practice

KentoGo is made for a little practice every day. A good day looks like this:

1. After you play some games, put them into the games folder and analyze them ("Analyze games with
   KataGo").
2. Solve today's mistake problems (20 at most at first). Problems you missed come back tomorrow;
   problems you solved come back after some days, until you solve them twice in a row.
3. Play today's local fights (5 at most at first).
4. Go back to the top screen: "Today" shows what you did. Open "Report" now and then to see how you
   are doing over the days.

The daily limits start again at midnight. When a day's problems are done, KentoGo says so.

## Mistake problems

The moves where you lost the most points in your games become problems. Your task is to find a
better move than the one you played.

### The start screen

KentoGo reads the games of the games folder and shows how many new problems and reviews there are
today, and how many more can be asked today. With staged problems, it also shows the stage. Press
"Start" (or Enter).

"Show the games that give no problems" lists the games where no problem was found, with the reason.

### Solving a problem

1. The board shows the position just before your mistake. Think, then click the point where you
   would play.
2. KataGo judges your answer. The panel shows whether it is correct, the loss of your answer, the
   loss of the move played in the game, and how much of that loss you won back.
3. Look at the sequences after your answer (see below) to see why. Then press "Next problem" (or
   Enter).

You can press "Next problem" at any time, also while KataGo is still reading.
"Look at this game" opens the game of the problem in the game viewer, at that move.

**When is an answer correct?** In short: your answer must win back a good part of the loss of the
game move (60% at first). In a small problem (the game move lost less than 3 points), it is enough
not to lose more than the game move. An answer that loses at most 1 point is always correct. The
values can be changed (see "Judging settings").

### The sequences after your answer

| Key | What it does |
| --- | --- |
| Tab | Switch to the next sequence |
| Shift+Tab | Switch to the sequence before |
| → or Space | Play the sequence one move forward |
| ← or Shift+Space | Play the sequence one move back |
| Enter | Next problem |

The buttons "◀ Back", "Forward ▶" and "Switch sequence (Tab)" do the same. When you switch, the
name of the sequence is shown on the board for a moment, and its first move is played.

The sequences, in the order of Tab:

1. **Rank replies**: after your answer, you play the moves of your rank, and the opponent plays
   the moves of the opponent's rank (from KataGo's human-like model). It shows how the game could
   go on after your answer, between players of your strength.
2. **Game**: the move played in the game, and the moves played after it.
3. **Best from here**: from the problem position, you play the best of the moves that a player of
   your rank may play, and the opponent plays the moves of the opponent's rank. It shows a good move
   that is within your reach.

The newest move of a sequence is shown as a magenta disc; the moves before it have numbers. The
board shows the territory of the move shown, and the panel shows a rough standing. At the last move
of a sequence, the exact standing is shown. For "Rank replies" and "Best from here", it is also
compared with the game after the same number of moves (the points you won back).

Your rank comes from the game record (`BR`/`WR`), or else from the rank you gave for the AI
commentary. When neither rank is known, both sides play KataGo's best moves.

### Offers to change the judging

After enough answers, KentoGo may ask whether to raise or lower the passing line, or to set or lower
the limit on the loss of a correct answer. Answer "Yes" to change the setting, or "No" to keep it.
KentoGo makes the judging stricter as you get stronger; you never have to change it yourself.

### Today

When you go back to the top screen after answering that day, "Today" shows the problems answered and
correct, the points got back, the number of the practice day and what you achieved, and how many of
the current problems there are in all, done, in progress and not started. Problems set aside are not
counted; reviews of problems no longer made from your games are counted as in progress.

## Local fight problems

KentoGo finds these problems when it analyzes your games: the life and death fights and the
boundaries you lost. You play the fight again against KataGo, from the position where it started.
KataGo is needed to play them.

1. The board shows the position where the fight started. The panel tells the kind of practice (life
   and death, or boundary) and whose turn it is.
2. Click your move; KataGo answers on the board. Go on until the fight is judged.
3. Press "Next problem" (or Enter) at any time.

The answer is correct when you win the fight and your score has not fallen from the start by more
than the allowed points (3 at first). It is wrong when you lose the fight, when the score falls too
much, when you play away from the fight or pass, or when you lose points with a move that was not
needed. **Tip:** stay in the fight until it is settled, but do not add a move when the place is
already safe; KataGo playing elsewhere tells you the place is settled.

After a fight:

| Key | What it does |
| --- | --- |
| Tab | Show the AIs' sequence; when there are two, switch between them |
| → | One move forward |
| ← | One move back |
| Enter | Next problem |

In the AIs' sequence, both sides play human-like moves from the position where the fight started
until the place is settled (at 9 dan when no rank is known). It shows how the fight is usually played.
When it does not settle the place, KataGo's best moves play it again. A group being chased is followed
until it is captured or gets away. While KataGo makes a sequence, the seconds of its thinking are
shown; a sequence that takes too long is stopped there.

Your mistakes inside a local fight are not asked as mistake problems: the fight is asked instead.

When you go back to the top screen after answering that day, "Today" shows the problems answered and
correct, and how many of the current fights there are in all, done, in progress and not started.

## Look through games

Press "Choose a game" and choose a game ("Only games with AI commentary" shortens the list).

| Key | What it does |
| --- | --- |
| ← → (or Shift+Space, Space) | One move back or forward |
| ↑ ↓ | The previous or next move with an AI commentary |
| Home / End | The first or last move |
| Tab / Shift+Tab | Show the best line of the analysis, the other branches, then the game again |
| Esc | Back to the game |
| T | Turn the territory and the standing on or off |

The panel shows the move number, the loss of the move and the best move, the AI commentary and your
notes. The slider moves through the game. "Review" shows the AI's review of the whole game.

## Territory counting

Turn it on first: ☰ > "General and Engine Settings" > "Also use the territory counting practice".
Then press "Territory counting" on the top screen. You count the final position of your own games
with the Japanese rules.

1. Click the dead stones (connected stones become dead together; click again to undo).
2. Press "Take off the dead stones", or drag them out of the board.
3. Click the dame to fill them with stones (click again to take a stone back).
4. Press "Confirm the end and start counting".
5. Tidy the territories: drag stones to empty points, drop a stone on a stone of the other color
   to swap them, and drag the prisoners from below the board into the territory of the same color.
   An empty point whose owner is not clear any more can be set by clicking it.
6. Press "Finish the seichi" to check your count.
7. Press "Done well" or "Not done well". A game not done well is asked again on a later day.

"Show the computer's counting" plays the computer's steps (as a reference). "▶ Play", "■ Stop" and
the ← → keys go through them. "Undo" takes back your last step, and "Back to the final position"
starts again.

## Analyze games with KataGo

1. The games of the games folder are listed. The games not analyzed yet are checked.
   "Also show the games analyzed by KentoGo" lists them too, to analyze them again.
   "Check all" and "Uncheck all" change all the checks.
2. Press "Analyze the N chosen games". The progress of each game is shown. A run can be stopped;
   it stops after the game being analyzed.

Each game is copied to the backup folder before it is written. A game takes about two minutes with
the recommended settings. You can analyze many games at once and let it run while you do something
else.

## Analyze games with AI

An AI such as Claude or ChatGPT explains in words why a move was a mistake. Choose one of three ways:

- **Paste mode (one game at a time, no API key needed)**: choose a game and your color, press "Make
  the prompt", then "Copy". Paste the prompt into the chat of any AI, copy its answer back into "The
  AI's answer", and press "Apply". The commentary is written into the game.
- **API mode (one game)**: KentoGo asks the AI directly with your API key (see "AI commentary"
  below). Choose a game and your color, and press "Ask the AI".
- **API mode (all new games)**: the games changed since the last run are listed (at the first run,
  you choose the date). Check the games and press "Ask the AI". "Exclude" hides a game from the list.

A game must be analyzed (by KaTrain or KentoGo) before an AI can explain it. A game that already has
a commentary is replaced only after you say yes. Read the commentary in "Look through games".

## Report

The report counts practice days, so that days without practice do not pull the numbers down.

- **Mistake problems**: the problems answered, correct and finished, the points got back, the days of
  practice, and the last 5 practice days compared with the 5 before. The chart shows the correct
  answers and the average part won back of each practice day, with the passing line as a dotted line.
- **Local fight problems**: the same counts without the points, and a chart of the correct answers.
- **Mistakes in each game**: all your moves count, by the size of the loss, with the average of the
  last 5 games compared with the 5 before. Fewer big mistakes over the games means your practice is
  working.

The charts show at most 14 practice days or games.

## The settings

The settings are opened from the ☰ menu. Press "Update Settings" to save them; they are used at
once. A change of the games folder or of the conditions for choosing problems makes KentoGo read all
games again at the next start of the quiz (it asks first).

The tables below tell what each setting does and what happens when you change it.

### General and Engine Settings

**KataGo settings**

These are usually copied from KaTrain; change them only when KataGo cannot be started.

| Setting | What it does |
| --- | --- |
| KaTrain's settings file (config.json) | Where KaTrain's settings are (`~/.katrain/config.json`). "Read from KaTrain" copies KataGo's paths and the engine values from it again. |
| KaTrain's program folder | The folder of the KaTrain program, for paths that start with `katrain/` (empty: found automatically). Set it when KentoGo says it cannot find KataGo. |
| Path to KataGo executable | The KataGo program (empty: the one in the PATH, or the one that comes with KaTrain). |
| Path to KataGo model | The model used for all readings. A smaller model (such as b18c384nbt) is faster; a larger one (b28c512nbt) is stronger. On a Mac, use a b28c512nbt or b18c384nbt model. Press "Measure" after changing it. |
| Path to human-like model | KataGo's human-like model, for the rank replies and the AIs' sequences (empty: not used). |
| Path to KataGo config file | KataGo's analysis settings file (KaTrain's `analysis_config.cfg`). |

**General Settings**

| Setting | What it does |
| --- | --- |
| Games folder | The folder of your SGF files (empty: KentoGo's `games` folder). |
| My names | The names you use in your games, separated by commas. They tell which color is yours. Add every name you use on Go servers, or those games may give no problems. |
| Also use the territory counting practice | Show "Territory counting" on the top screen (off). |

**Engine Settings**

| Setting | What it does | When you change it |
| --- | --- | --- |
| Calculate with KataGo | Judge with KataGo the answers whose loss is not in the SGF file (on). | Off: only answers already read in the analysis can be judged. Keep it on. |
| Max visits in analysis | How many positions KataGo reads to judge an answer, and for each move of the local fights (500). | More: more exact, but each answer takes longer. Fewer: faster, but the judging is rougher. The time is about in proportion to the visits. |
| Wide root noise | Makes KataGo look at more candidate moves (0.04, as in KaTrain). | Leave it as it is. |
| Maximum time for analysis | The most seconds for one reading of the mistake problems (8; 0: no limit). | Lower it to cut the longest waits on a slow computer: KataGo then reads fewer positions in that time. It does not limit the local fights. |
| Visits for territory and standing | The visits of the territory and the rough standing after an answer; your later moves in "Best from here" use twice this (100). | Fewer: the territory and the sequences come faster, but are rougher. |
| Longest wait for KataGo to get ready | Seconds to wait for KataGo to load its model (600). | Raise it when KentoGo gives up while KataGo is still starting (a slow computer, or KataGo's first start). |

### Recommended settings

Choose your kind of computer and press "Use": the visits for judging, for the territory and
standing, and for the analysis of games are set for it. "Measure" measures KataGo's speed with your
model and sets the visits from it; press it again after changing the model. The values aim at about
1.6 seconds for one reading and about two minutes for the analysis of a game.

| Kind of computer | Judging | Territory and standing |
| --- | --- | --- |
| No GPU, older CPU | 16 | 4 |
| No GPU, newer CPU | 40 | 10 |
| GPU, entry to mid-range | 480 | 120 |
| GPU, high-end | 1600 | 400 |
| Mac, standard | 80 | 20 |
| Mac, fast | 160 | 40 |
| Mac, very fast | 360 | 90 |
| Mac, fastest | 960 | 240 |

These replace only the numbers of visits; the paths of KataGo and its models stay as they are.

### KataGo game analysis (written into the SGF)

| Setting | What it does | When you change it |
| --- | --- | --- |
| Folder of the games to analyze | Empty: the games folder of the quiz. | |
| Backup folder of the original games | Where each game is copied before it is written (empty: `backup` in the games folder). | |
| Visits of the fast analysis | The visits of the first, shallow reading of every position (never fewer than 50). | More: the mistakes are found more surely, but the analysis takes longer. |
| Visits of the moves read deeply | The visits of the deep reading of the moves that can become problems (0: "Max visits in analysis"). | More: the losses of the problems are more exact, but the analysis takes longer. |
| Most moves read deeply per game | How many moves are read deeply, the biggest losses first; the opponent's moves (for punishment problems) take at most half (6; 0: all). | Fewer: faster, but fewer problems from each game. 0 reads all of them, which can take long. |
| Retries of positions that failed | How many times a position that KataGo could not read is asked again (2). | |

### Problem and Judging Settings

**Problem settings**

| Setting | What it does | When you change it |
| --- | --- | --- |
| Most problems a day | Problems asked in a day, reviews included; the count starts again at midnight (20; 0: no limit). | Lower it for shorter days of practice. With many reviews, a low limit can leave no room for new problems. |
| Problems per game | The most problems from one game, the biggest losses first (5). | More: more problems, also smaller mistakes. |
| Smallest loss (points) | Only moves that lost at least this many points become problems (3). | Higher: only the big mistakes. Lower: also the small ones (more problems, and harder to judge). |
| Staged problems: losses | Thresholds such as `20,10,5,3`: the problems that lost 20 points or more are asked first, then 10 or more, and so on. A stage ends when all its problems were answered correctly once (empty: off; then "Problems per game" and "Smallest loss" are not used). | Use it to fix the biggest mistakes first. |
| Opening moves left out | Moves up to this number do not become problems (0). | Raise it (for example to 20) if you do not want to practice the opening. |
| Also ask moves that were taken back | Use the moves taken back in KaTrain's teaching games (off). | |
| Winrate that decides the game (%) | In a position where one side's winrate is at least this, the moves become problems only when there are not enough others (99). | Lower: fewer problems from games that were already decided. |
| Lead that decides the game | The same, for a lead of more than this many points (40). | |
| Order of problems | By file name, newest first, or random (by file name). | "Newest first" practices your latest games first. |
| Rotate and flip the board | Show each problem rotated or flipped at random (off). | On: you cannot remember the answer from the look of the board. |
| Swap the colors | Show each problem with black and white swapped at random (off). | |
| Problems to ask | All problems, or only punishment problems (all). | |
| Punishment problems: loss of the opponent's move before | A problem is a punishment problem when the opponent's move just before it lost at least this many points... (15) | Lower: more punishment problems. |
| Punishment problems: loss of your move | ...and your move lost at least this many points (5): you missed the chance to punish the opponent's mistake. | |

**Judging settings**

| Setting | What it does | When you change it |
| --- | --- | --- |
| Limit of a small problem (points) | A problem whose game move lost less than this is small: the answer is correct if it does not lose more than the game move (3). | |
| Passing line (share won back, 0 to 1) | In other problems, the answer must win back at least this part of the loss (0.6: 60%). | Higher: stricter. 0.8 means your answer must win back 80% of the loss. |
| Most points a correct answer may lose | In other problems, a correct answer may lose at most this many points (0: no limit). | Set it (for example 5) to stop a big problem from being passed with a move that still loses much. |
| Offer to change the pass ratio and the most points… | KentoGo offers to change the two values above to suit your latest answers (on). | Off: the values stay as you set them. |
| Number of latest problems for the offers | How many of your latest answers the offers are made from, and how many new answers are needed before the next offer (30). | |
| Steps of the most points a correct answer may lose | The limits offered one after another (`12,8,5,3`; empty: the limit is not offered). | |
| Tolerance (points) | An answer that loses at most this many points is always correct (1). | Lower: stricter for nearly good answers. |

The losses are judged as they are shown (rounded to 0.1 points), and the part won back in whole
percent. The passing line is offered from 0.5 to 0.9, by steps of 0.1. A limit is offered when at
least a third of the latest answers are correct, their average loss is below the next limit, and at
least 80% of them are within it.

**Local fight problems (life and death, boundaries)**

| Setting | What it does | When you change it |
| --- | --- | --- |
| Opponent | KataGo's strongest replies, or the human-like replies of the opponent's rank (KataGo's strongest replies). | "Human-like replies": the opponent plays like a person of that rank, which is easier and closer to your real games. |
| Points the score may fall in a won fight before it is wrong | Counted from the start of the fight (3). | Higher: easier (a win that costs some points is still correct). Lower: you must win without losing points. |

### Review Settings

| Setting | What it does | When you change it |
| --- | --- | --- |
| Way of reviewing | Forgetting curve (a problem ends after correct answers in a row), or ends after one correct answer (forgetting curve). | "One correct answer": fewer reviews, more new problems. |
| Correct answers in a row | With the forgetting curve, how many correct answers in a row finish a problem (2; 0: no reviews). A problem answered wrong comes back the next day, then after 3, 7, 14, 30 and 60 days. | 3 or more: you remember the problems longer, but each takes more reviews. |
| Problems asked first | New problems, reviews of wrong answers, or a mix of two reviews and one new problem (new problems). | "Reviews of wrong answers" when the reviews pile up. |

**Review settings of the local fight problems (life and death, boundaries)**

| Setting | What it does |
| --- | --- |
| Most problems a day | Fights asked in a day, reviews included; the count starts again at midnight (5; 0: no limit). |
| Way of reviewing | Forgetting curve, or ends after one correct answer (forgetting curve). |
| Correct answers in a row | With the forgetting curve, how many correct answers in a row finish a fight (2; 0: no reviews). |
| Problems asked first | New problems, reviews of wrong answers, or a mix of two reviews and one new problem (new problems). |

They work as the review settings of the mistake problems above.

Buttons:

- **Set aside all current problems**: all problems of the games folder are treated as answered.
  Problems of games added later are still asked. Use it to start fresh with your new games.
- **Bring all problems back**: problems set aside, and problems finished, are asked again as new.
  The answers are kept.
- **Clear the learning history**: the answers are cleared, after a backup in
  `~/.kentogo/backups`. The problems are then asked as for a new user.
- **Clear the local fight history**: the same for the answers of the local fight problems.
- **Clear the territory counting history** (when the counting practice is on): the same for the
  results of the counting practice.

### Territory Counting Settings

| Setting | What it does |
| --- | --- |
| Most games a day | Games counted in a day; the count starts again at midnight (3; 0: no limit). |
| Order of games | By file name, newest first, or random (random). |
| Games asked first | Games never counted, games to count again, or a mix (games never counted). |
| Way of reviewing | Forgetting curve, or ends after one good count (forgetting curve). |
| Times done well in a row | With the forgetting curve, how many good counts in a row finish a game (2; 0: no reviews). |

### AI commentary

| Setting | What it does |
| --- | --- |
| Kind of AI (API) | Claude (Anthropic), or OpenAI-compatible (ChatGPT, Gemini, DeepSeek, Ollama and others). |
| Model name | The AI's model, as the AI publishes it (claude-opus-5-5). |
| API address | The address of the API (empty: the AI's own). For an OpenAI-compatible AI other than ChatGPT, this chooses the AI. |
| Environment variable of the API key | The name of the variable that holds your API key (ANTHROPIC_API_KEY). The key itself is never saved. |
| Largest answer (tokens) | The longest answer the AI may give (15000). |

"Open the prompt file" opens your copy of the prompt, to change what the AI is asked. The API mode
needs the packages of the APIs (`uv sync --extra ai` when KentoGo runs from the source). The paste
mode needs no API key and costs nothing beyond the AI's chat.

## When KentoGo is slow

How long KataGo takes depends very much on the computer: a GPU is 30 to 100 times faster than a
processor alone. Go through these steps in order, and stop when it is fast enough.

### Step 1: use the recommended settings

Open ☰ > "Recommended settings" and press "Measure" (or choose your kind of computer and press
"Use"). This sets the visits so that one reading takes about 1.6 seconds and a game is analyzed in
about two minutes. Press "Measure" again after you change the model.

### Step 2: use a model that is fast on your computer

The models whose names start with tf3 are fast only on an NVIDIA RTX with the CUDA or TensorRT version
of KataGo. Elsewhere (the KataGo that comes with KaTrain, GTX, Radeon or built-in GPUs, computers
without a GPU, Macs), use a b18c384nbt model (faster) or a b28c512nbt model (stronger), in "Path to
KataGo model". For example, on a base M5 Mac, a tf3 model read about 170 visits a second, b28 about
420 and b18 about 960. Then press "Measure" again.

### Step 3: lower the visits where it is slow

KataGo's time is about in proportion to the visits: half the visits, about half the time. Lower
the value by half at a time, and try again. Fewer visits make the readings rougher, so lower only the
value of the part that is slow.

| Where it is slow | What to change (under ☰ > "General and Engine Settings", unless named) | How much |
| --- | --- | --- |
| The judging after an answer (mistake problems) | "Max visits in analysis" | Half (for example 500 → 250). Or set "Maximum time for analysis" to 3 or 4: an answer then takes at most about three times that. |
| The territory, the standing and the sequences after an answer | "Visits for territory and standing" | Half (for example 100 → 50). "Best from here" uses twice this value for your later moves. |
| KataGo's replies in a local fight | "Max visits in analysis" ("Maximum time for analysis" does not limit the local fights) | Half. |
| The AIs' sequence after a local fight ("KataGo is slow to answer, so the sequence stops here") | "Max visits in analysis" | Half, until the sequence ends with a result. |
| The analysis of a game (more than a few minutes) | ☰ > "KataGo game analysis": "Visits of the fast analysis" and "Visits of the moves read deeply" | Half each. The fast analysis never reads fewer than 50. You can also set "Most moves read deeply per game" to 3 (fewer problems a game). |

### Step 4: when KataGo itself is slow to start

KataGo loads its model when KentoGo starts. A larger model takes longer, and with some versions of
KataGo, the first start tunes itself for the GPU, which can take some minutes (only once). KentoGo
shows how long it will still take from the second start on. When KentoGo gives up while KataGo is
still starting, raise "Longest wait for KataGo to get ready" (for example 600 → 1200).

### A computer without a GPU

Without a GPU, KataGo reads only some tens of positions a second, so the recommended settings use
few visits (16 or 40 for judging), and the analysis of a game takes longer than two minutes. It still
works: analyze the games while you do something else (for example overnight), use a b18c384nbt model,
and choose "No GPU, older CPU" or "No GPU, newer CPU" in "Recommended settings".

## Making the practice easier or harder

| You want | Change |
| --- | --- |
| Only the big mistakes | Raise "Smallest loss (points)" (for example 3 → 8), or use "Staged problems: losses". |
| A stricter judging | Raise "Passing line" (0.6 → 0.8), set "Most points a correct answer may lose", or leave the offers on: KentoGo raises the line as you get stronger. |
| An easier judging | Lower "Passing line" (0.6 → 0.5), or raise "Tolerance (points)". |
| Shorter days | Lower "Most problems a day" (mistake problems) and "Most problems a day" of the local fights. |
| More reviews (to remember longer) | Raise "Correct answers in a row" (2 → 3). |
| Easier local fights | "Opponent": "Human-like replies of the opponent's rank", and raise the allowed points (3 → 5). |
| Not to remember the answers by the look of the board | Turn on "Rotate and flip the board" and "Swap the colors". |
