"""
Module defining logic to compute player and level ranks.
"""

import logging
import math
from typing import Dict, List, Set, Tuple

from sklearn.linear_model import LinearRegression  # type: ignore

# Maps that cannot be part of the randomizer even if otherwise eligible. They
# will also be ignored for player rank and difficulty calculations.

LEVEL_ALPHA = 0.95
PLAYER_ALPHA = 0.90

REGRESSION_SIGMOID_MULT = 2.0
REGRESSION_WEIGHTING = 0.4

LOGGER = logging.getLogger(__name__)


def alpha_sum(A: List[float], alpha: float, s_init: float = 0.0) -> float:
    r"""
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


def predict_sses(
    levels: Dict[str, dict], solvers: Dict[str, List[int]]
) -> Dict[str, float]:
    """Compute linear regression for expected number of SSes based on
    level ID and if the level was the daily.
    """
    dataset: Tuple[List[dict], List[dict]] = ([], [])
    for level, level_solvers in solvers.items():
        leveldata = levels[level]
        dataset[1 if leveldata["was_daily"] else 0].append(
            {
                "level": level,
                "x": [leveldata["atlas_id"]],
                "y": len(level_solvers),
            }
        )

    result: Dict[str, float] = {}
    for dset in dataset:
        x = [datum["x"] for datum in dset]
        y = [datum["y"] for datum in dset]
        lev = [datum["level"] for datum in dset]
        result.update(zip(lev, LinearRegression().fit(x, y).predict(x)))

    return result


def compute_ranks(
    levels: Dict[str, dict],
    solvers: Dict[str, List[int]],
) -> Tuple[Dict[str, float], Dict[int, float]]:
    """Calculate and return a tuple of two mappings using an iterative
    method.  The first maps level IDs to difficulties (between 0.0 and 1.0)
    The second maps player IDs to a skill (between 0.0 and 1.0).

    Formulas are setup so that:

    1. A player solving more levels should increase their skill
    2. A level being solved by more players should decrease its difficulty
    3. A players skill should be affected most by the most difficulty levels they solve
    4. A level's difficulty should be affected most by the lowest skilled player to solve it
    """
    expected_level_sses = predict_sses(levels, solvers)

    # Filter out maps and compute inverse mapping from players to levels.
    player_map: Dict[int, List[str]] = {}
    level_set: Set[str] = set()
    for level, players in solvers.items():
        level_set.add(level)
        for player in players:
            player_map.setdefault(player, []).append(level)

    def naive_difficulty(level):
        ss_count = max(1, len(solvers[level]))
        expected_ss_count = float(max(1, expected_level_sses[level]))

        # sigmoid(ln(a) - ln(b))
        x = math.log(expected_ss_count) - math.log(ss_count)
        return 1.0 / (1.0 + math.exp(-x * REGRESSION_SIGMOID_MULT))

    # Initialize level difficulties and player ranks to 0.5. The algorithm is such
    # that rankings can be between 0 and 1 as the algorithm continues.
    level_score = {level: naive_difficulty(level) for level in level_set}

    player_score = {player: 0.5 for player in player_map}

    # Iterate the calculations until they converge.
    while True:
        # Compute new level diffulty rankings based on previous player rankings.
        # A level's difficulty is dominated by the lowest player ranks to have
        # SS'ed it.
        new_level_score = {}
        for level in level_set:
            players = solvers[level]
            scores = sorted(player_score[player] for player in players)
            base_score = alpha_sum(scores, LEVEL_ALPHA, s_init=1)
            new_level_score[level] = math.pow(
                naive_difficulty(level), REGRESSION_WEIGHTING
            ) * math.pow(
                base_score,
                1.0 - REGRESSION_WEIGHTING,
            )

        # Compute new player rankings based on the previous level difficulties.
        # A player's ranking is dominated by the hardest maps they have SS'ed.
        new_player_score = {}
        for player, player_levels in player_map.items():
            scores = sorted(
                (level_score[level] for level in player_levels),
                reverse=True,
            )
            new_player_score[player] = alpha_sum(scores, PLAYER_ALPHA, s_init=0)

        # Compute squared difference between the last iteration to detect
        # convergence.
        level_ssq = sum(
            (lscore - new_level_score[level]) ** 2
            for level, lscore in level_score.items()
        )
        player_ssq = sum(
            (pscore - new_player_score[player]) ** 2
            for player, pscore in player_score.items()
        )

        level_score = new_level_score
        player_score = new_player_score

        # Wait for convergence and then exit.
        LOGGER.info("Convergence errors %f %f", level_ssq, player_ssq)
        if level_ssq + player_ssq < 1e-11:
            break

    return level_score, player_score
