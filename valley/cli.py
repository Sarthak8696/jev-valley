"""Command line entry point. Subcommands are added phase by phase."""

import argparse
import os
import sys
from pathlib import Path

from valley import __version__

VIEWER_PATH = Path(__file__).resolve().parent.parent / "viewer" / "index.html"
CACHE_DIR = ".valley-cache"


def _seed_list(text: str) -> list[int]:
    return [int(part) for part in text.split(",") if part.strip()]


def _size(text: str) -> tuple[int, int]:
    try:
        width, height = text.lower().split("x")
        return int(width), int(height)
    except ValueError:
        raise argparse.ArgumentTypeError(f"size must look like 28x18, not {text!r}") from None


def _add_model_settings(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--batch", type=int, default=16, help="creatures per request (default 16)")
    parser.add_argument("--workers", type=int, default=4, help="parallel requests per brain (default 4)")
    parser.add_argument("--timeout", type=float, default=30, help="hard timeout in seconds per request")


def _add_run_arguments(parser: argparse.ArgumentParser, log_default: bool) -> None:
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--days", type=int, default=30)
    parser.add_argument("--size", type=_size, default=(28, 18), help="map size, such as 28x18")
    parser.add_argument("--max-creatures", type=int, default=50)
    parser.add_argument("--brain", default="rules", help="jev, laya, rules, random or system-one@URL#MODEL")
    parser.add_argument("--prey-brain", default=None, help="brain for rabbits and deer (default: --brain)")
    parser.add_argument("--wolf-brain", default=None, help="brain for wolves (default: --brain)")
    parser.add_argument("--hesitate-below", type=float, default=None, metavar="CONFIDENCE",
                        help="freeze for the hour when the model's confidence is below this")
    _add_model_settings(parser)
    parser.add_argument("--log-requests", action=argparse.BooleanOptionalAction, default=log_default,
                        help="write every request and response to requests.jsonl")
    parser.add_argument("--cache", action="store_true", help=f"cache responses in {CACHE_DIR}/ (never used by bench)")
    parser.add_argument("--out", default=None, help="output directory (default runs/<run id>)")
    parser.add_argument("--run-id", default=None)


def _run_spec(args, experiment: str):
    from valley import bench
    prey = args.prey_brain or args.brain
    wolf = args.wolf_brain or args.brain
    return bench.RunSpec(
        seed=args.seed, brains={"rabbit": prey, "deer": prey, "wolf": wolf}, experiment=experiment, days=args.days,
        width=args.size[0], height=args.size[1], max_creatures=args.max_creatures,
        hesitate_below=args.hesitate_below, batch=args.batch, workers=args.workers, timeout=args.timeout,
        log_requests=args.log_requests, cache_dir=CACHE_DIR if args.cache else None, run_id=args.run_id)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m valley",
        description="Jev Valley: a simulated valley whose animals decide through a typed decision model.",
    )
    parser.add_argument("--version", action="version", version=f"jev-valley {__version__}")
    sub = parser.add_subparsers(dest="command", metavar="<subcommand>")

    tune = sub.add_parser("tune", help="check the balance targets, or fix hesitation thresholds from smoke runs")
    tune.add_argument("--check", action="store_true", help="run rules and random and report each target")
    tune.add_argument("--thresholds", nargs="+", metavar="RUN_DIR", default=None,
                      help="smoke run folders to take each brain's 10th and 25th percentile confidence from")
    tune.add_argument("-o", "--output", default=None, help="where to write the thresholds (default results/hesitation/thresholds.json)")
    tune.add_argument("--seeds", type=_seed_list, default=None, help="comma-separated seeds (default: the ten benchmark seeds)")
    tune.add_argument("--days", type=int, default=30)
    tune.add_argument("--jobs", type=int, default=min(8, os.cpu_count() or 1), help="parallel processes")
    return parser


def _tune(args) -> int:
    from valley import tuning
    if args.thresholds:
        path = args.output or os.path.join("results", "hesitation", "thresholds.json")
        try:
            thresholds = tuning.thresholds_from_runs(args.thresholds)
        except (OSError, ValueError) as error:
            print(f"error: {error}", file=sys.stderr)
            return 2
        tuning.write_thresholds(path, thresholds)
        for brain, values in thresholds["brains"].items():
            print(f"{brain}: p10 {values['p10']:.4f}, p25 {values['p25']:.4f} from {values['decisions']:,} decisions")
        print(f"wrote {path}")
        return 0
    if not args.check:
        print("nothing to do: pass --check, or --thresholds RUN_DIR [RUN_DIR ...]", file=sys.stderr)
        return 2
    result = tuning.run_check(args.seeds or tuning.BENCH_SEEDS, args.days, jobs=args.jobs)
    print(tuning.format_report(result))
    return 0 if result["passed"] else 1


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    handlers = {"tune": _tune}
    if args.command is None:
        parser.print_help()
        return 0
    return handlers[args.command](args)
