"""Functions copied unchanged from KaTrain 1.20.0 (https://github.com/sanderland/katrain).

Only the functions below are copied, letter for letter; nothing else of KaTrain is here.
- pack_floats and unpack_floats: from katrain/core/utils.py
- analysis_dumps: from katrain/core/game_node.py
The imports are the ones these functions need (KaTrain imports them at the top of those files).

Copyright 2020 Sander Land and/or other authors of KaTrain.
Released under the MIT License (see THIRD_PARTY_NOTICES.md, "1. KaTrain").
"""

import base64
import copy
import gzip
import json
import struct


def pack_floats(float_list):
    if float_list is None:
        return b""
    return struct.pack(f"{len(float_list)}e", *float_list)


def unpack_floats(str, num):
    if not str:
        return None
    return struct.unpack(f"{num}e", str)


def analysis_dumps(analysis):
    analysis = copy.deepcopy(analysis)
    for movedict in analysis["moves"].values():
        if "ownership" in movedict:  # per-move ownership rarely used
            del movedict["ownership"]
    ownership_data = pack_floats(analysis.pop("ownership"))
    policy_data = pack_floats(analysis.pop("policy"))
    main_data = json.dumps(analysis).encode("utf-8")
    return [
        base64.standard_b64encode(gzip.compress(data)).decode("utf-8")
        for data in [ownership_data, policy_data, main_data]
    ]
