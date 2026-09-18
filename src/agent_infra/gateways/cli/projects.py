"""Project argument definitions; behavior is injected by the composition root."""

import argparse


def add_init_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("directory", nargs="?", help="New project directory (must not exist)")
    parser.add_argument(
        "--directory", dest="directory_option", help="Alternative to positional directory"
    )
    parser.add_argument("--goal", required=True, help="Original research goal; saved verbatim")
    parser.add_argument(
        "--name", help="Display name; used for directory name when no path is supplied"
    )
    parser.add_argument("--root", help="Parent projects directory (default: environment or cwd)")
    parser.add_argument(
        "--state-dir", help="Control state root (default: environment or user state)"
    )
    parser.add_argument(
        "--operation-id", help="Idempotency key, especially for automatic directory names"
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Preview files without writing anything"
    )
