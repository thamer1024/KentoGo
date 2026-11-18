"""The log of the human-like moves of the user in the sequence from the problem position.

For each move of the user that is chosen among the moves that a human of the user's rank may play (see
quiz.natural_move), JSON objects are told, one on each line (JSON Lines), so that a program can read them:

- on the console (stderr), after the prefix LINE_PREFIX;
- appended to the log file LOG_PATH (~/.kentogo/human_line.jsonl), when it can be written.

The keys of every record: "time" (the local time, ISO 8601), "problem" (the problem's ID), "line" (the sequence:
"rank" or "best"), "event". The records of a move also have: "number" (the number of the move in the sequence),
"color", "chosen" (the move), "visits" (read for it).

"human_best_move" (the choice) also has: "how" ("only": one candidate; "search": the least loss in KataGo's reading
of the candidates; "fallback": KataGo read none of them, so the most likely one), "chosen_loss" (its points lost
against the best candidate, or null), "seconds" (the time of the reading) and "candidates" (each with its "move",
its "chance" in the human-like policy and its "loss").

"human_best_reference" (told when the sequence has ended) has: "best" (KataGo's best move when it reads without a
limit) and "loss_against_best" (the points that the chosen move lost against it).

"human_line_end" (told when a sequence ends) has: "moves" (its length), "own" (the length that is always made: KataGo's
own sequence, or 1), "aimed" (the length aimed at) and "reason" ("length": the aimed length; "time": the time limit
passed; "pass": a pass; "no_move": KataGo gave no move). A sequence shorter than "aimed" tells why in "reason".

The sequence of the AIs after a local fight (see quiz.fight_follow) is told with "line" "ai_follow" and no "problem":

- "ai_follow_end" (told when it ends) has: "moves", "seconds" (since it was asked for) and "reason" ("lived",
  "killed", "territory": settled in one way, with "color" (B or W) that lives, captures or owns; "lived_killed": one
  side ("color") lives and captures the other's stones; "all": all the judged points belong to one side ("color") in
  other ways; "mixed": both sides own some of the judged points, with "black" and "white", the points that each owns;
  "left": a side
  played away from the fight; "pass": a pass; "length": the most moves; "time": the time limit passed);
- "ai_follow_error" (told when KataGo cannot answer) has: "moves" (made so far) and "message".

The sequence of the strongest AI (both sides play KataGo's best moves), asked when the one above did not conclude, is
told in the same way with "line" "strong_follow" and the events "strong_follow_end" and "strong_follow_error".

"ai_follow_end" and "strong_follow_end" also have "chase", how the last chase of a group went (see quiz.fight_stones):
null (there was none), "going", "captured" or "broken", and "chase_share", how much the group looked at last belonged
to the other color (null if no group was looked at).
"""

from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

from kentogo.settings_file import SETTINGS_PATH

LINE_PREFIX = "KENTOGO_HUMAN_LINE "
LOG_PATH = SETTINGS_PATH.parent / "human_line.jsonl"


def log_line(record: dict, log_path: Path | None = None, now: datetime | None = None) -> None:
    """Tell the record on the console and append it to the log file (LOG_PATH unless another is given).

    A log file that cannot be written is told; the quiz goes on.
    """
    line = json.dumps({"time": (now or datetime.now()).isoformat(timespec="seconds"), **record}, ensure_ascii=False)
    print(LINE_PREFIX + line, file=sys.stderr)
    path = (log_path or LOG_PATH).expanduser()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as log:
            log.write(line + "\n")
    except OSError as error:
        print(f"KentoGo: the human-like move log cannot be written: {error}", file=sys.stderr)
