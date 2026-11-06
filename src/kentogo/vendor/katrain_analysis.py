"""Functions copied unchanged from KaTrain 1.20.0 (https://github.com/sanderland/katrain).

Only the functions below are copied, letter for letter; nothing else of KaTrain is here.
- var_to_grid, evaluation_class, pack_floats and unpack_floats (and the type variable T that
  var_to_grid uses): from katrain/core/utils.py
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
from typing import List, Tuple, TypeVar

T = TypeVar("T")


def var_to_grid(array_var: List[T], size: Tuple[int, int]) -> List[List[T]]:
    """convert ownership/policy to grid format such that grid[y][x] is for move with coords x,y"""
    ix = 0
    grid = [[]] * size[1]
    for y in range(size[1] - 1, -1, -1):
        grid[y] = array_var[ix : ix + size[0]]
        ix += size[0]
    return grid


def evaluation_class(points_lost: float, eval_thresholds: List[float]):
    i = 0
    while i < len(eval_thresholds) - 1 and points_lost < eval_thresholds[i]:
        i += 1
    return i


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
