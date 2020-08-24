#!/usr/bin/env python3

import json
import sys


def main():
  """
  Format output from rank.py into level_data listings that can be
  copied into randomizer_data.h.
  """
  data = json.load(sys.stdin)  
  for level, leveldata in data.items():
    tile_counts = [0, 0, 0, 0, 0]
    for idx, cnt in leveldata["tiles"].items():
      tile_counts[int(idx) - 1] += cnt

    print('  level_data({}, {}, {}, {}, {}, {}, {}),'.format(
      repr(level),
      *tile_counts,
      leveldata["difficulty"],
    ))


if __name__ == "__main__":
  main()
