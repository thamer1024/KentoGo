"""A fake KataGo analysis engine for the tests.

It answers every query at once, and the answer says which moves (and overrideSettings) it got.
A query with "maxVisits" gets them all as the visits of its root, as if they were read at once.
A query with "action": "crash" makes it stop, "action": "slow" is answered
only after the next query (so the answers come in a different order), and
"action": "warn" gets a warning before its answer. With the argument --quiet, it does not
write that it is ready to its error output (as KataGo with its log turned off there).
"""

import json
import sys

if "--quiet" not in sys.argv:
    print("fake KataGo started, ready to begin handling requests", file=sys.stderr, flush=True)
slow = None
for line in sys.stdin:
    query = json.loads(line)
    if query.get("action") == "crash":
        print("fake KataGo crashed", file=sys.stderr, flush=True)
        sys.exit(1)
    if query.get("action") == "warn":
        print(json.dumps({"id": query["id"], "field": "action", "warning": "unused field"}), flush=True)
    if query.get("action") == "slow":
        slow = query
        continue
    answers = [query] if slow is None else [query, slow]
    slow = None
    for item in answers:
        print(json.dumps({"id": item["id"], "isDuringSearch": True, "moveInfos": []}), flush=True)
        final = {"id": item["id"], "isDuringSearch": False, "moves": item.get("moves", [])}
        if "maxVisits" in item:
            final["rootInfo"] = {"visits": item["maxVisits"]}  # As if every visit was read at once.
        if "overrideSettings" in item:
            final["overrideSettings"] = item["overrideSettings"]  # So that the tests can see what was sent.
        print(json.dumps(final), flush=True)
