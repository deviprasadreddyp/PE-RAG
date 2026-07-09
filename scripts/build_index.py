"""Build the full offline index: run every pipeline stage in order.

    python scripts/build_index.py        # ingest -> ... -> store  (embed needs OPENAI_API_KEY)
    python scripts/build_index.py --force

Thin wrapper over ``src.run`` so the whole index builds with one command.
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.run import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main(["--stage", "all", *sys.argv[1:]]))
