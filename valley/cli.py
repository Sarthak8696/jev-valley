"""Command line entry point. Subcommands are added phase by phase."""

import argparse

from valley import __version__


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m valley",
        description="Jev Valley: a simulated valley whose animals decide through a typed decision model.",
    )
    parser.add_argument("--version", action="version", version=f"jev-valley {__version__}")
    parser.add_subparsers(dest="command", metavar="<subcommand>")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command is None:
        parser.print_help()
    return 0
