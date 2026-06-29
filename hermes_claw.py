#!/usr/bin/env python3
"""Hermes Agent entry point for the Partner Follow-up Claw.

This wraps the existing agent as a Hermes-orchestrated workflow. Hermes
calls our tools via the plugin system (hermes_plugins/) and orchestrates
the 5-stage pipeline using its own planning + tool-calling loop.

    Usage (with Hermes Agent installed):
        python hermes_claw.py --today 2026-06-28

    Without Hermes installed, falls back to the standalone pipeline:
        python run.py --today 2026-06-28

Why Hermes Agent?
    Among OpenClaw / NemoClaw / NanoClaw / Hermes, we chose Hermes because:
    - Native Python SDK (pip install) — our codebase is Python.
    - Custom tool contracts via a plugin system with JSON schemas.
    - Built-in persistent memory across runs.
    - Self-improving learning loop (skills distillation).
    OpenClaw and NemoClaw are TypeScript/Node.js — would require rewriting.
    NanoClaw is Docker-focused infra, not a workflow framework.
"""

import argparse
import json
import os
import sys
from datetime import datetime, date

# Load .env if python-dotenv is installed.
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from src import config

# The Hermes system prompt tells the agent what workflow to follow.
SYSTEM_PROMPT = """\
You are the Partner Follow-up Claw — an autonomous agent that owns the daily
partner follow-up workflow for Eko's ops team.

You have 5 tools. Run them in this exact order:

1. **ingest_partners** — load partner data from the JSON file.
2. **triage_partner** — for EACH partner, classify their situation.
3. Based on the triage, decide the action:
   - ESCALATE if: days_since_contact >= 14, or status is HIGH_RISK, or
     severity is high, or sentiment is negative, or (monthly_volume >= 50000
     and status is DELAYED/HIGH_RISK), or followups_sent >= 3 with no response,
     or confidence < 0.55.
   - SEND_REMINDER if: there's an open issue, awaiting response, days >= 5,
     or status is PENDING/DELAYED (and no escalation trigger).
   - NO_ACTION otherwise.
4. **draft_reminder** — for each SEND_REMINDER partner.
5. **create_escalation** — for each ESCALATE partner.
6. After processing all partners, summarise the results.

Be concise. Act, don't chat. Process every partner.
"""


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Partner Follow-up Claw — Hermes Agent entry point")
    p.add_argument("--data", default=config.DEFAULT_DATA_PATH,
                   help="path to partners JSON (default: %(default)s)")
    p.add_argument("--out", default=config.DEFAULT_OUTPUT_DIR,
                   help="output directory (default: %(default)s)")
    p.add_argument("--today", default=None,
                   help="reference date YYYY-MM-DD (default: system date)")
    p.add_argument("--no-llm", action="store_true",
                   help="force the deterministic rule-based brain")
    return p.parse_args()


def run_with_hermes(args) -> int:
    """Run the workflow via Hermes Agent's orchestration loop."""
    try:
        from run_agent import AIAgent
    except ImportError:
        print("Hermes Agent not installed. Install with:")
        print("  pip install git+https://github.com/NousResearch/hermes-agent.git")
        print("\nFalling back to standalone mode...\n")
        return run_standalone(args)

    reference = args.today or date.today().isoformat()

    # Initialise Hermes with our system prompt.
    agent = AIAgent(
        model=os.environ.get("LLM_MODEL", "llama-3.3-70b-versatile"),
        quiet_mode=False,
    )

    # Register our tools from the plugin.
    from hermes_plugins import register

    class PluginContext:
        """Minimal context adapter for Hermes plugin registration."""
        def __init__(self):
            self.tools = {}

        def register_tool(self, schema, handler):
            self.tools[schema["name"]] = {"schema": schema, "handler": handler}

    ctx = PluginContext()
    register(ctx)

    # Build the task prompt.
    task = (
        "Run the partner follow-up workflow for reference date %s. "
        "Data file: %s. Process every partner." % (reference, args.data)
    )

    print("=" * 64)
    print("Partner Follow-up Claw  |  Hermes Agent mode")
    print("Reference date: %s" % reference)
    print("=" * 64)

    # Run the conversation.
    result = agent.run_conversation(
        user_message=task,
        system_message=SYSTEM_PROMPT,
    )

    print("\n" + "=" * 64)
    print("Hermes Agent run complete.")
    print("=" * 64)
    return 0


def run_standalone(args) -> int:
    """Fallback: run the standalone pipeline (same as run.py)."""
    from src.agent import FollowUpClaw

    if args.no_llm:
        os.environ.pop("ANTHROPIC_API_KEY", None)
        os.environ.pop("LLM_API_KEY", None)

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


def main() -> int:
    args = parse_args()

    # Try Hermes first; fall back to standalone.
    try:
        return run_with_hermes(args)
    except Exception as exc:
        print("\nHermes orchestration failed: %s" % exc)
        print("Falling back to standalone mode...\n")
        return run_standalone(args)


if __name__ == "__main__":
    raise SystemExit(main())
