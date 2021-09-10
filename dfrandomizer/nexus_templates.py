import collections
import logging
import json
import os
from typing import Dict

from dustmaker import DFReader
from dustmaker.entity import LevelDoor
from dustmaker.tile import TileSpriteSet

LOGGER = logging.getLogger(__name__)

DOOR_INFO = (
    None,
    (TileSpriteSet.MANSION, 0), # 1
    (TileSpriteSet.MANSION, 2), # 2
    (TileSpriteSet.MANSION, 3), # 3
    (TileSpriteSet.MANSION, 0), # 4
    (TileSpriteSet.FOREST, 0), # 5
    (TileSpriteSet.FOREST, 2), # 6
    (TileSpriteSet.FOREST, 3), # 7
    (TileSpriteSet.FOREST, 0), # 8
    (TileSpriteSet.FOREST, 0), # 9
    (TileSpriteSet.FOREST, 2), # 10
    (TileSpriteSet.FOREST, 3), # 11
    (TileSpriteSet.FOREST, 0), # 12
    (TileSpriteSet.CITY, 0), # 13
    (TileSpriteSet.CITY, 2), # 14
    (TileSpriteSet.CITY, 3), # 15
    (TileSpriteSet.CITY, 0), # 16
    (TileSpriteSet.LABORATORY, 0), # 17
    (TileSpriteSet.LABORATORY, 2), # 18
    (TileSpriteSet.LABORATORY, 3), # 19
    (TileSpriteSet.LABORATORY, 0), # 20
    (TileSpriteSet.TUTORIAL, 0), # 21
    (TileSpriteSet.MANSION, 1), # 22
    (TileSpriteSet.FOREST, 1), # 23
    (TileSpriteSet.CITY, 1), # 24
    (TileSpriteSet.LABORATORY, 1), # 25
    (TileSpriteSet.FOREST, 1), # 26
)


class NexusTemplate:
    def __init__(self, fullpath, name, data, level_doors, other_doors) -> None:
        self.fullpath = fullpath
        self.name = name
        self.data = data
        self.level_doors = level_doors
        self.other_doors = other_doors
        self.level_doors.sort(
            key=lambda eid: DOOR_INFO[self.data["doors"][eid]["door"]][::-1]
        )


def load_template(dataset: 'DatasetManager', template_dir: str, template_name: str) -> NexusTemplate:
    """ Load a template metadata into memory. Uses dataset to determine which
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
    """ Load all templates into a dictionary within the given template directory """
    result = {}
    for template_name in os.listdir(template_dir):
        if template_name.endswith(".json"):
            continue
        result[template_name] = load_template(dataset, template_dir, template_name)
    return result


def preprocess_templates(template_dir: str) -> None:
    """ Preprocess all the doors within the template file to find their IDs,
    mapped level name, and door set type.
    """
    for template_name in os.listdir(template_dir):
        if template_name.endswith(".json"):
            continue
        if os.path.exists(os.path.join(template_dir, template_name + ".json")):
            continue

        LOGGER.info("Processing template %s", template_name)

        with DFReader(open(os.path.join(template_dir, template_name), "rb")) as reader:
            level = reader.read_level()

        doors = {}
        keys_needed = collections.Counter()
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
            

        with open(os.path.join(template_dir, template_name + ".json"), "w") as fout:
            json.dump(
                {"doors": doors},
                fout,
            )
