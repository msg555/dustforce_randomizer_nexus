#!/usr/bin/env python3
"""
Simple CLI script to extract the first script out of a level file. This is used
to extract the nexus script out of the level it was compiled into.

Usage:

./extract_script.py < level.dflevel > script.bin
"""
import sys

from dustmaker import DFReader


def main():
    """CLI entry point for extracting randomizer script from a level"""
    with DFReader(sys.stdin.buffer) as reader:
        level = reader.read_level()

    sys.stdout.buffer.write(level.variables["scripts"][0])


if __name__ == "__main__":
    main()
