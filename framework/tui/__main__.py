"""Launch the TUI: python -m framework.tui [--manifest PATH] [--at ROOT]

Both this module entry point and the unified CLI's `paramify tui` subcommand
call launch(), so the two paths stay in lock-step.
"""

import argparse
from typing import Optional

from framework.tui.app import FetcherApp


def launch(manifest: Optional[str] = None, at: Optional[str] = None) -> None:
    """Run the terminal UI. Shared by `paramify tui` and `python -m framework.tui`."""
    FetcherApp(manifest_path=manifest, root_override=at).run()


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="framework.tui", description="Fetcher console (terminal UI)"
    )
    parser.add_argument(
        "--manifest",
        default=None,
        help="manifest to open directly, skipping the welcome screen "
        "(default: show the welcome / manifest picker)",
    )
    parser.add_argument(
        "--at",
        default=None,
        help="repo root override (default: discovered by walking up)",
    )
    args = parser.parse_args()
    launch(args.manifest, args.at)


if __name__ == "__main__":
    main()
