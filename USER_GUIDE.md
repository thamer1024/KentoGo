# KentoGo user guide

This page tells how to use each screen of KentoGo, and what each setting means. The values in
brackets are the values at the first start. The names are those of the English screens.

## The top screen

The top screen has a button for each feature:

- **Mistake problems**: solve problems made from your own mistakes.
- **Local fight problems (life and death, boundaries)**: play again against KataGo the local fights
  you lost.
- **Look through games**: replay your games with the analysis.
- **Territory counting**: count the final positions of your games (only when "Also use the
  territory counting practice" is on in the settings).
- **Analyze games with KataGo**: let KentoGo analyze your games.
- **Analyze games with AI**: get a commentary in words from an AI such as Claude or ChatGPT.
- **Report**: your results day by day (mistake problems and local fights), and your mistakes game
  by game.

The ☰ button opens the menu: the flags (the language of the screens) and the settings screens.

## Mistake problems

### The start screen

KentoGo reads the games of the games folder and shows how many new problems and reviews there are
today, and how many more can be asked today. With staged problems, it also shows the stage. Press
"Start" (or Enter).

"Show the games that give no problems" lists the games where no problem was found, with the reason
(for example, the game is not analyzed).

### Solving a problem

1. The board shows the position before your mistake. Click the point where you would play.
2. KataGo judges the answer. The panel shows whether it is correct, the loss of your answer, the
   loss of the game move, and the part of the loss you won back.
3. Look at the sequences after your answer (see below), then press "Next problem" (or Enter).

You can press "Next problem" at any time, also while KataGo is still reading.
"Look at this game" opens the game of the problem in the game viewer, at that move.

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
   the moves of the opponent's rank (from KataGo's human-like model).
2. **Game**: the move played in the game, and the moves played after it.
3. **Best from here**: from the problem position, you play the best of the moves that a player of
   your rank may play, and the opponent plays the moves of the opponent's rank.

The newest move of a sequence is shown as a magenta disc; the moves before it have numbers. The
board shows the territory of the move shown, and the panel shows a rough standing. At the last move
of a sequence, the exact standing is shown. For "Rank replies" and "Best from here", it is also
compared with the game after the same number of moves (the points you won back).

### Offers to change the judging

After enough answers, KentoGo may ask whether to raise or lower the passing line, or to set or lower
the limit on the loss of a correct answer. Answer "Yes" to change the setting, or "No" to keep it.
See "Judging settings" below.

### Today

When you go back to the top screen after answering that day, "Today" shows the problems answered and
correct, the points got back, the number of the practice day and what you achieved, and how many of
the current problems there are in all, done, in progress and not started. Problems set aside are not
counted; reviews of problems no longer made from your games are counted as in progress.

## Local fight problems

KentoGo finds these problems when it analyzes your games: the life and death fights and the
boundaries you lost. KataGo is needed to play them.

1. The board shows the position where the fight started. Click your move; KataGo answers on the board.
2. Go on until the fight is judged. The panel tells whose turn it is and how the fight ended.
3. Press "Next problem" (or Enter) at any time.

The answer is correct when you win the fight and your score has not fallen from the start by more
than the allowed points. It is wrong when you lose the fight, when the score falls too much, when you
play away from the fight or pass, or when you lose points with a move that was not needed.

After a fight:

| Key | What it does |
| --- | --- |
| Tab | Show the AIs' sequence; when there are two, switch between them |
| → | One move forward |
| ← | One move back |
| Enter | Next problem |

In the AIs' sequence, both sides play human-like moves from the position where the fight started
until the place is settled (at 9 dan when no rank is known). When it does not settle the place,
KataGo's best moves play it again. A group being chased is followed until it is captured or gets away.

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
the recommended settings.

## Analyze games with AI

Choose one of three ways:

- **Paste mode (one game at a time)**: choose a game and your color, press "Make the prompt", then
  "Copy". Paste the prompt into the chat of any AI, copy its answer back into "The AI's answer",
  and press "Apply". The commentary is written into the game.
