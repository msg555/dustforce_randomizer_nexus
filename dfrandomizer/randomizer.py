"""
Module that performs level filtering, selection, and writing the actual
level files.
"""
import dataclasses
import logging
import random
import re
from typing import Any, BinaryIO, Dict, List, Set

from dustmaker import DFReader, DFWriter
from dustmaker.variable import (
    VariableArray,
    VariableString,
    VariableStruct,
)

from .dataset import DatasetManager
from .level_sets import LEVELS_STOCK, LEVELS_CMP
from .nexus_templates import NexusTemplate, DOOR_INFO

LOGGER = logging.getLogger(__name__)


ATLAS_MIN_SS_DEFAULT = "5"
ATLAS_MAX_SS_DEFAULT = "-1"
ATLAS_MIN_SS_TIME_DEFAULT = ""
ATLAS_MAX_SS_TIME_DEFAULT = "3:00.000"

RANDOMIZER_SCRIPT_NAME = "randomizer/nexus.cpp"


@dataclasses.dataclass
class RandomizerData:
    """Container class to hold all information needed to create a randomized
    nexus outside of the nexus template.
    """

    levels: List[str]
    doors: List[int]
    keys: List[int]

    def as_json(self) -> Dict[str, Any]:
        """Return the dataclass as a json dict"""
        return {
            "levels": self.levels,
            "doors": self.doors,
            "keys": self.keys,
        }


def atlas_filter_levels(
    dataset: DatasetManager,
    nexus_template: NexusTemplate,  # pylint: disable=unused-argument
    *,
    min_ss=ATLAS_MIN_SS_DEFAULT,
    max_ss=ATLAS_MAX_SS_DEFAULT,
    min_time=ATLAS_MIN_SS_TIME_DEFAULT,
    max_time=ATLAS_MAX_SS_TIME_DEFAULT,
    cmp_filter: str = "",
    daily_filter: str = "",
    community_filter: str = "",
    apple_filter: str = "",
    cw_filter: str = "n",
    ccw_filter: str = "n",
    clunky_filter: str = "n",
    backwards_filter: str = "n",
    required_authors: str = "",
    blocked_authors: str = "",
    ss_users: str = "",
    no_ss_users: str = "",
    **_,
) -> List[str]:
    """
    Return a list of candidate levels after applying the requested constraints.
    """

    def _parse_time_ms(tm):
        """Convert a time in mm:ss.MMM format into milliseconds"""
        m = re.match(r"(\d+):(\d+)\.(\d+)", tm)
        if m:
            return int(m.group(1)) * 60000 + int(m.group(2)) * 1000 + int(m.group(3))
        m = re.match(r"(\d+)\.(\d+)", tm)
        if m:
            return int(m.group(1)) * 1000 + int(m.group(2))
        try:
            return int(tm)
        except ValueError:
            return -1

    min_ss_num = int(ATLAS_MIN_SS_DEFAULT)
    try:
        min_ss_num = int(min_ss)
    except ValueError:
        pass
    max_ss_num = int(ATLAS_MAX_SS_DEFAULT)
    try:
        max_ss_num = int(max_ss)
    except ValueError:
        pass

    min_time_ms = _parse_time_ms(min_time)
    max_time_ms = _parse_time_ms(max_time)

    required_authors_st = set(
        author.strip().lower()
        for author in required_authors.split(",")
        if author.strip()
    )
    blocked_authors_st = set(
        author.strip().lower()
        for author in blocked_authors.split(",")
        if author.strip()
    )

    ss_users_list = []
    no_ss_users_list = []
    for user_id_str in ss_users.split(","):
        try:
            ss_users_list.append(int(user_id_str))
        except ValueError:
            pass
    for user_id_str in no_ss_users.split(","):
        try:
            no_ss_users_list.append(int(user_id_str))
        except ValueError:
            pass

    community_levels = set()
    want_trees: Dict[str, Set[str]] = {
        "Main Nexus CW": set(),
        "Main Nexus CCW": set(),
        "clunknexusdx": set(),
        "Main Nexus Backwards": set(),
    }

    def dfs(tree: Dict[str, dict]) -> Set[str]:
        result = set()
        for level, subtree in tree.items():
            if not subtree:
                result.add(level)
                continue

            subres = dfs(subtree)
            if level in want_trees:
                want_trees[level] = set(subres)
            if len(result) > len(subres):
                result.update(subres)
            else:
                subres.update(result)
                result = subres

        return result

    community_levels = dfs(dataset.community_levels)

    result = []
    for level, leveldata in dataset.levels.items():
        if not leveldata["atlas_id"]:
            continue
        if level in dataset.banned_levels:
            continue

        ss_count = len(dataset.solvers[level])
        if ss_count < min_ss_num:
            continue
        if max_ss_num != -1 and max_ss_num < ss_count:
            continue

        ss_time = leveldata["fastest_time"]
        if ss_time < min_time_ms:
            continue
        if max_time_ms != -1 and max_time_ms < ss_time:
            continue

        props = (
            (cmp_filter, level in LEVELS_CMP),
            (daily_filter, leveldata["was_daily"]),
            (community_filter, level in community_levels),
            (apple_filter, "hittable_apple" in leveldata["entities"]),
            (cw_filter, level in want_trees["Main Nexus CW"]),
            (ccw_filter, level in want_trees["Main Nexus CCW"]),
            (clunky_filter, level in want_trees["clunknexusdx"]),
            (backwards_filter, level in want_trees["Main Nexus Backwards"]),
        )

        require_props = [prop[1] for prop in props if prop[0] == "y"]
        if require_props and not any(require_props):
            continue

        disallow_props = (prop[1] for prop in props if prop[0] == "n")
        if any(disallow_props):
            continue

        if (
            required_authors_st
            and leveldata["author"].lower() not in required_authors_st
        ):
            continue

        if leveldata["author"].lower() in blocked_authors_st:
            continue

        if ss_users_list or no_ss_users_list:
            solvers_st = set(dataset.solvers[level])
            if not all(user in solvers_st for user in ss_users_list):
                continue
            if any(user in solvers_st for user in no_ss_users_list):
                continue

        result.append(level)

    return result


