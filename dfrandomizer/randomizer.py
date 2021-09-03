#!/usr/bin/env python3
import argparse
import hashlib
import logging
import itertools
import random
import time
from typing import List, IO

from dustmaker import DFReader, DFWriter
from dustmaker.tile import TileSpriteSet

from .dataset import DatasetManager, open_and_swap
from .level_sets import LEVELS_STOCK, LEVELS_CMP

LOGGER = logging.getLogger(__name__)


def derange(rng: random.Random, n: int) -> List[int]:
    """ Return a derangement permutation of length n """
    assert n > 1

    a = list(range(n))
    while True:
        for i in range(n):
            j = rng.randrange(i, n)
            if i != j:
                a[i], a[j] = a[j], a[i]
            if i == a[i]:
                break
        else:
            return a


def randomize_stock(rng: random.Random, preserve_hub: bool, stock_more: bool, stock_all: bool):
    if stock_all:
        levels = LEVELS_STOCK
    elif stock_more:
        levels = LEVELS_STOCK[:75]
    else:
        levels = LEVELS_STOCK[:64]

    if preserve_hub:
        result = []
        for i in range(4):
            result.extend(
                levels[i * 16 + j] for j in derange(rng, 16)
            )
    else:
        result = [
            levels[i] for i in derange(rng, len(levels))[:64]
        ]

    gen_id = f"stock;{stock_all};{stock_more};{preserve_hub}"
    return result, gen_id


def randomize_atlas(rng: random.Random, dataset: DatasetManager, min_difficulty: float, max_difficulty: float, cmp_only: bool, no_cmp: bool):
    ord_levels = list(dataset.level_ranks)

    if cmp_only:
        cmp_st = set(LEVELS_CMP)
        ord_levels = [level for level in ord_levels if level in cmp_st]
    elif no_cmp:
        cmp_st = set(LEVELS_CMP)
        ord_levels = [level for level in ord_levels if level not in cmp_st]
        

    ord_levels.sort(key=lambda level: dataset.level_ranks[level])

    ind_start = int(round(min_difficulty * len(ord_levels)))
    ind_end = int(round(max_difficulty * len(ord_levels)))
    ind_start = max(0, min(len(ord_levels), ind_start))
    ind_end = max(0, min(len(ord_levels), ind_end))
    if ind_end < ind_start:
        ind_start = ind_end

    while ind_end - ind_start < 64:
        if ind_end < len(ord_levels):
            ind_end += 1
        if ind_start > 0:
            ind_start -= 1


    # Select range of possible levels
    ord_levels = ord_levels[ind_start:ind_end]

    # Pick the first 64 of those levels
    rng.shuffle(ord_levels)
    ord_levels = ord_levels[:64]

    hubs = [
        TileSpriteSet.FOREST,
        TileSpriteSet.MANSION,
        TileSpriteSet.CITY,
        TileSpriteSet.LABORATORY,
    ]
    hub_index = {
        hub: i for i, hub in enumerate(hubs)
    }
    hub_entities = {
        TileSpriteSet.FOREST: {
            "enemy_bear", "enemy_critter", "enemy_hawk", "enemy_procupine",
            "enemy_stoneboss", "enemy_stonebro", "enemy_wolf",
        },
        TileSpriteSet.MANSION: {
            "enemy_book", "enemy_butler", "enemy_chest_scrolls", "enemy_chest_treasure",
            "enemy_door", "enemy_flag", "enemy_gargoyle_big", "enemy_gargoyle_small",
            "enemy_key", "enemy_knight", "enemy_maid", "enemy_scrolls", "enemy_treasure",
        },
        TileSpriteSet.CITY: {
            "enemy_trash_bag", "enemy_trash_ball", "enemy_trash_beast",
            "enemy_trash_can", "enemy_trash_tire"
        },
        TileSpriteSet.LABORATORY: {
            "enemy_slime_ball", " enemy_slime_barrel", "enemy_slime_beast",
            "enemy_spring_ball"
        }
    }

    level_affinities = {}
    for level in ord_levels:
        leveldata = dataset.levels.get(level, {})

        affinities = {}
        for hub in hubs:
            affinity = leveldata.get("tiles", {}).get(str(hub), 0)
            for entity_name, entity_count in leveldata.get("entities", {}).items():
                if entity_name in hub_entities[hub]:
                    affinity += 50 * entity_count
            affinities[hub] = affinity

        total_affinity = max(1, sum(affinities.values()))
        level_affinities[level] = {
            hub: 1.0 * affinity / total_affinity
            for hub, affinity in affinities.items()
        }

    result = ["" for _ in range(64)]

    # Map levels to their appropriate door difficulty first
    ord_levels.sort(key=lambda level: dataset.level_ranks.get(level, 0.0))
    for chunk in range(4):
        chunk_levels = ord_levels[16 * chunk:16 * (chunk + 1)]

        # Within each difficulty bracket try to map to the nexus with the most
        # affinity.
        chunk_levels.sort(key=lambda level: max(level_affinities[level]), reverse=True)

        hub_levels = [[] for _ in hubs]
        for level in chunk_levels:
            affinities = level_affinities[level]
            hubs.sort(key=lambda hub: affinities[hub], reverse=True)

            for hub in hubs:
                hub_ind = hub_index[hub]
                if len(hub_levels[hub_ind]) < 4:
                    hub_levels[hub_ind].append(level)
                    break
            else:
                assert False

        for i, hub_level_set in enumerate(hub_levels):
            rng.shuffle(hub_level_set)

            for j, level in enumerate(hub_level_set):
                result[16 * i + j + chunk * 4] = level

    gen_id = f"atlas;{dataset.rank_gen_time};{ind_start};{ind_end};{cmp_only};{no_cmp}"
    return result, gen_id


