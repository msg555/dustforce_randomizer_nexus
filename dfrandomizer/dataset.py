#!/usr/bin/env python3
import argparse
import collections
import contextlib
import logging
import os
import re
import tempfile
import time
from typing import Dict, List, Optional, Tuple
import urllib

from dustmaker.entity import LevelDoor, CustomScoreBook
from dustmaker.dfreader import DFReader
from dustmaker.level import Level, LevelType

import json
import requests

from .playerrank import compute_ranks
from .nexus_templates import preprocess_templates


LOGGER = logging.getLogger(__name__)

DEFAULT_DUSTKID_ROOT = "https://dustkid.com"
DEFAULT_ATLAS_ROOT = "http://atlas.dustforce.com"

LevelMetaMapping = Dict[str, dict]
SolverMapping = Dict[str, List[int]]
RankMapping = Dict[str, float]


@contextlib.contextmanager
def open_and_swap(filename, mode='w+b', buffering=-1, encoding=None, newline=None):
    fd, tmppath = tempfile.mkstemp(
        dir=os.path.dirname(filename) or ".",
        text='b' not in mode,
    )
    try:
        fh = open(
            fd,
            mode=mode,
            buffering=buffering,
            encoding=encoding,
            newline=newline,
            closefd=False,
        )
        yield fh
        os.rename(tmppath, filename)
        tmppath = None
    finally:
        if fh is not None:
            fh.close()
        os.close(fd)
        if tmppath is not None:
            os.unlink(tmppath)


