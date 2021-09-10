import sys

from dustmaker import DFReader

with DFReader(sys.stdin.buffer) as reader:
    level = reader.read_level()

sys.stdout.buffer.write(level.variables["scripts"][0])