def write_level(dataset: DatasetManager, input_path: str, fout: IO, level_set: List[str], full_seed: str, no_authors: bool) -> None:
    with DFReader(open(input_path, "rb")) as reader:
        dflevel, region_offsets = reader.read_level_ex()
        region_data = reader.read_bytes(region_offsets[-1])

    spd = dflevel.variables["script_persist_data"]
    assert len(spd) == 1

    persist_keys = spd[0]["keys"]
    persist_vals = spd[0]["values"]

    while persist_keys:
        persist_keys.pop()
    while persist_vals:
        persist_vals.pop()

    persist_keys.append(b"full_seed_name")
    persist_vals.append(full_seed.encode())

    internal_seed_name = hashlib.sha256(full_seed.encode()).hexdigest()[:8]
    persist_keys.append(b"seed_name")
    persist_vals.append(internal_seed_name.encode())

    persist_keys.append(b"[]level_mapping")
    persist_vals.append(str(len(level_set)).encode())
    for level in level_set:
        persist_keys.append(b"")
        persist_vals.append(level.encode())

    if not no_authors:
        persist_keys.append(b"[]authors")
        persist_vals.append(str(len(level_set)).encode())
        for level in level_set:
            persist_keys.append(b"")
            author = dataset.levels.get(level, {}).get("author", "")
            persist_vals.append(author.encode())

    persist_keys.append(b"[]level_names")
    persist_vals.append(str(len(level_set)).encode())
    for level in level_set:
        author = dataset.levels.get(level, {}).get("name", "")
        persist_keys.append(b"")
        persist_vals.append(author.encode())
    
    with DFWriter(fout, noclose=True) as writer:
        writer.write_level_ex(dflevel, region_offsets, region_data)

    return internal_seed_name


def main():
    parser = argparse.ArgumentParser("create randomized nexus")
    parser.add_argument(
        "randomizer_template",
        help="randomizer level binary file",
    )
    parser.add_argument(
        "output_path",
        help="randomizer output path",
    )
    parser.add_argument(
        "--dataset",
        default="dataset",
        required=False,
        help="path to dataset folder",
    )
    parser.add_argument(
        "--stock",
        action="store_const",
        const=True,
        default=False,
        required=False,
        help="use stock levels instead of Atlas levels",
    )
    parser.add_argument(
        "--stock-more",
        action="store_const",
        const=True,
        default=False,
        required=False,
        help="include new tutorials, difficults. Implies --stock",
    )
    parser.add_argument(
        "--stock-all",
        action="store_const",
        const=True,
        default=False,
        required=False,
        help="implies --stock-more and adds tutorial0 and devclip."
    )
    parser.add_argument(
        "--stock-preserve-hub",
        action="store_const",
        const=True,
        default=False,
        required=False,
        help="keep stock levels in the same hub, implies --stock",
    )
    parser.add_argument(
        "--min-difficulty",
        default=0.0,
        required=False,
        type=float,
        help="minimum difficulty percentile from 0.0 to 1.0",
    )
    parser.add_argument(
        "--max-difficulty",
        default=1.0,
        required=False,
        type=float,
        help="maximum difficulty percentile from 0.0 to 1.0",
    )
    parser.add_argument(
        "--no-authors",
        action="store_const",
        const=True,
        default=False,
        help="Don't show level authors",
    )
    parser.add_argument(
        "--cmp",
        action="store_const",
        const=True,
        default=False,
        help="Use cmp levels only",
    )
    parser.add_argument(
        "--no-cmp",
        action="store_const",
        const=True,
        default=False,
        help="Don't use any CMP levels",
    )
    parser.add_argument(
        "--seed",
        default=None,
        required=False,
        help="randomizer seed",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="count",
        default=0,
    )
    args = parser.parse_args()

    if args.stock_all:
        args.stock_more = True
    if args.stock_preserve_hub or args.stock_more:
        args.stock = True
    if args.stock_preserve_hub and args.stock_more:
        raise ValueError("cannot use --stock-preserve-hub with --stock-more")
    if not args.seed:
        args.seed = time.time_ns()

    log_level = logging.WARN
    if args.verbose > 1:
        log_level = logging.DEBUG
    elif args.verbose:
        log_level = logging.INFO
    logging.basicConfig(
        format="%(levelname)s: %(message)s",
        level=log_level,
    )

    dataset = DatasetManager(args.dataset)
    dataset.load_levels()

    rng = random.Random(args.seed)
    if args.stock:
        level_set, gen_id = randomize_stock(rng, args.stock_preserve_hub, args.stock_more, args.stock_all)
    else:
        dataset.load_ranks()
        level_set, gen_id = randomize_atlas(rng, dataset, args.min_difficulty, args.max_difficulty, args.cmp, args.no_cmp)

    full_seed = f"{gen_id};{args.seed}"

    with open_and_swap(args.output_path, "wb") as fout:
        write_level(dataset, args.randomizer_template, fout, level_set, full_seed, args.no_authors)


if __name__ == "__main__":
    main()
