"""Launch the web UI: python -m framework.web [--host H] [--port P] [--reload]

Both this module entry point and the unified CLI's `paramify web` subcommand
call launch(), so the two paths stay in lock-step.
"""

import argparse

import uvicorn


def launch(host: str = "127.0.0.1", port: int = 8765, reload: bool = False) -> None:
    """Run the web server. Shared by `paramify web` and `python -m framework.web`."""
    uvicorn.run("framework.web.server:app", host=host, port=port, reload=reload)


def main() -> None:
    parser = argparse.ArgumentParser(prog="framework.web", description="Fetcher console")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--reload", action="store_true", help="auto-reload on code changes")
    args = parser.parse_args()
    launch(args.host, args.port, args.reload)


if __name__ == "__main__":
    main()