def atlas_randomize(
    rng: random.Random,
    dataset: DatasetManager,
    nexus_template: NexusTemplate,
    *,
    min_difficulty="0",
    max_difficulty="1000",
    rand_doors="",
    **filter_args,
) -> RandomizerData:
    """Create all randomizer metadata. Decides what levels to use,
    what door types to put in front of those levels, and what key
    type each of those levels should produce.
    """
    ord_levels = sorted(
        atlas_filter_levels(dataset, nexus_template, **filter_args),
        key=lambda level: dataset.level_ranks[level],
    )

    mn_diff, mx_diff = 0.0, 1.0
    try:
        mn_diff = int(min_difficulty) / 1000.0
    except ValueError:
        pass
    try:
        mx_diff = int(max_difficulty) / 1000.0
    except ValueError:
        pass

    # Figure out what range of levels to include
    ind_start = int(round(mn_diff * len(ord_levels)))
    ind_end = int(round(mx_diff * len(ord_levels)))
    ind_start = max(0, min(len(ord_levels), ind_start))
    ind_end = max(0, min(len(ord_levels), ind_end))
    if ind_end < ind_start:
        ind_start = ind_end

    num_levels = len(nexus_template.level_doors)
    while ind_end - ind_start < num_levels:
        if ind_end < len(ord_levels):
            ind_end += 1
        if ind_start > 0:
            ind_start -= 1

    # Select range of possible levels
    ord_levels = ord_levels[ind_start:ind_end]

    # Pick the first 64 of those levels
    rng.shuffle(ord_levels)
    ord_levels = ord_levels[:num_levels]

    doors = []
    keys = []
    for door_id in nexus_template.level_doors:
        doors.append(nexus_template.data["doors"][door_id]["door"])
        keys.append(nexus_template.data["doors"][door_id]["key_get"])

    levels = ["" for _ in range(num_levels)]

    # Map levels to their appropriate door difficulty first
    ord_levels.sort(key=lambda level: dataset.level_ranks.get(level, 0.0))

    offset = 0
    for key_type in range(4):
        door_indexes = [
            ind for ind, door in enumerate(doors) if DOOR_INFO[door][1] == key_type
        ]
        chunk_levels = ord_levels[offset : offset + len(door_indexes)]
        offset += len(door_indexes)

        rng.shuffle(chunk_levels)
        for ind, level in zip(door_indexes, chunk_levels):
            levels[ind] = level

    if rand_doors:
        pi = list(range(num_levels))
        rng.shuffle(pi)
        levels = [levels[ind] for ind in pi]
        doors = [doors[ind] for ind in pi]
        keys = [keys[ind] for ind in pi]

    return RandomizerData(
        levels=levels,
        doors=doors,
        keys=keys,
    )


