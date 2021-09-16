#!/usr/bin/env python3
"""
Classes and functions for managing nexus templates.

If you want to add a new nexus template run 

./nexus_template.py nexus_template_file [other_template_file ...]
"""
import collections
import copy
import logging
import json
import os
from typing import Any, BinaryIO, Dict, Iterable, Tuple

from dustmaker import DFReader, DFWriter
from dustmaker.entity import FogTrigger, LevelDoor, RedKeyDoor
from dustmaker.level import Level, LevelType
from dustmaker.tile import Tile, TileSpriteSet

from .dataset import DatasetManager
from .util import ArgumentParser

LOGGER = logging.getLogger(__name__)

DOOR_INFO = (
    (TileSpriteSet.NONE_0, 0),  # 0 (not valid)
    (TileSpriteSet.MANSION, 0),  # 1
    (TileSpriteSet.MANSION, 2),  # 2
    (TileSpriteSet.MANSION, 3),  # 3
    (TileSpriteSet.MANSION, 0),  # 4
    (TileSpriteSet.FOREST, 0),  # 5
    (TileSpriteSet.FOREST, 2),  # 6
    (TileSpriteSet.FOREST, 3),  # 7
    (TileSpriteSet.FOREST, 0),  # 8
    (TileSpriteSet.FOREST, 0),  # 9
    (TileSpriteSet.FOREST, 2),  # 10
    (TileSpriteSet.FOREST, 3),  # 11
    (TileSpriteSet.FOREST, 0),  # 12
    (TileSpriteSet.CITY, 0),  # 13
    (TileSpriteSet.CITY, 2),  # 14
    (TileSpriteSet.CITY, 3),  # 15
    (TileSpriteSet.CITY, 0),  # 16
    (TileSpriteSet.LABORATORY, 0),  # 17
    (TileSpriteSet.LABORATORY, 2),  # 18
    (TileSpriteSet.LABORATORY, 3),  # 19
    (TileSpriteSet.LABORATORY, 0),  # 20
    (TileSpriteSet.TUTORIAL, 0),  # 21
    (TileSpriteSet.MANSION, 1),  # 22
    (TileSpriteSet.FOREST, 1),  # 23
    (TileSpriteSet.CITY, 1),  # 24
    (TileSpriteSet.LABORATORY, 1),  # 25
    (TileSpriteSet.FOREST, 1),  # 26
)

TEMPLATE_PREFERRED_ORDER = (
    "nexusdx",
    "linear",
    "forestnexus",
    "mansionnexus",
    "citynexus",
    "labnexus",
    "virtualnexus",
)


class NexusTemplate:
    """
    Container class containing metadata about a nexus template.
    """

    def __init__(
        self,
        fullpath: str,
        name: str,
        data,
        level_doors: Iterable[int],
        other_doors: Iterable[int],
    ) -> None:
        self.fullpath = fullpath
        self.name = name
        self.data = data
        self.other_doors = tuple(other_doors)
        self.level_doors = tuple(
            sorted(
                level_doors, key=lambda eid: DOOR_INFO[data["doors"][eid]["door"]][::-1]
            )
        )

    def display_label(self) -> str:
        """Return a display label to use in UIs"""
        return f"{self.name} ({len(self.level_doors)} levels)"

    def config(self, **_) -> "NexusTemplate":
        """Return a configured nexus template"""
        return self

    def read(self) -> Tuple[Level, Any]:
        """Read level data. Return the level and additional opaque
        data that will be passed back to write.
        """
        with DFReader(open(self.fullpath, "rb")) as reader:
            dflevel, region_offsets = reader.read_level_ex()
            region_data = reader.read_bytes(region_offsets[-1])
        return dflevel, (region_offsets, region_data)

    # pylint: disable=no-self-use
    def write(self, fout: BinaryIO, dflevel: Level, level_data: Any) -> None:
        """Write level to fout"""
        region_offsets, region_data = level_data
        with DFWriter(fout, noclose=True) as writer:
            writer.write_level_ex(dflevel, region_offsets, region_data)


