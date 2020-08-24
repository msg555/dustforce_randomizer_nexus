#!/usr/bin/env python3

import json
import sys


def main():
  """
  Print out Anglescript author dictionary data to be copied into
  randomizer_authors.h.
  """
  data = json.load(sys.stdin)  
  for level, author in data.items():
    print("  {%s, %s}," % (repr(level), repr(author)))


if __name__ == "__main__":
  main()
