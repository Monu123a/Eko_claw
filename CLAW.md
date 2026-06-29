# Partner Follow-up Claw 🐾 — Submission

> **Track 1 — Forward Deployed AI Accelerator**
> An autonomous agent that owns Eko's partner follow-up workflow end-to-end.

---

## GitHub Link

**[github.com/Monu123a/Eko_claw](https://github.com/Monu123a/Eko_claw)**

---

## Demo Video

**[▶️ Watch the demo](https://drive.google.com/file/d/1ZHbMt4Z27PiyORmK-9_7cTpwOV7-gXEk/view?usp=sharing)**

---

## Platform Integration — Why Hermes Agent

Among **OpenClaw**, **NemoClaw**, **NanoClaw**, and **Hermes Agent**, we chose **Hermes Agent** because:

| Platform | Why not / why yes |
|---|---|
| **Hermes Agent** ✅ | **Native Python SDK** (`pip install`), custom tool contracts via plugin system, built-in persistent memory, self-improving learning loop. Our codebase is Python — Hermes integrates natively. |
| OpenClaw | TypeScript/Node.js core — would require rewriting the entire Python pipeline. |
| NemoClaw | NVIDIA's enterprise governance layer — sits on top of other agents, not a workflow framework itself. |
| NanoClaw | Docker-based security isolation — infrastructure tooling, not a workflow orchestrator. |

### How the integration works

- **`hermes_plugins/`** — Our 5 tools are registered as Hermes-compatible plugins with formal JSON schemas (`schemas.py`) and handler functions (`tools.py`).
- **`hermes_claw.py`** — New entry point that runs the workflow via Hermes Agent's orchestration loop. Falls back gracefully to standalone mode if Hermes isn't installed.
- **Standalone mode** — `run.py` still works exactly as before, no Hermes dependency required.

---

## What the Agent Does — End to End

The Partner Follow-up Claw is an **autonomous agent** (not a chatbot) that owns the daily partner follow-up loop for Eko's ops team. It reads every partner record, understands each situation, decides what to do, acts on it, and produces structured outputs — all without a human in the loop until it encounters uncertainty.

### The 5-stage pipeline

```
data/partners.json
        │
        ▼
┌─────────────────────────────────────────────────────────────────┐
│                    FollowUpClaw  (the agent)                    │
│                                                                 │
│  1. INGEST ─→ 2. TRIAGE ─→ 3. DECIDE ─→ 4. ACT ─→ 5. REPORT  │
│                   │            │           │                    │
│              LLM brain    explicit      tools:                  │
│              or rules     escalation    write reminders,        │
│              (llm.py)     policy        escalation notes,       │
│                          (config.py)    logs, reports           │
└─────────────────────────────────────────────────────────────────┘
        │
        ▼
outputs/run-YYYY-MM-DD/
├── run_report.json       ← structured, machine-readable
├── summary.md            ← daily brief for the ops lead
├── report.html           ← visual report, opens in any browser
├── activity_log.jsonl    ← full audit trail of every action
├── reminders/*.txt       ← drafted WhatsApp-style messages
└── escalations/*.json    ← structured escalation notes
```

**Step by step:**

| Stage | What happens | Where in code |
|---|---|---|
| **INGEST** | Load partner records from JSON (or uploaded file). Validate each record into a typed `Partner` dataclass. | `agent.py → _ingest()` |
| **TRIAGE** | For each partner, the **brain** (LLM or rule-based) classifies: `status` (ON_TRACK / PENDING / DELAYED / HIGH_RISK), `severity`, `sentiment`, a `confidence` score (0–1), a one-line summary, and pending actions we owe them. | `llm.py → classify()` |
| **DECIDE** | An **explicit, auditable escalation policy** turns that understanding into exactly one action: `NO_ACTION`, `SEND_REMINDER`, or `ESCALATE`. The model *interprets*; the policy *decides*. | `agent.py → _decide()` |
| **ACT** | The agent uses **tools** to: draft a warm, situation-specific reminder (via LLM or template), create a structured escalation note routed to the right team, and log every move to a JSONL audit trail. | `agent.py → _act()` + `tools.py` |
| **REPORT** | Emit a structured JSON report, a human-readable markdown brief, and a self-contained HTML report. | `agent.py → _build_report()`, `_build_summary()`, `_build_html()` |

**Why split TRIAGE and DECIDE?** This is the core design choice. The LLM interprets the messy human reality (Hinglish notes, ambiguous status). But the *decision to escalate* is governed by transparent, tunable rules in `config.py` — including the rule that if the model's confidence is too low, it escalates to a human instead of guessing. This makes the agent safe to run autonomously.

---

## Input and Output Examples

### Input — a partner record (`data/partners.json`)

```json
{
  "id": "EKO-1003",
  "name": "Khan Telecom Point",
  "owner": "Imran Khan",
  "region": "Bhopal, MP",
  "segment": "Distributor",
  "monthly_volume_inr": 76000,
  "last_contact_date": "2026-06-09",
  "followups_sent": 2,
  "awaiting_response": true,
  "open_issue": "Settlement of 4,300 INR pending for 3 days; partner is upset.",
  "notes": "High-volume distributor. Last message: 'paisa abhi tak nahi aaya, customers wait kar rahe hain'. Risk of churn — competitor agent in same market."
}
```

### Output 1 — Console (what the agent prints)

```
Partner Follow-up Claw  |  reference date: 2026-06-28  |  brain: free LLM (llama-3.3-70b-versatile)
----------------------------------------------------------------
  EKO-1001  Sunrise Mobile & Recharge      -> NO_ACTION     [ON_TRACK, conf 0.90]
  EKO-1002  Maa Vaishno Kirana Store       -> SEND_REMINDER [PENDING, conf 0.80]
  EKO-1003  Khan Telecom Point             -> ESCALATE      [HIGH_RISK, conf 0.90]
  EKO-1004  Janseva CSC Kendra             -> ESCALATE      [PENDING, conf 0.80]
  EKO-1005  New Bharat Mobile              -> ESCALATE      [HIGH_RISK, conf 0.80]
  EKO-1006  Shree Ganesh Communications    -> SEND_REMINDER [PENDING, conf 0.90]
  EKO-1007  Annapurna Digital Seva         -> SEND_REMINDER [ON_TRACK, conf 0.90]
----------------------------------------------------------------
SUMMARY  reviewed=7  reminders=3  escalations=3  no_action=1
```

### Output 2 — Structured escalation note (`escalations/EKO-1003.json`)

```json
{
  "partner_id": "EKO-1003",
  "partner_name": "Khan Telecom Point",
  "owner": "Imran Khan",
  "region": "Bhopal, MP",
  "segment": "Distributor",
  "monthly_volume_inr": 76000,
  "status": "HIGH_RISK",
  "severity": "high",
  "sentiment": "negative",
  "confidence": 0.9,
  "days_since_last_contact": 19,
  "open_issue": "Settlement of 4,300 INR pending for 3 days; partner is upset.",
  "summary": "High-volume distributor Khan Telecom Point has a pending settlement issue and is at risk of churn due to competitor presence",
  "pending_actions": [
    "Verify settlement of 4,300 INR",
    "Respond to partner's concern about pending amount",
    "Offer resolution to prevent churn"
  ],
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

### Output 3 — Drafted reminder (`reminders/EKO-1002.txt`)

```
Hi Sunita ji, hope you're doing well. We're still working on your KYC,
will get DMT enabled soon. Can you please confirm if all documents are
uploaded correctly? Need your help to move forward.
```

### Output 4 — Daily brief (`summary.md`)

```markdown
# Partner Follow-up — Daily Brief

**Run:** run-2026-06-28  |  **Brain:** free LLM (llama-3.3-70b-versatile)

- Partners reviewed: **7**
- Reminders drafted: **3**
- Escalations created: **3**
- On track / no action: **1**

## Escalations (need a human)

### EKO-1003 — Khan Telecom Point (HIGH)
- High-volume distributor with pending settlement; at risk of churn
  - No contact for 19 days (>= 14).
  - High-risk / high-severity situation flagged in triage.
  - Negative partner sentiment detected.
  - Key partner (volume INR 76000) is stalled.

### EKO-1005 — New Bharat Mobile (HIGH)
- Stopped transacting, unresponsive to follow-ups
  - No contact for 31 days (>= 14).
  - 3 follow-ups with no response.

## Reminders drafted

- **Maa Vaishno Kirana Store** (EKO-1002): Awaits DMT enablement after KYC steps sent 10 days ago
- **Shree Ganesh Communications** (EKO-1006): Wants confirmation on next incentive payout
- **Annapurna Digital Seva** (EKO-1007): Active and growing, routine check-in
```

---

## Tools, APIs, Models, and Databases Used

| Category | What | Purpose |
|---|---|---|
| **Agent platform** | Hermes Agent (Nous Research) | Orchestration, tool-calling, plugin system |
| **Language** | Python 3.10+ | Core agent logic |
| **LLM — free path** | Groq (Llama 3.3 70B) or Google Gemini 2.0 Flash via OpenAI-compatible SDK | Triage classification + reminder drafting. No credit card needed. |
| **LLM — paid path** | Anthropic Claude (claude-opus-4-8) with structured outputs | Higher-quality triage when available |
| **Fallback brain** | Deterministic rule-based engine (keyword + threshold matching) | Always works — no key, no internet |
| **Web UI** | Streamlit | Interactive browser-based runner (optional) |
| **Data store** | JSON file (`data/partners.json`) | Simulates CRM / database read |
| **Persistent memory** | SQLite (`data/memory.db`) | Tracks partner interaction history across runs |
| **Ticket system** | SQLite (`data/tickets.db`) | Simulates Jira/Zoho — escalations create tickets with team routing |
| **Send queue** | SQLite (`data/send_queue.db`) | Simulated WhatsApp Business API — reminders enqueued for delivery |
| **Agent tools** | Formal tool contracts in `hermes_plugins/schemas.py` | 5 tools with JSON input/output schemas |
| **Structured outputs** | JSON + dataclasses (`schemas.py`) | Typed data between stages; machine-readable escalation notes |
| **Config / Policy** | `config.py` | All escalation thresholds in one auditable file |
| **Tests** | pytest (54 tests) | Escalation policy, low-confidence routing, malformed LLM, fallback mode, memory, tickets, send queue |

### Key design: the agent has **tools, not just text**

The agent doesn't just generate prose. It performs concrete actions:
- **Writes reminder files** to `reminders/<partner_id>.txt`
- **Enqueues reminders** in the WhatsApp send queue (ready for real API)
- **Creates structured escalation notes** to `escalations/<partner_id>.json`
- **Creates tickets** in the SQLite ticket system (routed to the right team)
- **Records every action** in persistent memory (SQLite) to prevent duplicate escalations
- **Appends to an audit log** (`activity_log.jsonl`) for every action
- **Emits a structured JSON report** for downstream consumption
- **Generates a self-contained HTML report** that opens in any browser with zero setup

---

## Exception Handling and Escalation Logic

### Exception handling — the agent never crashes

| Failure mode | How the agent handles it | Where in code |
|---|---|---|
| **No API key** | Falls through to the rule-based brain automatically. The run always completes. | `llm.py → _provider()` |
| **LLM API call fails** (timeout, rate limit, 500, bad JSON) | Catches the exception, prints a warning, falls back to rule-based classification for that partner. The rest of the run continues. | `llm.py → classify()` L124–132 |
| **Reminder drafting fails** | Falls back to a warm, human-written template. Never leaves a partner without a message. | `llm.py → draft_reminder()` L144–168 |
| **Malformed JSON from LLM** | Tolerant parser strips markdown fences, extracts JSON via regex, validates and normalises every field. | `llm.py → _extract_json()`, `_classification_from_json()` |
| **`response_format: json_object` unsupported** by provider | Retries without the parameter automatically. | `llm.py → _chat_openai()` L203–210 |
| **Data file not found** | Prints a clear error and exits before starting the pipeline. | `run.py` L56–58 |
| **Status value not in vocabulary** | Normalises to `PENDING` rather than crashing. | `llm.py → _classification_from_json()` L244 |

### Escalation logic — the transparent policy

All thresholds live in [`src/config.py`](src/config.py) and are **separate from the LLM's judgement**. A partner is escalated to a human when **any** of these conditions hold:

| Rule | Threshold | Rationale |
|---|---|---|
| Silence too long | `days_since_contact ≥ 14` | Prolonged silence = likely problem |
| High-risk triage | status = `HIGH_RISK` or severity = `high` | Settlement issues, device failures, churn signals |
| Negative sentiment | sentiment = `negative` | An upset partner needs human attention |
| Key partner stalled | `monthly_volume ≥ ₹50,000` + status is `DELAYED` / `HIGH_RISK` | Protect high-value relationships |
| Repeated no-response | `followups_sent ≥ 3` + still awaiting response | Likely churn |
| **Low model confidence** | `confidence < 0.55` | **The agent escalates rather than acts on a shaky read** — this is the feature most "agent" demos skip |

If none of these trigger: send a **gentle reminder** if there's an open thread or a check-in is due, otherwise **no action**.

**Why is this important?** The LLM *interprets* messy real-world data (Hinglish notes, ambiguous statuses). But it doesn't get to decide on its own whether to act or escalate. The policy decides. That's what makes it safe to run autonomously.

---

## What the Current Version Can Do Autonomously

1. **Ingest** partner records from a structured JSON data store.
2. **Understand** each partner's situation using an LLM (Groq / Gemini / Claude), including reading Hinglish notes and inferring sentiment — with a deterministic fallback that works offline.
3. **Classify** every partner on 4 dimensions: status, severity, sentiment, and model confidence.
4. **Decide** the right action for each partner using an explicit, auditable policy.
5. **Draft** warm, situation-specific WhatsApp-style reminders tailored to each partner's context.
6. **Create** structured escalation notes with the issue, reasons for escalation, pending actions, and the recommended internal owner (Finance, Field Support, Key Account Manager, etc.).
7. **Route** escalations to the right team based on the nature of the issue.
8. **Log** every action to a JSONL audit trail.
9. **Report** in three formats: machine-readable JSON, human-readable markdown brief, and a visual HTML report.
10. **Handle failure gracefully** — LLM outages, malformed responses, missing keys — the agent always completes the run.
11. **Escalate on uncertainty** — if the model isn't confident enough, it routes to a human instead of guessing.
12. **Run via CLI or web UI** — `python run.py` for scripts/cron, `streamlit run app.py` for interactive use.

The full pipeline runs **without any human input** and produces a complete, actionable daily brief.

---

## What the Next Version Would Improve

| Area | What we'd build | Impact |
|---|---|---|
| **Real data sources** | Swap `partners.json` for live reads from Eko's CRM / Google Sheet / database. | Agent runs on real, current data instead of a snapshot. |
| **Real WhatsApp delivery** | Swap `_simulate_send()` in `send_queue.py` with the **WhatsApp Business API** HTTP call. The queue infrastructure is already built. | The agent doesn't just draft — it *delivers*. |
| **Real ticketing** | Swap the SQLite `TicketStore` with **Jira / Zoho API** calls. The ticket schema and routing logic are already built. | Escalations flow into the team's real workflow. |
| **Scheduling** | Run the agent every morning as a cron job / Cloud Function. Push the daily brief to a **Slack channel**. | Zero-touch daily ops workflow. |
| **Feedback loop** | Track which reminders actually got a response. Use the signal to **tune policy thresholds** (e.g., adjust `REMIND_AFTER_DAYS`, `MIN_CONFIDENCE`). | The agent improves itself over time. |
| **Multi-language reminders** | Draft messages in Hindi, Bengali, Tamil — not just English/Hinglish — based on the partner's region. | Better partner experience. |
| **Richer triage** | Pull in transaction volume trends, last-N-interactions history, and regional churn data to give the LLM more signal. | Higher-quality classifications with fewer false escalations. |
| **Human-in-the-loop UI** | After an escalation, the human marks it as resolved/overridden in the ticket system. The agent learns from overrides. | Closes the autonomy loop — the agent gets better from human corrections. |
| **Batch + streaming modes** | Support both daily batch runs (all partners) and real-time event-driven triggers (e.g., a settlement fails → immediately classify and escalate that one partner). | Faster response to urgent issues. |

---

## Project Structure

```
partner-followup-claw/
├── run.py                 # CLI entry point (standalone)
├── hermes_claw.py         # Hermes Agent entry point
├── app.py                 # Streamlit web UI
├── requirements.txt
├── .env.example           # brain configuration (optional)
├── CLAW.md                # ← this file
├── README.md              # full documentation
├── hermes_plugins/        # Hermes Agent tool integration
│   ├── plugin.yaml        # plugin manifest
│   ├── __init__.py        # tool registration
│   ├── schemas.py         # formal JSON tool contracts (input/output)
│   └── tools.py           # tool handler wrappers
├── data/
│   ├── partners.json      # sample partner records (7 partners)
│   ├── memory.db          # persistent memory (auto-created)
│   ├── tickets.db         # ticket system (auto-created)
│   └── send_queue.db      # WhatsApp queue (auto-created)
├── src/
│   ├── config.py          # escalation policy + thresholds
│   ├── schemas.py         # typed data structures between stages
│   ├── llm.py             # the brain: free LLM / Claude / rule-based fallback
│   ├── tools.py           # the agent's actions (write reminders, escalations, logs)
│   ├── agent.py           # the 5-stage orchestration pipeline
│   ├── memory.py          # SQLite persistent memory across runs
│   ├── tickets.py         # SQLite ticket system (simulates Jira/Zoho)
│   └── send_queue.py      # simulated WhatsApp Business API send queue
├── tests/                 # 54 tests
│   ├── test_escalation_policy.py
│   ├── test_low_confidence.py
│   ├── test_malformed_llm.py
│   ├── test_fallback_mode.py
│   ├── test_memory.py
│   ├── test_tickets.py
│   └── test_send_queue.py
└── outputs/
    └── run-2026-06-28/    # example run output
```

---

## Quick Start

```bash
# Clone and run — no API key needed (rule-based brain works offline):
git clone https://github.com/Monu123a/Eko_claw.git
cd Eko_claw
python run.py --today 2026-06-28

# Hermes Agent mode (with Hermes installed):
python hermes_claw.py --today 2026-06-28

# For a real LLM brain (free, no credit card):
pip install openai
export LLM_API_KEY=gsk_...          # from https://console.groq.com
export LLM_BASE_URL=https://api.groq.com/openai/v1
export LLM_MODEL=llama-3.3-70b-versatile
python run.py --today 2026-06-28

# Run all tests:
python -m pytest tests/ -v

# Web UI:
pip install streamlit
streamlit run app.py
```

---

*Built by Harsh Ahlawat for Eko's Forward Deployed AI Accelerator track.*
