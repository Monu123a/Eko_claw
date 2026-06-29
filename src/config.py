"""Central configuration for the Partner Follow-up Claw.

Everything that controls the agent's *policy* lives here so the behaviour is
auditable and tunable in one place — not buried in the code.
"""

import os

# --- LLM brain -------------------------------------------------------------
# Default to the most capable model. Override with ANTHROPIC_MODEL if needed.
MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-opus-4-8")

# --- Escalation policy (deterministic, human-readable rules) ---------------
# These thresholds turn an "assistant" into an agent that owns a decision.
ESCALATE_AFTER_DAYS = 14          # silence longer than this -> escalate
HIGH_VALUE_VOLUME_INR = 50000     # monthly volume that makes a partner "key"
MAX_FOLLOWUPS_BEFORE_ESCALATION = 3   # repeated no-response -> escalate
MIN_CONFIDENCE = 0.55             # below this, the agent escalates rather than act

# Days of silence after which an active partner gets a gentle reminder.
REMIND_AFTER_DAYS = 5

# --- Status vocabulary -----------------------------------------------------
STATUS_ON_TRACK = "ON_TRACK"
STATUS_PENDING = "PENDING"
STATUS_DELAYED = "DELAYED"
STATUS_HIGH_RISK = "HIGH_RISK"
ALL_STATUSES = [STATUS_ON_TRACK, STATUS_PENDING, STATUS_DELAYED, STATUS_HIGH_RISK]

# --- Action vocabulary -----------------------------------------------------
ACTION_NONE = "NO_ACTION"
ACTION_REMIND = "SEND_REMINDER"
ACTION_ESCALATE = "ESCALATE"

# --- Paths -----------------------------------------------------------------
DEFAULT_DATA_PATH = "data/partners.json"
DEFAULT_OUTPUT_DIR = "outputs"
