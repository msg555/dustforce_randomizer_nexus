#!/usr/bin/env python3

import collections
import json
import logging
import os
import re
import sys

from dustmaker import read_map
import requests

# Maps that cannot be part of the randomizer even if otherwise eligible. They
# will also be ignored for player rank and difficulty calculations.
BANNED_MAPS = {
  "16-Red-Adventure-5400",
  "--4078",
  "3-Days-2294",
  "Abrupt-3235",
  "AircomboGalore-v2-2606",
  "Amathophobia-3407",
  "Annony-2968",
  "AppleGlider-3286",
  "Gloomy-Cavern-2914",
  "Grasslands-975",
  "High-School-1993",
  "Highrise-1107",
  "Hop-4621",
  "Infini-Walls-4260",
  "Infinite-wall-jump-710",
  "Invaded-Forest-Cave-1090",
  "Island-Hopping-4383",
  "Krankdud-Trololo-Party-4303",
  "Late-night-cleanup-1182",
  "Magnetzip-2078",
  "My-Test-Level-1151",
  "New-Nexus-3163",
  "No-Way-Back-4748",
  "Race-2-Announcement-786",
  "Shot-By-The-Bullet-2139",
  "Smile-3812",
  "Spike-Jump-Phobia-3569",
  "Take-Out-the-Trash-3893",
  "The-Cliff-3745",
  "Triangle-Boost-425",
  "Vertical-Freestyle-2280",
  "Wall-Climb-Quirk-402",
  "Waste-of-Time-4883",
  "Whee-3511",
  "awqvcsz-4252",
  "bears-question-mark-1072",
  "petadifficult",
  "titan",
  "wall-cancEL-2792",
  "Ascent-Backwards-2896",
  "Construction-Site-Backwards-2870",
  "Summit-Backwards-2893",
  "Ancient-Garden-Backwards-2891",
  "Hideout-5270",
  "The-Garage-5342",
  "Filthy-Climb-5384",
  "Bounding-Box-5446",
  "slish-dirty-5528",
  "Tera-x1-5545",
  "Tera-x0-5546",
  "First-5586",
  "Gotta-go-fast-5587",
  "Dont-mess-up-1510",
  "Alcoves-CW-5707",
  "Tower-CW-5722",
  "First Level-97",
  "Superdrop-Mash-Macro-5932",
  "Twirlie-Test-Chamber-5942",
  "Yotta-Practice-4-5963",
  "Puzzle-Room-1-5979",
  "Still-Without-Friends-6006",
  "dumb-puzzle-thingy-thing-6088",
  "ledge-cancel-6103",
  "fuhh-you-sheila-6372",
  "mattttttt1-106",
  "mattttttt1-104",
  "Ascensionist-6413",
  "unnamed-120",
  "Dash-Attack-and-Jump-Attack-Practice-661",
  "Spike-Jump-811",
  "Snowflakes-828",
  "AERIAL-ASSAULT-1747",
  "upload-test-2081",
  "nodustkid-2793",
  "3-bit-3246",
  "hubproj02-3533",
  "Broom-Closet-TestDock-3787",
  "Sightseeing-4131",
  "Shadow-Halls-4267",
  "Vacant-Lot-4274",
  "Dashing-Over-Ledges-Practice-4331",
  "shitmap-6421",
  "Clunky-Overgrown-Temple-6632",
  "Two-New-Cards-8172",
  "Dustworth-advanced-course-7106",
  "Downhill-x100-7011",
  "terakid-7001",
  "insane-gimmicks-6993",
  "itaydash-7087",
  "Pokemon-Stadium-2-6913",
  "lmao-new-tech-7409",
  "lmao-crowdsourcing-7407",
  "Difficult-But-Easy-8181",
  "Garbage-Day-7562",
  "Lunar-Temple-7600",
  "The-Virus-7724",
  "Ressurection-7996",
  "DONTPLAY-8239",
  "Penumbra-8090",
  "birb-house-6-8788",
  "8-tall-birbs-8790",
  "djskjdkfjdk-8376",
  "Downtrill-8472",
  "Full-Nelson-8739",
  "Huge-8929",
  "Cream-Soda-8914",
  "Streets-of-Rage-2065",
}

LEVEL_ALPHA = 0.9
PLAYER_ALPHA = 0.99

