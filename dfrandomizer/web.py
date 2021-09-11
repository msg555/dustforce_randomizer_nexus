"""
Flask web app definition around the randomizer
"""
import hashlib
import io
import json
import os
import random
import time
from typing import Dict
import urllib.parse

from flask import Flask, Response, request, render_template

from .dataset import DatasetManager
from .nexus_templates import NexusTemplate, load_all_templates
from .randomizer import (
    atlas_filter_levels,
    atlas_randomize,
    stock_filter_levels,
    stock_randomize,
    write_level,
)
from .util import ArgumentParser


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
    },
}

LEVEL_FILTERS = {
    "atlas": atlas_filter_levels,
    "stock": stock_filter_levels,
}

GENERATORS = {
    "atlas": atlas_randomize,
    "stock": stock_randomize,
}


class FlaskRandomizer:
    """Flask app wrapper for the randomizer"""

    def __init__(
        self,
        dataset_path: str,
        template_dir: str,
        script_data: bytes,
        *,
        old_datasets_dir: str = "",
    ) -> None:
        self.dataset_path = dataset_path
        self.template_dir = template_dir
        self.script_data = script_data
        self.old_datasets_dir = old_datasets_dir

        self.app = Flask("dfrandomizer")
        self.app.config["MAX_CONTENT_LENGTH"] = 10 * 2 ** 20
        self.app.add_url_rule("/", view_func=self.atlas_view)
        self.app.add_url_rule("/atlas", view_func=self.atlas_view)
        self.app.add_url_rule("/stock", view_func=self.stock_view)
        self.app.add_url_rule("/_update_datasets", view_func=self.update_datasets_view)
        self.app.add_url_rule(
            "/generate-link", view_func=self.generate_link_view, methods=["POST"]
        )
        self.app.add_url_rule("/generate", view_func=self.generate_view)

        self.datasets: Dict[int, DatasetManager] = {}
        self.nexus_templates: Dict[str, NexusTemplate] = {}
        self.default_dataset_id = 0
        self.last_update_time = time.time()
        self.update_datasets()

    def update_datasets(self) -> None:
        """Update datasets used to generate nexuses. Also updates nexus template
        information.
        """
        self.datasets.clear()
        if self.old_datasets_dir:
            for ds_path in os.listdir(self.old_datasets_dir):
                dataset = DatasetManager(os.path.join(self.old_datasets_dir, ds_path))
                dataset.load_levels()
                dataset.load_solvers()
                dataset.load_ranks()
                dataset.load_community_levels()
                dataset.load_banned_levels()
                self.datasets[dataset.rank_gen_time] = dataset

        dataset = DatasetManager(self.dataset_path)
        dataset.load_levels()
        dataset.load_solvers()
        dataset.load_ranks()
        dataset.load_community_levels()
        dataset.load_banned_levels()
        self.datasets[dataset.rank_gen_time] = dataset
        self.default_dataset_id = dataset.rank_gen_time

        self.nexus_templates.clear()
        self.nexus_templates.update(load_all_templates(dataset, self.template_dir))

    def atlas_view(self):
        """Render the atlas randomizer UI"""
        return render_template(
            "index.html",
            randomizer_type="atlas",
            dataset_gen_time=self.default_dataset_id,
            nexus_templates=self.nexus_templates,
        )

    def stock_view(self):
        """Render the stock randomizer UI"""
        return render_template(
            "index.html",
            randomizer_type="stock",
            dataset_gen_time=self.default_dataset_id,
            nexus_templates=self.nexus_templates,
        )

    def update_datasets_view(self):
        """Backend URL to trigger an update of the datasets"""
        if time.time() - self.last_update_time > 60:
            self.update_datasets()
            self.last_update_time = time.time()
            return "updated"
        return "sleepy"

    def generate_link_view(self):
        """Verify and report the number of available levels and yield a
        permanent link if there are enough to create a randomizer.
        """
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

        nexus_template = self.nexus_templates.get(args.pop("nexus-template", ""))
        if nexus_template is None:
            return Response(
                "invalid nexus template",
                status=400,
            )

        dataset = self.datasets.get(args.get("dataset-id"))
        if dataset is None:
            dataset = self.datasets[self.default_dataset_id]

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

        new_args.update(
            {
                "type": args["type"],
                "nexus-template": nexus_template.name,
                "seed": seed,
                "dataset-id": dataset.rank_gen_time,
            }
        )

        target = "generate?" + urllib.parse.urlencode(new_args)
        return f"""
<html><head><title>Randomizer Nexus</title>      
</head><body><p>{len(levels)} levels matching constraints.</p>
<p>Download/share this <a href="{target}">link</a>.</p>
</body></html>
"""

    def generate_view(self):
        """Generate the requested randomizer nexus"""
        args = dict(request.args)

        try:
            dataset_id = int(args.get("dataset-id"))
        except ValueError:
            return Response("invalid dataset", status=400)

        dataset = self.datasets.get(dataset_id)
        if dataset is None:
            return Response("invalid dataset", status=400)

        nexus_template = self.nexus_templates.get(args.pop("nexus-template", ""))
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

        randomizer_hash = hashlib.sha256(
            json.dumps(nexus_data.as_json(), sort_keys=True).encode()
        ).hexdigest()[:8]
        json_data = {
            "args": args,
            "hash": randomizer_hash,
            "template": {
                "name": nexus_template.name,
                "level_door_ids": [
                    int(door_id) for door_id in nexus_template.level_doors
                ],
                "level_door_names": [
                    nexus_template.data["doors"][door_id]["level"]
                    for door_id in nexus_template.level_doors
                ],
            },
            **nexus_data.as_json(),
        }

        if "json" in args:
            return Response(
                json.dumps(json_data, indent=2 if args["json"] == "pretty" else None),
                headers={
                    "Content-Type": "application/json; charset=utf-8",
                },
            )

        with io.BytesIO() as data_out:
            try:
                write_level(
                    dataset,
                    nexus_template,
                    self.script_data,
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
                    "Content-Disposition": f'inline; filename="randomizer-{randomizer_hash}.dflevel"',
                },
            )


def parse_args():
    """Parse CLI arguments"""
    parser = ArgumentParser(description="create randomized nexus")
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


def main() -> None:
    """CLI entrypoint for the flask-based web server"""
    args = parse_args()

    with open(args.randomizer_script, "rb") as fscript:
        script_data = fscript.read()

    randomizer = FlaskRandomizer(
        args.dataset,
        args.template_dir,
        script_data,
        old_datasets_dir=args.old_datasets,
    )
    randomizer.app.run(host=args.host, port=args.port, debug=args.debug)


if __name__ == "__main__":
    main()