def stock_filter_levels(
    dataset: DatasetManager,  # pylint: disable=unused-argument
    nexus_template: NexusTemplate,
    *,
    builtin_filter: str = "y",
    stock_filter: str = "",
    forest_filter: str = "",
    mansion_filter: str = "",
    city_filter: str = "",
    lab_filter: str = "",
    tutorials_filter: str = "",
    difficults_filter: str = "",
    yotta_filter: str = "n",
    old_tutorial_filter: str = "n",
    devclip_filter: str = "n",
    infini_filter: str = "n",
    **_,
) -> List[str]:
    """
    Return a list of candidate levels after applying the requested constraints.
    """
    levels_builtin = {
        nexus_template.data["doors"][doorid]["level"]
        for doorid in nexus_template.level_doors
    }
    levels_stock = set(LEVELS_STOCK)
    levels_forest = set(LEVELS_STOCK[0:16])
    levels_mansion = set(LEVELS_STOCK[16:32])
    levels_city = set(LEVELS_STOCK[32:48])
    levels_lab = set(LEVELS_STOCK[48:64])
    levels_tutorials = set(LEVELS_STOCK[72:75])
    levels_difficults = set(LEVELS_STOCK[64:72])

    result = []
    for level in levels_builtin | levels_stock:
        props = (
            (builtin_filter, level in levels_builtin),
            (stock_filter, level in levels_stock),
            (forest_filter, level in levels_forest),
            (mansion_filter, level in levels_mansion),
            (city_filter, level in levels_city),
            (lab_filter, level in levels_lab),
            (tutorials_filter, level in levels_tutorials),
            (difficults_filter, level in levels_difficults),
            (yotta_filter, level == "yottadifficult"),
            (old_tutorial_filter, level == "tutorial0"),
            (devclip_filter, level == "devclip"),
            (infini_filter, level == "exec func ruin user"),
        )

        require_props = [prop[1] for prop in props if prop[0] == "y"]
        if require_props and not any(require_props):
            continue

        disallow_props = (prop[1] for prop in props if prop[0] == "n")
        if any(disallow_props):
            continue

        result.append(level)

    return result


def stock_randomize(
    rng: random.Random,
    dataset: DatasetManager,
    nexus_template: NexusTemplate,
    *,
    rand_doors="normal",
    **filter_args,
):
    """Create all randomizer metadata. Decides what levels to use,
    what door types to put in front of those levels, and what key
    type each of those levels should produce.
    """
    num_levels = len(nexus_template.level_doors)
    levels = stock_filter_levels(dataset, nexus_template, **filter_args)
    rng.shuffle(levels)
    levels = levels[:num_levels]

    builtin_levels = [
        nexus_template.data["doors"][doorid]["level"]
        for doorid in nexus_template.level_doors
    ]
    if rand_doors == "match" and set(builtin_levels) != set(levels):
        rand_doors = "normal"

    doors = []
    keys = []
    for door_id in nexus_template.level_doors:
        doors.append(nexus_template.data["doors"][door_id]["door"])
        keys.append(nexus_template.data["doors"][door_id]["key_get"])

    if rand_doors != "normal":
        pi = list(range(num_levels))
        rng.shuffle(pi)
        doors = [doors[ind] for ind in pi]
        keys = [keys[ind] for ind in pi]
        if rand_doors == "match":
            levels = [builtin_levels[ind] for ind in pi]

    return RandomizerData(
        levels=levels,
        doors=doors,
        keys=keys,
    )


