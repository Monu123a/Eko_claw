#!/usr/bin/env python3
"""CLI entry point for the Partner Follow-up Claw.

Examples:
    python run.py                       # run on sample data
    python run.py --no-llm              # force the rule-based brain
    python run.py --today 2026-06-28    # pin the reference date (deterministic)
    python run.py --data my_partners.json --out runs
"""

import argparse
import os
import sys
from datetime import datetime, date

# Load .env if python-dotenv is installed (optional convenience).
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from src import config
from src.agent import FollowUpClaw


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Partner Follow-up Claw — autonomous follow-up agent")
    p.add_argument("--data", default=config.DEFAULT_DATA_PATH,
                   help="path to partners JSON (default: %(default)s)")
    p.add_argument("--out", default=config.DEFAULT_OUTPUT_DIR,
                   help="output directory (default: %(default)s)")
    p.add_argument("--today", default=None,
                   help="reference date YYYY-MM-DD (default: system date). "
                        "Use 2026-06-28 to reproduce the demo numbers.")
    p.add_argument("--no-llm", action="store_true",
                   help="force the deterministic rule-based brain (no API calls)")
    return p.parse_args()


def main() -> int:
    args = parse_args()

    if args.no_llm:
        # Hide the key so llm_available() returns False for this run.
        os.environ.pop("ANTHROPIC_API_KEY", None)

    reference = None
    if args.today:
        try:
            reference = datetime.strptime(args.today, "%Y-%m-%d").date()
        except ValueError:
            print("error: --today must be YYYY-MM-DD", file=sys.stderr)
            return 2

    if not os.path.exists(args.data):
        print("error: data file not found: %s" % args.data, file=sys.stderr)
        return 2

    claw = FollowUpClaw(reference_date=reference, output_dir=args.out)
    claw.run(args.data)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
