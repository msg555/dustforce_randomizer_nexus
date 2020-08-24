#!/usr/bin/env python3
import sys

from dustmaker import read_map, LevelDoor

LEVELS = [
  "downhill", "shadedgrove", "dahlia", "fields",
  "momentum", "fireflyforest", "tunnels", "momentum2",
  "suntemple", "ascent", "summit", "grasscave",
  "den", "autumnforest", "garden", "hyperdifficult",
  
  "atrium", "secretpassage", "alcoves", "mezzanine",
  "cave", "cliffsidecaves", "library", "courtyard",
  "precarious", "treasureroom", "arena", "ramparts",
  "moontemple", "observatory", "parapets", "brimstone",
    
  "vacantlot", "sprawl", "development", "abandoned",
  "park", "boxes", "chemworld", "factory", 
  "tunnel", "basement", "scaffold", "cityrun",
  "clocktower", "concretetemple", "alley", "hideout",
        
  "control", "ferrofluid", "titan", "satellite",
  "vat", "venom", "security", "mary",
  "wiringfixed", "containment", "orb", "pod",
  "mary2", "coretemple", "abyss", "dome",
]


def main():
  """
  Compute the mapping of levels to entity IDs from the source map.
  """
  mp = read_map(sys.stdin.buffer.read())

  mapping = {}
  for entity_id, (x, y, entity) in mp.entities.items():
    if isinstance(entity, LevelDoor):
      mapping[entity.file_name()] = entity_id

  for level in LEVELS:
    print("  {}, # {}".format(mapping[level], level))


if __name__ == "__main__":
  main()
