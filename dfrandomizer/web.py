import argparse
import hashlib
import io
import json
import os
import random
import time
import urllib.parse

from flask import Flask, Response, request, redirect, render_template

from .dataset import DatasetManager
from .nexus_templates import load_all_templates
from .randomizer import (
    atlas_filter,
    atlas_randomize,
    stock_filter,
    stock_randomize,
    write_level,
)


DEFAULT_ARGS = {
    "atlas": {
        "min-ss": "5",
        "max-ss": "",
        "min-time": "",
        "max-time": "3:00.000",
        "cmp-filter": "",
        "daily-filter": "",
        "community-filter": "",
        "cw-filter": "n",
        "ccw-filter": "n",
        "clunky-filter": "n",
        "backwards-filter": "n",
        "apples-filter": "",
        "required-authors": "",
        "blocked-authors": "",
        "ss-users": "",
        "no-ss-users": "",
        "min-difficulty": "0",
        "max-difficulty": "1000",
        "hide-authors": "",
        "hide-names": "",
        "rand-doors": "",
    },
    "stock": {
        "builtin-filter": "y",
        "stock-filter": "",
        "forest-filter": "",
        "mansion-filter": "",
        "city-filter": "",
        "lab-filter": "",
        "tutorials-filter": "",
        "difficults-filter": "",
        "yotta-filter": "n",
        "old-tutorial-filter": "n",
        "devclip-filter": "n",
        "infini-filter": "n",
        "rand-doors": "normal",
        "hide-names": "",
    }
}

LEVEL_FILTERS = {
    "atlas": atlas_filter,
    "stock": stock_filter,
}

GENERATORS = {
    "atlas": atlas_randomize,
    "stock": stock_randomize,
}