def write_level(
    dataset: DatasetManager,
    nexus_template: NexusTemplate,
    script_data: bytes,
    fout: BinaryIO,
    nexus_data: RandomizerData,
    *,
    hide_authors=False,
    hide_names=False,
    **_,
) -> None:
    """Combine the nexus template, randomizer script, and randomizer data into
    a randomizer nexus level file and write that result to fout.
    """
    with DFReader(open(nexus_template.fullpath, "rb")) as reader:
        dflevel, region_offsets = reader.read_level_ex()
        region_data = reader.read_bytes(region_offsets[-1])

    levels = nexus_data.levels
    doors = nexus_data.doors
    keys = nexus_data.keys
    if len(levels) != len(nexus_template.level_doors):
        raise ValueError("unexpected number of levels")
    if len(doors) != len(nexus_template.level_doors):
        raise ValueError("unexpected number of doors")
    if len(keys) != len(nexus_template.level_doors):
        raise ValueError("unexpected number of keys")

    door_ids = nexus_template.level_doors + nexus_template.other_doors
    for door_id in nexus_template.other_doors:
        levels.append("_back_")
        doors.append(nexus_template.data["doors"][door_id]["door"])
        keys.append(0)

    persist_keys = VariableArray(VariableString)
    persist_vals = VariableArray(VariableString)

    persist_keys.append(b"[]door_ids")
    persist_vals.append(str(len(door_ids)).encode())
    for door_id in door_ids:
        persist_keys.append(b"")
        persist_vals.append(str(door_id).encode())

    persist_keys.append(b"[]door_sets")
    persist_vals.append(str(len(doors)).encode())
    for door_set in doors:
        persist_keys.append(b"")
        persist_vals.append(str(door_set).encode())

    persist_keys.append(b"[]keys")
    persist_vals.append(str(len(keys)).encode())
    for key_get in keys:
        persist_keys.append(b"")
        persist_vals.append(str(key_get).encode())

    persist_keys.append(b"[]level_mapping")
    persist_vals.append(str(len(levels)).encode())
    for level in levels:
        persist_keys.append(b"")
        persist_vals.append(level.encode())

    persist_keys.append(b"[]authors")
    persist_vals.append(str(len(levels)).encode())
    for level in levels:
        persist_keys.append(b"")
        author = "" if hide_authors else dataset.levels.get(level, {}).get("author", "")
        persist_vals.append(author.encode())

    persist_keys.append(b"[]level_names")
    persist_vals.append(str(len(levels)).encode())
    for level in levels:
        level_name = (
            "???" if hide_names else dataset.levels.get(level, {}).get("name", "")
        )
        persist_keys.append(b"")
        persist_vals.append(level_name.encode())

    dflevel.variables.setdefault("scriptNames", VariableArray(VariableString)).insert(
        0,
        RANDOMIZER_SCRIPT_NAME.encode(),
    )
    dflevel.variables.setdefault("scripts", VariableArray(VariableString)).insert(
        0,
        script_data,
    )
    dflevel.variables.setdefault(
        "script_persist_data", VariableArray(VariableStruct)
    ).insert(
        0,
        {
            "keys": persist_keys,
            "values": persist_vals,
            "name": VariableString(RANDOMIZER_SCRIPT_NAME.encode()),
        },
    )

    with DFWriter(fout, noclose=True) as writer:
        writer.write_level_ex(dflevel, region_offsets, region_data)