MIN_PLAYER_THRESHOLD = 5

LOGGER = logging.getLogger(__name__)


def alpha_sum(A, alpha, s_init=0):
  """
  Compute a decaying sum as

  s_init * alpha^|A| + \sum_i (1-alpha)*alpha^i * A_i

  You can consider this an infinite average where elements in the front are
  weighted more heavily than later elements and the back of the list is filled
  with an infinite sequence of elements of value s_init.
  """
  s = s_init
  for x in A[::-1]:
    s *= alpha
    s += (1 - alpha) * x
  return s


def main():
  """
  Run player rank/level difficulty calculation and fill in metadata.
  """
  logging.basicConfig(stream=sys.stderr, level=logging.INFO, format='%(message)s')

  # Load solver dataset into memory.
  with open("dataset/solvers.json") as fdata:
    level_map = json.load(fdata)

  # Filter out maps and compute inverse mapping from players to levels.
  player_map = {}
  for level, players in list(level_map.items()):
    if len(players) < MIN_PLAYER_THRESHOLD or level in BANNED_MAPS:
      del level_map[level]
    else:
      for player in players:
        player_map.setdefault(player, []).append(level)

  # Initialize level difficulties and player ranks to 0.5. The algorithm is such
  # that rankings can be between 0 and 1 as the algorithm continues.
  level_score = {
    level: 0.5 for level in level_map
  }
  player_score = {
    player: 0.5 for player in player_map
  }

  # Iterate the calculations until they converge.
  while True:
    # Compute new level diffulty rankings based on previous player rankings.
    # A level's difficulty is dominated by the lowest player ranks to have
    # SS'ed it.
    new_level_score = {}
    for level, players in level_map.items():
      scores = sorted(
        player_score[player] for player in players
      )
      new_level_score[level] = alpha_sum(
        scores,
        LEVEL_ALPHA,
        s_init=1,
      )

    # Compute new player rankings based on the previous level difficulties.
    # A player's ranking is dominated by the hardest maps they have SS'ed.
    new_player_score = {}
    for player, levels in player_map.items():
      scores = sorted(
        (level_score[level] for level in levels),
        reverse=True,
      )
      new_player_score[player] = alpha_sum(
        scores,
        PLAYER_ALPHA,
        s_init=0,
      )

    # Compute squared difference between the last iteration to detect
    # convergence.
    level_ssq = 0
    for level in level_score:
      level_ssq += (level_score[level] - new_level_score[level]) ** 2
    player_ssq = 0
    for player in player_score:
      player_ssq += (player_score[player] - new_player_score[player]) ** 2

    level_score = new_level_score
    player_score = new_player_score

    # Wait for convergence and then exit.
    LOGGER.info("Convergence errors %f %f", level_ssq, player_ssq)
    if level_ssq + player_ssq < 1e-11:
      break

  # Sort levels by difficulty
  levels = sorted(level_score, key=lambda level: level_score[level])
  data_out = {}

  # Load maps into levels directory as needed.
  session = requests.Session()
  for level in levels:
    if os.path.exists("levels/{}".format(level)):
      continue
    match = re.search(r"-([0-9]+)$", level)
    if not match:
      continue

    response = session.get(
      "http://atlas.dustforce.com/gi/downloader.php?id={}".format(match.group(1)),
      stream=True,
    )
    if response.status_code != 200:
      continue

    with open("levels/{}".format(level), "wb") as fout:
      for chunk in response.iter_content(1024):
        fout.write(chunk)

  # Add tile metadata for each map.
  for level in levels:
    try:
      LOGGER.info("Processing %s", level)

      with open("levels/{}".format(level), "rb") as f:
        mp = read_map(f.read())

      tile_types = collections.Counter()
      for (layer, x, y), tile in mp.tiles.items():
        tile_types[tile.sprite_set()] += 1

      data_out[level] = {
        "tiles": {
          int(tile_type): count for tile_type, count in tile_types.items()
        },
        "difficulty": level_score[level],
      }
    except Exception:
      LOGGER.exception("Failed to prase level %s", level)

  # Output result to standard out.
  json.dump(data_out, sys.stdout, indent=2)
  sys.stdout.write("\n")


if __name__ == "__main__":
  main()