class LinearNexusTemplate(NexusTemplate):
    """
    Generic linear nexus template.
    """

    def __init__(self, data=None, level_doors=None, other_doors=None):
        super().__init__("", "linear", data or {}, level_doors or [], other_doors or [])

    def display_label(self) -> str:
        """Return a display label to use in UIs"""
        return "linear (variable levels)"

    # pylint: disable=arguments-differ
    def config(self, *, num_levels="", **_) -> NexusTemplate:
        """Return a configured nexus template"""
        try:
            cnt = int(num_levels)
        except ValueError as exc:
            raise ValueError("num_levels invalid or unset") from exc
        if cnt < 1 or cnt > 256:
            raise ValueError("num_levels must be between 1 and 256 inclusive")
        data = {
            "doors": {
                ind
                + 200: {
                    "level": f"level_{ind}",
                    "door": (5, 23, 6, 7)[ind % 4],
                    "key_get": ind % 4,
                }
                for ind in range(cnt)
            },
        }
        data["doors"][199] = {
            "level": "_bak_",
            "door": 1,
            "key_get": -1,
        }
        return LinearNexusTemplate(
            data=data,
            level_doors=list(200 + ind for ind in range(cnt)),
            other_doors=[199],
        )

    def read(self) -> Tuple[Level, Any]:
        """Read level data. Return the level and additional opaque
        data that will be passed back to write.
        """
        dflevel = Level()
        dflevel.name = b"Linear Randomizer"
        dflevel.level_type = LevelType.NEXUS

        base_tile = Tile(
            sprite_set=TileSpriteSet.FOREST,
            sprite_tile=6,
            sprite_palette=1,
        )

        x_left = -6
        x_right = -6 + len(self.data["doors"]) * 8 + 4
        for x in range(x_left, x_right):
            dflevel.tiles[(19, x, 0)] = copy.deepcopy(base_tile)
            dflevel.tiles[(19, x, 1)] = copy.deepcopy(base_tile)
            dflevel.tiles[(19, x, -6)] = copy.deepcopy(base_tile)
            dflevel.tiles[(19, x, -5)] = copy.deepcopy(base_tile)
            if x <= x_left + 1 or x_right - 2 <= x:
                for y in range(-4, 0):
                    dflevel.tiles[(19, x, y)] = copy.deepcopy(base_tile)

        dflevel.calculate_edge_visibility()
        dflevel.calculate_edge_caps()

        for i, door_id in enumerate(range(199, 200 + len(self.level_doors))):
            door = LevelDoor()
            door.door_set = self.data["doors"][door_id]["door"]
            dflevel.add_entity(i * 48 * 8, 0, door, id_num=door_id)

        fog_trigger = FogTrigger()
        fog_trigger.normalize()
        fog_trigger.star_bottom = 0.0
        fog_trigger.star_middle = 0.0
        fog_trigger.star_top = 0.0
        fog_trigger.width = 500
        dflevel.add_entity(0, 0, fog_trigger)

        for i in range((len(self.level_doors) - 1) // 4):
            red_door = RedKeyDoor()
            red_door.keys_needed = i + 1
            dflevel.add_entity(((i + 1) * 4 * 8 + 4) * 48, 0, red_door)

        return dflevel, None

    def write(self, fout: BinaryIO, dflevel: Level, _: Any) -> None:
        """Write level to fout"""
        with DFWriter(fout, noclose=True) as writer:
            writer.write_level(dflevel)


def load_template(
    dataset: DatasetManager, template_dir: str, template_name: str
) -> NexusTemplate:
    """Load a template metadata into memory. Uses dataset to determine which
    levels correspond to playable levels rather than other nexuses.
    """
    if template_name == "linear":
        return LinearNexusTemplate()

    fullpath = os.path.join(template_dir, template_name)
    with open(fullpath + ".json", "r") as fdata:
        data = json.load(fdata)

    level_doors = []
    other_doors = []
    for eid, door_data in data["doors"].items():
        if door_data["level"] in dataset.levels:
            level_doors.append(eid)
        else:
            other_doors.append(eid)

    return NexusTemplate(fullpath, template_name, data, level_doors, other_doors)


def load_all_templates(dataset, template_dir: str) -> Dict[str, NexusTemplate]:
    """Load all templates into a dictionary within the given template directory"""
    template_set = {
        template_name
        for template_name in os.listdir(template_dir)
        if not template_name.endswith(".json")
    }
    template_set.add("linear")

    template_ord = []
    for template_name in TEMPLATE_PREFERRED_ORDER:
        try:
            template_set.remove(template_name)
        except KeyError:
            pass
        else:
            template_ord.append(template_name)
    template_ord.extend(sorted(template_set))

    return {
        template_name: load_template(dataset, template_dir, template_name)
        for template_name in template_ord
    }


def preprocess_template(template_file: str) -> None:
    """Preprocess the given template file. Will save the preprocessed metadata
    to the save path with an additional ".json" extension.
    """
    LOGGER.info("Processing template %s", template_file)

    with DFReader(open(template_file, "rb")) as reader:
        level = reader.read_level()

    doors = {}
    keys_needed: Dict[int, int] = collections.Counter()
    for eid, (_, _, entity) in level.entities.items():
        if not isinstance(entity, LevelDoor):
            continue

        doors[eid] = {
            "level": entity.file_name.decode(),
            "door": entity.door_set,
        }
        keys_needed[DOOR_INFO[entity.door_set][1]] += 1

    for door_data in doors.values():
        key_type = DOOR_INFO[door_data["door"]][1]
        while key_type < 3 and keys_needed[key_type + 1] == 0:
            key_type += 1
        door_data["key_get"] = key_type

    with open(template_file + ".json", "w") as fout:
        json.dump(
            {"doors": doors},
            fout,
        )


def main():
    """CLI entrypoint for preprocessing nexus templates"""
    parser = ArgumentParser(description="pre-process nexus templates")
    parser.add_argument(
        "nexus_templates",
        nargs="+",
        help="Nexus template files to process",
    )
    args = parser.parse_args()

    for template_file in args.nexus_templates:
        preprocess_template(template_file)


if __name__ == "__main__":
    main()
