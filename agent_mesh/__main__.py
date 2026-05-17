"""Module entrypoint for `python -m agent_mesh`."""

import sys

from agent_mesh.cli import app


if __name__ == "__main__":
    raise SystemExit(app(sys.argv[1:]))
