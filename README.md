# Partner Follow-up Claw 🐾

**An autonomous AI agent that owns the partner follow-up workflow end-to-end** — it
reads partner data, understands each situation, decides what to do, drafts reminders,
creates structured escalation notes, and routes high-risk or uncertain cases to a
human. Built for **Eko's** mission of empowering micro-entrepreneur partners.

> Track 1 — Forward Deployed AI Accelerator. An agent, not a chatbot: it **acts**,
> produces **structured outputs**, and **escalates** when it isn't sure.

---

## Why this, for Eko

Eko's partners — kirana stores, mobile shops, CSC centres — are livelihoods. When a
settlement is stuck or a partner goes quiet, every day of delay risks churn and lost
income. Today an ops person manually scans a list, decides who to chase, writes
messages, and flags the serious cases. **This agent owns that loop.**

### Before → After

| Manual follow-up (today) | Partner Follow-up Claw |
|---|---|
| Person eyeballs a spreadsheet daily | Agent ingests every partner record |
| Judges status case-by-case | Triages each one (status, severity, sentiment, confidence) |
| Decides who to chase | Applies an explicit, auditable escalation policy |
| Types reminders one by one | Drafts tailored reminder messages |
| Flags serious cases in their head | Creates structured escalation notes routed to the right team |
| No paper trail | Every action logged; a daily brief + JSON report |

---

## What makes it a *real* agent (not a chatbot)

1. **Owns a bounded workflow** — one clear job, run end-to-end, no human in the loop until escalation.
2. **It acts via tools** — writes reminders, escalation notes, logs, and reports to disk.
3. **Structured outputs** — every run emits machine-readable JSON, not just prose.
4. **Handles uncertainty** — when the model's confidence is low, the agent *escalates to a human instead of guessing.* This is the feature most "agent" demos skip.
5. **Auditable policy** — the decision to escalate is governed by explicit rules in [config.py](src/config.py), separate from the model's judgement.

---

## Architecture

```
                         ┌──────────────────────────────────────────────┐
   data/partners.json ──▶│              FollowUpClaw  (the agent)         │
                         │                                                │
                         │  INGEST → TRIAGE → DECIDE → ACT → REPORT        │
                         │            │        │       │                  │
                         │       ┌────┘   ┌────┘   ┌───┴────────┐         │
                         │   Claude /   explicit   tools (write  │         │
                         │   rule-based  escalation reminders,   │         │
                         │   brain       policy     escalations, │         │
                         │   (llm.py)   (config.py) logs, report)│         │
                         └──────────────────────────────┬───────┘         │
                                                        ▼
                                          outputs/run-YYYY-MM-DD/
                                          ├── run_report.json   (structured)
                                          ├── summary.md        (daily brief)
                                          ├── activity_log.jsonl(audit trail)
                                          ├── reminders/*.txt
                                          └── escalations/*.json
```

### The 5-stage pipeline

| Stage | What happens |
|---|---|
| **INGEST** | Load partner records from the data store. |
| **TRIAGE** | For each partner, the **brain** classifies `status`, `severity`, `sentiment`, a `confidence` score, a one-line summary, and the pending actions we owe them. |
| **DECIDE** | An explicit **escalation policy** turns that understanding into exactly one action: `NO_ACTION`, `SEND_REMINDER`, or `ESCALATE`. |
| **ACT** | The agent uses **tools** to draft a reminder, create a structured escalation note (routed to the right team), and log every move. |
| **REPORT** | Emits a structured JSON report + a human-readable daily brief. |

**Why split TRIAGE and DECIDE?** The model *interprets*; the *policy decides*. That
keeps the agent's behaviour transparent and safe — and lets it escalate on low
confidence rather than act on a shaky read.

---

## The escalation policy (transparent + tunable)

All thresholds live in [src/config.py](src/config.py). A partner is escalated to a human when **any** of these hold:

- No contact for **≥ 14 days**
- Triage flags **HIGH_RISK** or **high severity** (e.g. stuck settlement, device down)
- **Negative sentiment** detected
- A **key partner** (monthly volume ≥ ₹50,000) is stalled
- **≥ 3 follow-ups** with no response (likely churn)
- **Model confidence < 0.55** → too uncertain to act safely → route to a human

Otherwise: a gentle **reminder** if there's an open thread or a check-in is due,
else **no action**.

---

## The brain: pluggable, with a deterministic fallback

The agent works with any of three brains, picked automatically at runtime — in this
priority order:

1. **A free LLM** (Groq, Google Gemini, or any OpenAI-compatible endpoint) — set
   `LLM_API_KEY` + `LLM_BASE_URL`. **No credit card needed.**
2. **Anthropic / Claude** (`claude-opus-4-8` by default) — set `ANTHROPIC_API_KEY`.
3. **Rule-based fallback** — no key, no internet. Always works.

Whichever brain is active reads each partner like an ops person would, returns a
validated structured classification, and drafts warm, situation-specific reminders.
The logic in [agent.py](src/agent.py) is **provider-agnostic** — only [llm.py](src/llm.py)
knows which brain is talking. This means the demo is **robust** (never crashes for
lack of a key) while using **real LLM understanding** whenever a key is present.