class DatasetManager:
    def __init__(self, dataset: str, *, dustkid_root: str = DEFAULT_DUSTKID_ROOT, atlas_root: str = DEFAULT_ATLAS_ROOT) -> None:
        self.dustkid_root = dustkid_root
        self.atlas_root = atlas_root
        self.dataset = dataset
        self.sess = requests.Session()
        self.solvers: SolverMapping = {}
        self.levels: LevelMetaMapping = {}
        self.level_ranks: RankMapping = {}
        self.player_ranks: RankMapping = {}
        self.rank_gen_time = 0

    def download_solvers(self, level_id: str) -> Tuple[Optional[int], List[int]]:
        offset = 0
        count = 1024

        solvers = []
        fastest_time = None
        while True:
            query_parameters = {
                "level": level_id,
                "offset": offset,
                "max": count,
                "json": True,
            }
            url = "{}/charboard.php?{}".format(
                self.dustkid_root,
                urllib.parse.urlencode(query_parameters),
            )
            LOGGER.debug("Querying %s", url)
            resp = self.sess.get(url)
            resp.raise_for_status()

            scores_map = resp.json()["scores"]

            non_ss = False
            for score in scores_map.values():
                if score["score_completion"] == 5 and score["score_finesse"] == 5:
                    if fastest_time is None or score["time"] < fastest_time:
                        fastest_time = score["time"]
                    solvers.append(score["user"])
                else:
                    non_ss = True

            if len(scores_map) != count:
                break
            offset += count

        return fastest_time, solvers

    def download_levels(self, *, prev: str = "", was_daily: Optional[bool] = None,
                        level_types: Optional[List[LevelType]] = None) -> LevelMetaMapping:
        """ Fetch the requested levels from dustkid. """

        query_parameters = {
            "count": 1024,
        }
        if was_daily is not None:
            query_parameters["was_daily"] = was_daily
        if level_types is not None:
            query_parameters["level_type"] = ",".join(
                str(int(level_type)) for level_type in level_types
            )

        print(query_parameters)

        result = {}
        while True:
            query_parameters["prev"] = prev
            url = "{}/levels.php?{}".format(
                self.dustkid_root,
                urllib.parse.urlencode(query_parameters),
            )
            LOGGER.debug("Querying %s", url)
            resp = self.sess.get(url)

            resp.raise_for_status()
            resp_data = resp.json()
            level_map = resp_data["levels"]
            for level_id, level_data in level_map.items():
                result[level_id] = level_data

            prev = resp_data["next"]
            if prev is None:
                break

        return result

    def load_community_levels(self, force_update: bool = False) -> None:
        """ Find all levels accessible from the community nexus """
        community_levels_path = os.path.join(self.dataset, "community.json")
        if not force_update:
            try:
                with open(community_levels_path, "r") as flevs:
                    self.community_levels = json.load(flevs)
                LOGGER.info("Read community.json dataset")
                return
            except FileNotFoundError:
                LOGGER.info("No existing community.json, computing")

        try:
            os.mkdir(os.path.join(self.dataset, "community_levels"))
        except FileExistsError:
            pass

        visited = {
            "random", "_back_", "_forward_", "", "Main Nexus", "Main Nexus DX",
            "tutorial0", "citynexus", "forestnexus", "labnexus", "mansionnexus",
            "Single Player Nexus", "randomizer_nexus",
        }

        def dfs(level, visited):
            if level in self.levels:
                # Level IDs in our levels struct are definitely normal
                # levels, we don't need to open them.
                return {}

            atlas_match = re.match(".*-(\d+)", level)
            atlas_id = 0
            if atlas_match:
                atlas_id = int(atlas_match.group(1))
                path = self.download_atlas_level(atlas_id)
            else:
                path = self.download_community_level(level, force_update=force_update)
            if not path:
                return None

            with DFReader(open(path, "rb")) as reader:
                level_data, region_offsets = reader.read_level_ex()
                if level_data.level_type in (LevelType.NORMAL, LevelType.DUSTMOD):
                    self.levels[level] = {
                        "name": level_data.name.decode(),
                        "author": "",
                        "atlas_id": atlas_id,
                        "level_type": int(level_data.level_type),
                        "was_daily": False,
                    }
                    return {}
                if level_data.level_type != LevelType.NEXUS:
                    return None

                for _ in region_offsets[:-1]:
                    reader.read_region(level_data)

            LOGGER.info("Searching community level %s", level)
            visited.add(level)

            sub_levels = []
            for _, _, entity in level_data.entities.values():
                if not isinstance(entity, LevelDoor):
                    continue
                sub_levels.append(entity.file_name.decode())

            for _, _, entity in level_data.entities.values():
                if not isinstance(entity, CustomScoreBook):
                    continue

                _, _, stringlist_entity = level_data.entities[entity.level_list]
                for ind, tome_level in enumerate(stringlist_entity.data):
                    if ind > 1:
                        sub_levels.append(tome_level.decode())

            result = {}
            for sub_level in sub_levels:
                if sub_level in visited:
                    continue
                sub_result = dfs(sub_level, visited)
                if sub_result is None:
                    continue

                result[sub_level] = sub_result

            return result if result else None

        self.community_levels = {
            level: dfs(level, visited)
            for level in ("customnexus", "Multiplayer Nexus")
        }
        with open_and_swap(community_levels_path, "w") as flevs:
            json.dump(self.community_levels, flevs)
        LOGGER.info("Wrote levels.json dataset")

    def load_levels(self, force_update: bool = False) -> None:
        """ Load level metadata into self.levels. By default this will just
        load level metadata from disk and download it from the dustkid API if
        no local level data exists.

        If `force_update` is set then it will always download new level metadata
        from the dustkid API.
        """
        levels_path = os.path.join(self.dataset, "levels.json")
        try:
            with open(levels_path, "r") as flevels:
                self.levels = json.load(flevels)
            LOGGER.info("Read levels.json dataset")
        except FileNotFoundError:
            self.levels = {}
            LOGGER.info("No existing levels.json")

        if force_update or not self.levels:
            new_levels = self.download_levels(level_types=[LevelType.NORMAL, LevelType.DUSTMOD])

            # Merge downloaded data into existing level metadata
            for level, new_leveldata in new_levels.items():
                self.levels.setdefault(level, {}).update(new_leveldata)

            # Filter out any removed (now hidden) levels.
            self.levels = {
                level: leveldata for level, leveldata in self.levels.items()
                if level in new_levels
            }

            with open_and_swap(levels_path, "w") as flevels:
                json.dump(self.levels, flevels)
            LOGGER.info("Wrote levels.json dataset")

    def download_level_files(self) -> None:
        """ Download the level binaries for each file in the levels metadata.
        Only downloads level files that are missing.
        """
        try:
            os.mkdir(os.path.join(self.dataset, "levels"))
        except FileExistsError:
            pass

        for level, levelinfo in self.levels.items():
            atlas_id = levelinfo["atlas_id"]
            if not atlas_id:
                continue
            self.download_atlas_level(atlas_id)

    def download_atlas_level(self, atlas_id: int) -> str:
        """ Download a singular level from Atlas by its ID. """
        level_path = os.path.join(self.dataset, "levels", str(atlas_id))
        if os.path.exists(level_path):
            return level_path

        url = f"{self.atlas_root}/gi/downloader.php?id={atlas_id}"
        LOGGER.info("Downloading atlas level ID %d from %s", atlas_id, url)

        # Atlas sometimes generates 400s despite nothing being wrong with
        # the request. We try to ignore those and just retry where possible.
        MAX_ATTEMPTS = 3
        for attempt in range(MAX_ATTEMPTS):
            resp = self.sess.get(url, stream=True)
            try:
                resp.raise_for_status()
            except requests.exceptions.HTTPError:
                if attempt + 1 == MAX_ATTEMPTS:
                    raise
                LOGGER.warning("request failed, pausing and then retrying")
                self.sess = requests.Session()
                time.sleep(1)
            else:
                break

        with open_and_swap(level_path, "wb") as fout:
            for chunk in resp.iter_content(1024):
                fout.write(chunk)

        return level_path

    def download_community_level(self, level: int, force_update: bool = False) -> str:
        """ Download a community level from Dustkid by name """
        scrubbed_name = re.sub(r"[^\w-]", "", level)
        level_path = os.path.join(self.dataset, "community_levels", scrubbed_name)
        if not force_update and os.path.exists(level_path):
            return level_path

        url = "{}/backend8/level.php?{}".format(
            self.dustkid_root,
            urllib.parse.urlencode({"id": level}),
        )
        LOGGER.info("Downloading level %s from %s", level, url)

        # Atlas sometimes generates 400s despite nothing being wrong with
        # the request. We try to ignore those and just retry where possible.
        MAX_ATTEMPTS = 3
        for attempt in range(MAX_ATTEMPTS):
            resp = self.sess.get(url, stream=True)
            try:
                if resp.status_code == 404:
                    return ""
                resp.raise_for_status()
            except requests.exceptions.HTTPError:
                if attempt + 1 == MAX_ATTEMPTS:
                    raise
                LOGGER.warning("request failed, pausing and then retrying")
                self.sess = requests.Session()
                time.sleep(1)
            else:
                break

        with open_and_swap(level_path, "wb") as fout:
            for chunk in resp.iter_content(1024):
                fout.write(chunk)

        return level_path

    def extend_level_metadata(self, force_update: bool = False) -> None:
        """ Add additional metadata from the level files to the self.levels
        mapping. This will by default only update levels that have no existing
        extended metadata. This will ignore any levels where the level has not
        been downloaded.

        If `force_update` is set then extended metadata will be updated for all
        levels regardless of if it already exists.
        """
        EXTENDED_KEYS = ("tiles", "entities", "virtual")

        updated_level_info = False
        try:
            for level, levelinfo in self.levels.items():
                atlas_id = levelinfo["atlas_id"]
                if not atlas_id:
                    continue
                if not force_update and all(key in levelinfo for key in EXTENDED_KEYS):
                    continue

                level_path = os.path.join(self.dataset, "levels", str(atlas_id))
                if not os.path.exists(level_path):
                    LOGGER.warning("could not find level file for %s", level)
                    continue

                LOGGER.info("Extract level metadata for %s", level)
                tile_sets = collections.Counter()
                entities = collections.Counter()
                with DFReader(open(level_path, "rb")) as reader:
                    level, region_offsets = reader.read_level_ex()
                    levelinfo["virtual"] = level.virtual_character
                    levelinfo["name"] = level.name.decode("utf-8")

                    for _ in region_offsets[:-1]:
                        level = Level()
                        reader.read_region(level)

                        for (layer, _, _), tile in level.tiles.items():
                            if layer != 19:
                                continue
                            tile_sets[tile.sprite_set] += 1

                        for _, _, entity in level.entities.values():
                            entities[entity.etype] += 1

                levelinfo["tiles"] = dict(tile_sets)
                levelinfo["entities"] = dict(entities)
                updated_level_info = True
        finally:
            if updated_level_info:
                with open_and_swap(os.path.join(self.dataset, "levels.json"), "w") as flevels:
                    json.dump(self.levels, flevels)

    def load_solvers(self, force_update: bool = False) -> None:
        """ Load solvers information into self.solvers. Normally this will
        load cached data from disk and load any additional missing levels
        from the dustkid API.

        If `force_update` is set then all levels will be reloaded from the
        dustkid API.
        """
        solvers = {}
        if not force_update:
            try:
                with open(os.path.join(self.dataset, "solvers.json"), "r") as fsolvers:
                    solvers = json.load(fsolvers)
                LOGGER.info("Read solvers.json dataset")
            except FileNotFoundError:
                LOGGER.info("No solvers.json found, initialized empty dataset")
        
        updated_solvers = False
        try:
            for level_id, level_data in self.levels.items():
                if not level_data["atlas_id"]:
                    continue
                if not force_update and level_id in solvers:
                    continue

                LOGGER.info("Calculating solvers for %s", level_id)
                level_data["fastest_time"], solvers[level_id] = self.download_solvers(level_id)
                updated_solvers = True

            orig_len = len(solvers)
            solvers = {
                level: solvers for level, solvers in solvers.items()
                if level in self.levels
            }
            updated_solvers = updated_solvers or len(solvers) != orig_len
        finally:
            if updated_solvers:
                with open_and_swap(os.path.join(self.dataset, "levels.json"), "w") as flevels:
                    json.dump(self.levels, flevels)
                with open_and_swap(os.path.join(self.dataset, "solvers.json"), "w") as fsolvers:
                    json.dump(solvers, fsolvers)
                LOGGER.info("Updated solvers.json")

        self.solvers = solvers

    def load_banned_levels(self) -> List[str]:
        try:
            with open(os.path.join(self.dataset, "banned_levels.json"), "r") as fbanned:
                self.banned_levels = set(json.load(fbanned))
        except FileNotFoundError:
            self.banned_levels = {}
            LOGGER.info("Found no banned_levels.json file")

    def load_ranks(self) -> None:
        """ Load player/level rank data from disk into self.level_ranks and
        self.player_ranks. If you want to recalculate ranks instead
        call compute_ranks.
        """
        try:
            with open(os.path.join(self.dataset, "ranks.json"), "r") as franks:
                ranks = json.load(franks)
            self.level_ranks = ranks["level_ranks"]
            self.player_ranks = ranks["player_ranks"]
            self.rank_gen_time = ranks["gen_time"]
        except FileNotFoundError:
            self.level_ranks = {}
            self.player_ranks = {}
            self.rank_gen_time = 0

    def compute_player_ranks(self) -> None:
        """ Compute and save rank data and store results in self.level_ranks
        and self.player_ranks.
        """
        self.level_ranks, self.player_ranks = compute_ranks(self.levels, self.solvers)
        self.rank_gen_time = time.time_ns()
        with open_and_swap(os.path.join(self.dataset, "ranks.json"), "w") as franks:
            json.dump(
                {
                    "level_ranks": self.level_ranks,
                    "player_ranks": self.player_ranks,
                    "gen_time": self.rank_gen_time,
                },
                franks,
            )


