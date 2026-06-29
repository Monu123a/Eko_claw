"""Formal tool contracts (JSON schemas) for the Partner Follow-up Claw.

Each schema defines the input/output contract for one agent tool, following
the Hermes Agent plugin convention. These schemas are what the LLM "sees"
when deciding which tool to call and how to call it.
"""

# ---------------------------------------------------------------------------
# Tool 1: ingest_partners
# ---------------------------------------------------------------------------
INGEST_PARTNERS_SCHEMA = {
    "name": "ingest_partners",
    "description": (
        "Load partner records from a JSON file. Returns a list of partner "
        "objects and the total count. This is always the first step."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "data_path": {
                "type": "string",
                "description": "Path to the partners JSON file (e.g. 'data/partners.json').",
            }
        },
        "required": ["data_path"],
    },
    "returns": {
        "type": "object",
        "properties": {
            "partners": {
                "type": "array",
                "description": "List of partner record objects.",
                "items": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "string"},
                        "name": {"type": "string"},
                        "owner": {"type": "string"},
                        "region": {"type": "string"},
                        "segment": {"type": "string"},
                        "monthly_volume_inr": {"type": "integer"},
                        "last_contact_date": {"type": "string", "format": "date"},
                        "followups_sent": {"type": "integer"},
                        "awaiting_response": {"type": "boolean"},
                        "open_issue": {"type": ["string", "null"]},
                        "notes": {"type": "string"},
                    },
                },
            },
            "count": {"type": "integer", "description": "Number of partners loaded."},
        },
    },
}

# ---------------------------------------------------------------------------
# Tool 2: triage_partner
# ---------------------------------------------------------------------------
TRIAGE_PARTNER_SCHEMA = {
    "name": "triage_partner",
    "description": (
        "Classify a single partner's situation. Returns status (ON_TRACK / "
        "PENDING / DELAYED / HIGH_RISK), severity, sentiment, confidence "
        "(0-1), a one-line summary, and pending actions we owe them."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "partner_id": {"type": "string", "description": "The partner's ID (e.g. EKO-1003)."},
            "reference_date": {
                "type": "string",
                "format": "date",
                "description": "The reference date for the run (YYYY-MM-DD).",
            },
        },
        "required": ["partner_id", "reference_date"],
    },
    "returns": {
        "type": "object",
        "properties": {
            "status": {"type": "string", "enum": ["ON_TRACK", "PENDING", "DELAYED", "HIGH_RISK"]},
            "severity": {"type": "string", "enum": ["low", "medium", "high"]},
            "sentiment": {"type": "string", "enum": ["positive", "neutral", "negative"]},
            "confidence": {"type": "number", "minimum": 0, "maximum": 1},
            "summary": {"type": "string"},
            "pending_actions": {"type": "array", "items": {"type": "string"}},
            "source": {"type": "string", "description": "Which brain produced this (rules / free-llm / claude)."},
        },
    },
}

# ---------------------------------------------------------------------------
# Tool 3: draft_reminder
# ---------------------------------------------------------------------------
DRAFT_REMINDER_SCHEMA = {
    "name": "draft_reminder",
    "description": (
        "Draft a warm, WhatsApp-style follow-up message for a partner. "
        "The message is saved to disk and enqueued in the send queue."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "partner_id": {"type": "string"},
            "partner_name": {"type": "string"},
            "owner": {"type": "string", "description": "The partner shop owner's name."},
            "region": {"type": "string"},
            "summary": {"type": "string", "description": "One-line summary of the partner's situation."},
            "pending_actions": {
                "type": "array",
                "items": {"type": "string"},
                "description": "What we owe the partner.",
            },
        },
        "required": ["partner_id", "partner_name", "owner", "region", "summary"],
    },
    "returns": {
        "type": "object",
        "properties": {
            "message": {"type": "string", "description": "The drafted reminder text."},
            "source": {"type": "string", "description": "How it was generated (free-llm / claude / template)."},
            "file_path": {"type": "string", "description": "Path where the reminder was saved."},
        },
    },
}

# ---------------------------------------------------------------------------
# Tool 4: create_escalation
# ---------------------------------------------------------------------------
CREATE_ESCALATION_SCHEMA = {
    "name": "create_escalation",
    "description": (
        "Create a structured escalation note for a partner that needs human "
        "attention. The note is saved to disk and a ticket is created."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "partner_id": {"type": "string"},
            "partner_name": {"type": "string"},
            "owner": {"type": "string"},
            "region": {"type": "string"},
            "segment": {"type": "string"},
            "monthly_volume_inr": {"type": "integer"},
            "status": {"type": "string"},
            "severity": {"type": "string", "enum": ["low", "medium", "high"]},
            "sentiment": {"type": "string", "enum": ["positive", "neutral", "negative"]},
            "confidence": {"type": "number"},
            "days_since_last_contact": {"type": "integer"},
            "open_issue": {"type": ["string", "null"]},
            "summary": {"type": "string"},
            "pending_actions": {"type": "array", "items": {"type": "string"}},
            "escalation_reasons": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["partner_id", "partner_name", "status", "severity", "escalation_reasons"],
    },
    "returns": {
        "type": "object",
        "properties": {
            "file_path": {"type": "string", "description": "Path to the escalation JSON file."},
            "ticket_id": {"type": "integer", "description": "ID of the created ticket."},
            "recommended_owner": {"type": "string", "description": "Which team should handle this."},
        },
    },
}

# ---------------------------------------------------------------------------
# Tool 5: generate_report
# ---------------------------------------------------------------------------
GENERATE_REPORT_SCHEMA = {
    "name": "generate_report",
    "description": (
        "Generate the final run report: a structured JSON report, a "
        "human-readable markdown brief, and a self-contained HTML report."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "run_id": {"type": "string", "description": "Run identifier (e.g. 'run-2026-06-28')."},
            "records": {
                "type": "array",
                "description": "List of per-partner result records from the pipeline.",
                "items": {"type": "object"},
            },
        },
        "required": ["run_id", "records"],
    },
    "returns": {
        "type": "object",
        "properties": {
            "report_path": {"type": "string"},
            "summary_path": {"type": "string"},
            "html_path": {"type": "string"},
            "totals": {
                "type": "object",
                "properties": {
                    "partners_reviewed": {"type": "integer"},
                    "reminders_drafted": {"type": "integer"},
                    "escalations_created": {"type": "integer"},
                    "no_action": {"type": "integer"},
                },
            },
        },
    },
}

# ---------------------------------------------------------------------------
# All schemas (for registration)
# ---------------------------------------------------------------------------
ALL_SCHEMAS = [
    INGEST_PARTNERS_SCHEMA,
    TRIAGE_PARTNER_SCHEMA,
    DRAFT_REMINDER_SCHEMA,
    CREATE_ESCALATION_SCHEMA,
    GENERATE_REPORT_SCHEMA,
]