### Using a free LLM (recommended for the demo)

```bash
pip install openai            # the only dependency needed for free providers

# --- Groq (free, very fast) — get a key at https://console.groq.com ---
export LLM_API_KEY=gsk_...
export LLM_BASE_URL=https://api.groq.com/openai/v1
export LLM_MODEL=llama-3.3-70b-versatile

python run.py --today 2026-06-28
```

Google Gemini works the same way (key from <https://aistudio.google.com/app/apikey>):
```bash
export LLM_API_KEY=AIza...
export LLM_BASE_URL=https://generativelanguage.googleapis.com/v1beta/openai/
export LLM_MODEL=gemini-2.0-flash
```

See [.env.example](.env.example) for all options.

---

## Run it in the browser (Streamlit) 🌐

```bash
pip install streamlit          # one-time
streamlit run app.py
```

This opens a web app at <http://localhost:8501>. Pick the brain in the sidebar
(default is the free, offline rule-based one), optionally paste a **free** Groq/
Gemini key, set the reference date, and click **Run agent**. You get live metrics,
a decisions table, expandable escalation notes and drafted reminders, and download
buttons for the JSON report and brief. Any key you paste is kept in memory for the
run only — never written to disk.

> If `streamlit` isn't found on your PATH, use `python -m streamlit run app.py`.

## Run it on the command line

```bash
# Runs immediately with the rule-based brain — no install, no key:
python run.py --today 2026-06-28
```

To use a real LLM brain (optional), add a key — a **free** one works fine:

```bash
pip install -r requirements.txt
cp .env.example .env       # then paste a free Groq/Gemini key (see below)
python run.py --today 2026-06-28
```

### Example run

```
Partner Follow-up Claw  |  reference date: 2026-06-28  |  brain: rule-based fallback
----------------------------------------------------------------
  EKO-1001  Sunrise Mobile & Recharge      -> NO_ACTION     [ON_TRACK, conf 0.60]
  EKO-1002  Maa Vaishno Kirana Store       -> SEND_REMINDER [PENDING, conf 0.60]
  EKO-1003  Khan Telecom Point             -> ESCALATE      [HIGH_RISK, conf 0.70]
  EKO-1004  Janseva CSC Kendra             -> ESCALATE      [HIGH_RISK, conf 0.70]
  EKO-1005  New Bharat Mobile              -> ESCALATE      [HIGH_RISK, conf 0.70]
  EKO-1006  Shree Ganesh Communications    -> SEND_REMINDER [PENDING, conf 0.60]
  EKO-1007  Annapurna Digital Seva         -> SEND_REMINDER [ON_TRACK, conf 0.60]
----------------------------------------------------------------
SUMMARY  reviewed=7  reminders=3  escalations=3  no_action=1
```

### Example escalation note (structured output, routed to a team)

```json
{
  "partner_id": "EKO-1003",
  "partner_name": "Khan Telecom Point",
  "status": "HIGH_RISK",
  "severity": "high",
  "sentiment": "negative",
  "confidence": 0.7,
  "days_since_last_contact": 19,
  "open_issue": "Settlement of 4,300 INR pending for 3 days; partner is upset.",
  "escalation_reasons": [
    "No contact for 19 days (>= 14).",
    "High-risk / high-severity situation flagged in triage.",
    "Negative partner sentiment detected.",
    "Key partner (volume INR 76000) is stalled."
  ],
  "recommended_owner": "Finance / Settlements team",
  "created_at": "2026-06-28"
}
```

---

## CLI options

```
python run.py [--data PATH] [--out DIR] [--today YYYY-MM-DD] [--no-llm]
```

| Flag | Purpose |
|---|---|
| `--data` | Partner JSON file (default `data/partners.json`) |
| `--out` | Output directory (default `outputs/`) |
| `--today` | Reference date — pin it for deterministic, reproducible runs |
| `--no-llm` | Force the rule-based brain (no API calls) |

---

## Project structure

```
partner-followup-claw/
├── run.py                 # CLI entry point
├── requirements.txt
├── .env.example
├── data/
│   └── partners.json      # sample partner records
└── src/
    ├── config.py          # escalation policy + thresholds (the agent's "rules")
    ├── schemas.py         # typed data passed between stages
    ├── llm.py             # the brain: Claude + rule-based fallback
    ├── tools.py           # the agent's actions (write reminders/escalations/logs/report)
    └── agent.py           # the 5-stage orchestration pipeline
```

---

## How I'd extend it (productionising)

- **Real data sources:** swap `partners.json` for a CRM / Google Sheet / database read.
- **Real actions:** wire the reminder tool to the WhatsApp Business API; push escalation notes into Jira/Zoho as tickets.
- **Scheduling:** run it every morning as a cron job → a daily ops brief in Slack.
- **Feedback loop:** track which reminders got a response to tune the policy thresholds.
- **Memory:** remember prior runs so the agent escalates faster on repeat offenders.

---

*Built as a small but real agentic workflow for Eko's Forward Deployed AI Accelerator track.*