- **API mode (one game)**: KentoGo asks the AI directly with your API key (see "AI commentary
  settings" below). Choose a game and your color, and press "Ask the AI".
- **API mode (all new games)**: the games changed since the last run are listed (at the first run,
  you choose the date). Check the games and press "Ask the AI". "Exclude" hides a game from the list.

A game must be analyzed (by KaTrain or KentoGo) before an AI can explain it. A game that already has
a commentary is replaced only after you say yes.

## Report

The report counts practice days, so that days without practice do not pull the numbers down.

- **Mistake problems**: the problems answered, correct and finished, the points got back, the days of
  practice, and the last 5 practice days compared with the 5 before. The chart shows the correct
  answers and the average part won back of each practice day, with the passing line as a dotted line.
- **Local fight problems**: the same counts without the points, and a chart of the correct answers.
- **Mistakes in each game**: all your moves count, by the size of the loss, with the average of the
  last 5 games compared with the 5 before.

The charts show at most 14 practice days or games.

## The settings

The settings are opened from the ☰ menu. Press "Update Settings" to save them; they are used at
once. A change of the games folder or of the conditions for choosing problems makes KentoGo read all
games again at the next start of the quiz (it asks first).

### General and Engine Settings

**KataGo settings**

| Setting | Meaning |
| --- | --- |
| KaTrain's settings file (config.json) | Where KaTrain's settings are (`~/.katrain/config.json`). "Read from KaTrain" copies KataGo's paths and the engine values from it. |
| KaTrain's program folder | The folder of the KaTrain program, for paths that start with `katrain/` (empty: found automatically). |
| Path to KataGo executable | The KataGo program (empty: the one in the PATH, or the one that comes with KaTrain). |
| Path to KataGo model | The model used for all readings. On a Mac, use a b28c512nbt or b18c384nbt model. |
| Path to human-like model | KataGo's human-like model, for the rank replies (empty: not used). |
| Path to KataGo config file | KataGo's analysis settings file (KaTrain's `analysis_config.cfg`). |

**General Settings**