def parse_args():
    parser = argparse.ArgumentParser("create randomized nexus")
    parser.add_argument(
        "randomizer_script",
        help="Randomizer Angelscript to attach to nexuses",
    )
    parser.add_argument(
        "--template_dir",
        default="nexus_templates",
        required=False,
        help="Directory of nexus templates",
    )
    parser.add_argument(
        "--dataset",
        default="dataset",
        required=False,
        help="path to dataset folder",
    )
    parser.add_argument(
        "--old-datasets",
        default=None,
        required=False,
        help="path to folder containing past datasets",
    )
    parser.add_argument(
        "--host",
        default="127.0.0.1",
        required=False,
        help="bind host",
    )
    parser.add_argument(
        "--port",
        default=5000,
        type=int,
        required=False,
        help="bind port",
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
    app.config["MAX_CONTENT_LENGTH"] = 10 * 2**20

    cli_args = parse_args()

    datasets = {}
    nexus_templates = {}

    with open(cli_args.randomizer_script, "rb") as fscript:
        script_data = fscript.read()

    def update_datasets():
        datasets.clear()
        if cli_args.old_datasets:
            for ds_path in os.listdir(cli_args.old_datasets):
                dataset = DatasetManager(os.path.join(cli_args.old_datasets, ds_path))
                dataset.load_levels()
                dataset.load_solvers()
                dataset.load_ranks()
                dataset.load_community_levels()
                dataset.load_banned_levels()
                datasets[dataset.rank_gen_time] = dataset

        dataset = DatasetManager(cli_args.dataset)
        dataset.load_levels()
        dataset.load_solvers()
        dataset.load_ranks()
        dataset.load_community_levels()
        dataset.load_banned_levels()
        datasets[dataset.rank_gen_time] = dataset
        nexus_templates.clear()
        nexus_templates.update(load_all_templates(dataset, cli_args.template_dir))
        return dataset.rank_gen_time

    default_dataset = update_datasets()

    @app.route("/")
    def index():
        return render_template(
            "index.html",
            randomizer_type="atlas",
            dataset_gen_time=default_dataset,
            nexus_templates=nexus_templates,
        )

    @app.route("/atlas")
    def atlas():
        return render_template(
            "index.html",
            randomizer_type="atlas",
            dataset_gen_time=default_dataset,
            nexus_templates=nexus_templates,
        )

    @app.route("/stock")
    def stock():
        return render_template(
            "index.html",
            randomizer_type="stock",
            dataset_gen_time=default_dataset,
            nexus_templates=nexus_templates,
        )

    last_update_time = time.time()

    @app.route("/_update_datasets")
    def update_datasets_view():
        nonlocal last_update_time
        nonlocal default_dataset
        if time.time() - last_update_time > 60:
            default_dataset = update_datasets()
            last_update_time = time.time()
            return "updated"
        return "sleepy"

    @app.route("/generate-link", methods=['POST'])
    def generate_link():
        args = dict(request.form)
        seed = args.get("seed", "")
        if not seed:
            seed = hashlib.sha256(str(time.time_ns()).encode()).hexdigest()[:8]

        default_args = DEFAULT_ARGS.get(args.get("type", ""))
        if default_args is None:
            return Response(
                "invalid generate type",
                status=400,
            )

        nexus_template = nexus_templates.get(args.pop("nexus-template", ""))
        if nexus_template is None:
            return Response(
                "invalid nexus template",
                status=400,
            )

        dataset = datasets.get(args.get("dataset-id"))
        if dataset is None:
            dataset = datasets[default_dataset]

        new_args = {}
        for key, default_val in default_args.items():
            val = args.get(key, default_val)
            if val != default_val:
                new_args[key] = val

        levels = LEVEL_FILTERS[args["type"]](
            dataset,
            nexus_template,
            **{key.replace("-", "_"): val for key, val in new_args.items()},
        )
        if args["type"] != "custom" and len(levels) < len(nexus_template.level_doors):
            return Response(
                f"{len(levels)} matching levels, need {len(nexus_template.level_doors)}",
                status=400,
            )

        new_args.update({
            "type": args["type"],
            "nexus-template": nexus_template.name,
            "seed": seed,
            "dataset-id": dataset.rank_gen_time,
        })

        target = "generate?" + urllib.parse.urlencode(new_args)
        return f"""
<html><head><title>Randomizer Nexus</title>      
</head><body><p>{len(levels)} levels matching constraints.</p>
<p>Download/share this <a href="{target}">link</a>.</p>
</body></html>
"""

    @app.route("/generate")
    def generate():
        args = dict(request.args)

        try:
            dataset_id = int(args.get("dataset-id"))
        except ValueError:
            return Response("invalid dataset", status=400)

        dataset = datasets.get(dataset_id)
        if dataset is None:
            return Response("invalid dataset", status=400)

        nexus_template = nexus_templates.get(args.pop("nexus-template", ""))
        if nexus_template is None:
            return Response(
                "invalid nexus template",
                status=400,
            )

        seed = args.get("seed", "")
        rng = random.Random(seed)

        generator = GENERATORS.get(args.get("type", ""))
        if generator is None:
            return Response("invalid generation type", status=400)

        nexus_data = generator(
            rng,
            dataset,
            nexus_template,
            **{key.replace("-", "_"): val for key, val in args.items()},
        )
        nexus_data["hash"] = hashlib.sha256(
            json.dumps(nexus_data, sort_keys=True).encode()
        ).hexdigest()[:8]
        nexus_data["args"] = args
        nexus_data["template"] = {
            "name": nexus_template.name,
            "level_door_ids": [int(door_id) for door_id in nexus_template.level_doors],
            "level_door_names": [
                nexus_template.data["doors"][door_id]["level"]
                for door_id in nexus_template.level_doors
            ],
        }

        if "json" in args:
            return Response(
                json.dumps(nexus_data, indent=2 if args["json"] == "pretty" else None),
                headers={
                    "Content-Type": "application/json; charset=utf-8",
                }
            )

        with io.BytesIO() as data_out:
            try:
                write_level(
                    dataset,
                    nexus_template,
                    script_data,
                    data_out,
                    nexus_data,
                    **{key.replace("-", "_"): val for key, val in args.items()},
                )
            except ValueError:
                return Response(
                    "invalid arguments",
                    status=400,
                )
            return Response(
                data_out.getvalue(),
                headers={
                    "Content-Type": "application/deflevel",
                    "Content-Disposition": f"inline; filename=\"randomizer-{nexus_data['hash']}.dflevel\"",
                },
            )

    app.run(host=cli_args.host, port=cli_args.port, debug=cli_args.debug)


if __name__ == "__main__":
    main()
