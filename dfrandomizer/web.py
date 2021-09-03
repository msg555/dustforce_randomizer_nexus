import argparse
import hashlib
import io
import random
import time
import urllib.parse

from flask import Flask, Response, request, redirect

from .dataset import DatasetManager
from .randomizer import randomize_atlas, randomize_stock, write_level


def parse_args():
    parser = argparse.ArgumentParser("create randomized nexus")
    parser.add_argument(
        "randomizer_template",
        help="randomizer level binary file",
    )
    parser.add_argument(
        "--dataset",
        default="dataset",
        required=False,
        help="path to dataset folder",
    )
    parser.add_argument(
        "--debug",
        action="store_const",
        const=True,
        default=False,
    )
    return parser.parse_args()


def main():
    app = Flask("dfrandomizer")

    cli_args = parse_args()
    dataset = DatasetManager(cli_args.dataset)
    dataset.load_levels()
    dataset.load_ranks()

    @app.route("/")
    def index():
        return app.send_static_file("_index.html")

    @app.route("/generate-link")
    def generate_link():
        args = dict(request.args)
        if not args.get("seed"):
            args["seed"] = hashlib.sha256(str(time.time_ns()).encode()).hexdigest()[:8]
        if args.get("levelset") == "atlas":
            del args["levelset"]
        if args.get("min-difficulty") == "0" or args.get("levelset", "").startswith("stock-"):
            del args["min-difficulty"]
        if args.get("max-difficulty") == "10000" or args.get("levelset", "").startswith("stock-"):
            del args["max-difficulty"]

        target = "generate?" + urllib.parse.urlencode(args)
        return f"""
<html><head><title>Randomizer Nexus</title>      
<meta http-equiv="refresh" content="0;URL='{target}'" />
</head><body><p>Download should begin automatically. Share this <a href="{target}">download
link</a>.</p>
</body></html>
"""

    @app.route("/generate")
    def generate():
        args = dict(request.args)

        min_difficulty = 0.0
        try:
            min_difficulty = int(args.get("min-difficulty", "0")) / 10000
        except ValueError:
            pass
        min_difficulty = max(0.0, min(min_difficulty, 1.0))

        max_difficulty = 1.0
        try:
            max_difficulty = int(args.get("max-difficulty", "10000")) / 10000
        except ValueError:
            pass
        max_difficulty = max(0.0, min(max_difficulty, 1.0))

        rng = random.Random(args.get("seed", ""))
        levelset = args.get("levelset", "atlas")
        if levelset == "atlas-no-cmp":
            levels, gen_id = randomize_atlas(rng, dataset, min_difficulty, max_difficulty, False, True)
        elif levelset == "cmp":
            levels, gen_id = randomize_atlas(rng, dataset, min_difficulty, max_difficulty, True, False)
        elif levelset == "stock-64":
            levels, gen_id = randomize_stock(rng, False, False, False)
        elif levelset == "stock-75":
            levels, gen_id = randomize_stock(rng, False, True, False)
        elif levelset == "stock-77":
            levels, gen_id = randomize_stock(rng, False, True, True)
        else:
            levels, gen_id = randomize_atlas(rng, dataset, min_difficulty, max_difficulty, False, False)

        full_seed = f"{gen_id};{args.get('seed', '')}"
        with io.BytesIO() as data_out:
            internal_seed_name = write_level(
                dataset,
                cli_args.randomizer_template,
                data_out,
                levels,
                full_seed,
                bool(args.get("no-authors")),
            )
            return Response(
                data_out.getvalue(),
                headers={
                    "Content-Type": "application/deflevel",
                    "Content-Disposition": f"inline; filename=\"randomizer-{internal_seed_name}\"",
                },
            )

    app.run(debug=cli_args.debug)


if __name__ == "__main__":
    main()