| Setting | Meaning |
| --- | --- |
| Games folder | The folder of your SGF files (empty: KentoGo's `games` folder). |
| My names | The names you use in your games, separated by commas (such as your name on a Go server). They tell which color is yours. |
| Also use the territory counting practice | Show the territory counting on the top screen (off). |

**Engine Settings**

| Setting | Meaning |
| --- | --- |
| Calculate with KataGo | Judge with KataGo the answers whose loss is not in the SGF file (on). |
| Max visits in analysis | How many positions KataGo reads to judge an answer (500). More is more exact but slower. |
| Wide root noise | Makes KataGo look at more candidate moves (0.04, as in KaTrain). |
| Maximum time for analysis | The most seconds for one reading (8; 0: no limit). |
| Visits for territory and standing | The visits of the territory and the rough standing; your later moves in "Best from here" use twice this (100). |
| Longest wait for KataGo to get ready | Seconds to wait for KataGo to load its model (600). |

### Recommended settings

Choose your kind of computer and press "Use": the visits for judging, for the territory and
standing, and for the analysis of games are set for it. "Measure" measures KataGo's speed with your
model and sets the visits from it; press it again after changing the model. The values aim at about
1.6 seconds for one reading and about two minutes for the analysis of a game.

### KataGo game analysis (written into the SGF)

| Setting | Meaning |
| --- | --- |
| Folder of the games to analyze | Empty: the games folder of the quiz. |
| Backup folder of the original games | Where each game is copied before it is written (empty: `backup` in the games folder). |
| Visits of the fast analysis | The visits of the first, shallow reading of every position (never fewer than 50). |
| Visits of the moves read deeply | The visits of the deep reading of the moves that can become problems (0: "Max visits in analysis"). |
| Most moves read deeply per game | How many moves are read deeply, the biggest losses first; the opponent's moves (for punishment problems) take at most half (6; 0: all). |
| Retries of positions that failed | How many times a position that KataGo could not read is asked again (2). |

### Problem and Judging Settings

**Problem settings**

| Setting | Meaning |
| --- | --- |
| Most problems a day | Problems asked in a day, reviews included; the count starts again at midnight (20; 0: no limit). |
| Problems per game | The most problems from one game, the biggest losses first (5). |
| Smallest loss (points) | Only moves that lost at least this many points become problems (3). |
| Staged problems: losses | Thresholds such as `20,10,5,3`: the problems that lost 20 points or more are asked first, then 10 or more, and so on. A stage ends when all its problems were answered correctly once (empty: off; then "Problems per game" and "Smallest loss" are not used). |
| Opening moves left out | Moves up to this number do not become problems (0). |
| Also ask moves that were taken back | Use the moves taken back in KaTrain's teaching games (off). |
| Winrate that decides the game (%) | In a position where one side's winrate is at least this, the moves become problems only when there are not enough others (99). |
| Lead that decides the game | The same, for a lead of more than this many points (40). |
| Order of problems | By file name, newest first, or random (by file name). |
| Rotate and flip the board | Show each problem rotated or flipped at random (off). |
| Swap the colors | Show each problem with black and white swapped at random (off). |
| Problems to ask | All problems, or only punishment problems (all). |
| Punishment problems: loss of the opponent's move before | A problem is a punishment problem when the opponent's move just before it lost at least this many points... (15) |
| Punishment problems: loss of your move | ...and your move lost at least this many points (5): you missed the chance to punish the opponent's mistake. |

**Judging settings**

| Setting | Meaning |
| --- | --- |
| Limit of a small problem (points) | A problem whose game move lost less than this is small: the answer is correct if it does not lose more than the game move (3). |
| Passing line (share won back, 0 to 1) | In other problems, the answer must win back at least this part of the loss (0.6: 60%). |
| Most points a correct answer may lose | In other problems, a correct answer may lose at most this many points (0: no limit). |
| Offer to change the pass ratio and the most points… | KentoGo offers to change the two values above to suit your latest answers (on). |
| Number of latest problems for the offers | How many of your latest answers the offers are made from, and how many new answers are needed before the next offer (30). |
| Steps of the most points a correct answer may lose | The limits offered one after another (`12,8,5,3`; empty: the limit is not offered). |
| Tolerance (points) | An answer that loses at most this many points is always correct (1). |

The losses are judged as they are shown (rounded to 0.1 points), and the part won back in whole
percent. The passing line is offered from 0.5 to 0.9, by steps of 0.1. A limit is offered when at
least a third of the latest answers are correct, their average loss is below the next limit, and at
least 80% of them are within it.

**Local fight problems (life and death, boundaries)**

| Setting | Meaning |
| --- | --- |
| Opponent | KataGo's strongest replies, or the human-like replies of the opponent's rank (KataGo's strongest replies). |
| Points the score may fall in a won fight before it is wrong | Counted from the start of the fight (3). |

### Review Settings

| Setting | Meaning |
| --- | --- |
| Way of reviewing | Forgetting curve (a problem ends after correct answers in a row), or ends after one correct answer (forgetting curve). |
| Correct answers in a row | With the forgetting curve, how many correct answers in a row finish a problem (2; 0: no reviews). A problem answered wrong comes back the next day, then after 3, 7, 14, 30 and 60 days. |
| Problems asked first | New problems, reviews of wrong answers, or a mix of two reviews and one new problem (new problems). |

**Review settings of the local fight problems (life and death, boundaries)**

| Setting | Meaning |
| --- | --- |
| Most problems a day | Fights asked in a day, reviews included; the count starts again at midnight (5; 0: no limit). |
| Way of reviewing | Forgetting curve, or ends after one correct answer (forgetting curve). |
| Correct answers in a row | With the forgetting curve, how many correct answers in a row finish a fight (2; 0: no reviews). |
| Problems asked first | New problems, reviews of wrong answers, or a mix of two reviews and one new problem (new problems). |

Buttons:

- **Set aside all current problems**: all problems of the games folder are treated as answered.
  Problems of games added later are still asked.
- **Bring all problems back**: problems set aside, and problems finished, are asked again as new.
  The answers are kept.
- **Clear the learning history**: the answers are cleared, after a backup in
  `~/.kentogo/backups`. The problems are then asked as for a new user.
- **Clear the local fight history**: the same for the answers of the local fight problems.
- **Clear the territory counting history** (when the counting practice is on): the same for the
  results of the counting practice.

### Territory Counting Settings

| Setting | Meaning |
| --- | --- |
| Most games a day | Games counted in a day; the count starts again at midnight (3; 0: no limit). |
| Order of games | By file name, newest first, or random (random). |
| Games asked first | Games never counted, games to count again, or a mix (games never counted). |
| Way of reviewing | Forgetting curve, or ends after one good count (forgetting curve). |
| Times done well in a row | With the forgetting curve, how many good counts in a row finish a game (2; 0: no reviews). |

### AI commentary

| Setting | Meaning |
| --- | --- |
| Kind of AI (API) | Claude (Anthropic), or OpenAI-compatible (ChatGPT, Gemini, DeepSeek, Ollama and others). |
| Model name | The AI's model, as the AI publishes it (claude-opus-5-5). |
| API address | The address of the API (empty: the AI's own). For an OpenAI-compatible AI other than ChatGPT, this chooses the AI. |
| Environment variable of the API key | The name of the variable that holds your API key (ANTHROPIC_API_KEY). The key itself is never saved. |
| Largest answer (tokens) | The longest answer the AI may give (15000). |

"Open the prompt file" opens your copy of the prompt, to change what the AI is asked. The API mode
needs the packages of the APIs (`uv sync --extra ai` when KentoGo runs from the source).