def main():
    """ Update dataset CLI interface """
    parser = argparse.ArgumentParser("update randomizer nexus dataset")
    parser.add_argument(
        "--dustkid",
        default=DEFAULT_DUSTKID_ROOT,
        required=False,
        help="Dustkid website root URL",
    )
    parser.add_argument(
        "--atlas",
        default=DEFAULT_ATLAS_ROOT,
        required=False,
        help="Atlas root URL",
    )
    parser.add_argument(
        "--dataset",
        default="dataset",
        required=False,
        help="path to dataset folder",
    )
    parser.add_argument(
        "--templates",
        default="nexus_templates",
        required=False,
        help="path to nexus templates folder",
    )
    parser.add_argument(
        "--update-levels",
        action="store_const",
        const=True,
        default=False,
        required=False,
        help="force update level list and metadata",
    )
    parser.add_argument(
        "--update-community",
        action="store_const",
        const=True,
        default=False,
        required=False,
        help="force update list of community levels",
    )
    parser.add_argument(
        "--update-levels-full",
        action="store_const",
        const=True,
        default=False,
        required=False,
        help="force update extended level metadata",
    )
    parser.add_argument(
        "--update-solvers",
        action="store_const",
        const=True,
        default=False,
        required=False,
        help="Force update solver list for each level",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="count",
        default=0,
    )
    args = parser.parse_args()

    log_level = logging.WARN
    if args.verbose > 1:
        log_level = logging.DEBUG
    elif args.verbose:
        log_level = logging.INFO
    logging.basicConfig(
        format="%(levelname)s: %(message)s",
        level=log_level,
    )

    dataset = DatasetManager(args.dataset, dustkid_root=args.dustkid, atlas_root=args.atlas)
    dataset.load_levels(args.update_levels)
    dataset.load_community_levels(args.update_community)
    dataset.download_level_files()
    dataset.extend_level_metadata(args.update_levels_full)
    dataset.load_solvers(args.update_solvers)
    dataset.compute_player_ranks()
    preprocess_templates(args.templates)


if __name__ == "__main__":
    main()
