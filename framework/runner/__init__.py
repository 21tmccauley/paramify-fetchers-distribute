"""Paramify fetcher framework runner — package + back-compat CLI entry point.

The command surface now lives in ``framework.cli`` (the unified ``paramify``
Typer app). This module is kept for two reasons:

1. **Back-compat:** ``python -m framework.runner <cmd>`` still works — ``main()``
   delegates to the same Typer app, so every documented command keeps running.
2. **Package home:** ``framework.api`` imports sibling submodules from this
   package (``from framework.runner import manifest_loader``; lazy
   ``framework.runner.executor``). Those modules are unchanged.

The Typer app is imported *lazily inside* ``main()`` so that importing this
package (which ``framework.api`` does) never pulls in Typer and never creates a
cli -> api -> runner import cycle.

See ``framework/cli.py`` for the full command reference, or run ``paramify
--help``.
"""

import sys


def main(argv=None) -> int:
    """Run the unified CLI. Kept so `python -m framework.runner ...` still works.

    Delegates to the `paramify` Typer app. Typer/Click exits via SystemExit with
    the right code, so this normally does not return; the trailing `return 0`
    only matters if the app is ever run in non-standalone mode.
    """
    from framework.cli import app
    app(args=argv)
    return 0


if __name__ == "__main__":
    sys.exit(main())
