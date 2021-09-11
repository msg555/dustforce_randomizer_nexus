#!/usr/bin/env python3
"""
Classes and functions for managing nexus templates.

If you want to add a new nexus template run 

./nexus_template.py nexus_template_file [other_template_file ...]
"""
import collections
import logging
import json
import os
from typing import Dict, Iterable

from dustmaker import DFReader
from dustmaker.entity import LevelDoor
from dustmaker.tile import TileSpriteSet

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


def load_template(
    dataset: DatasetManager, template_dir: str, template_name: str
) -> NexusTemplate:
    """Load a template metadata into memory. Uses dataset to determine which
    levels correspond to playable levels rather than other nexuses.
    """
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
    result = {}
    for template_name in os.listdir(template_dir):
        if template_name.endswith(".json"):
            continue
        result[template_name] = load_template(dataset, template_dir, template_name)
    return result


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
