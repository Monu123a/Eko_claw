"""The agent's brain.

Three interchangeable brains, picked automatically at runtime:

  1. FREE provider (Groq / Google Gemini / any OpenAI-compatible endpoint)
     -> used when LLM_API_KEY + LLM_BASE_URL are set. No credit card needed.
  2. Anthropic / Claude  -> used when ANTHROPIC_API_KEY is set.
  3. Rule-based fallback -> always works, no key, no internet.

This keeps the demo robust (it ALWAYS runs) while letting you use a real LLM for
free. The agent's logic is provider-agnostic — only this file knows which brain
is talking.
"""

import json
import os
import re
from typing import Tuple

from . import config
from .schemas import Partner, Classification

# Both SDKs are optional at import time — the agent still runs without them.
try:
    import anthropic
    _HAS_ANTHROPIC = True
except ImportError:  # pragma: no cover
    _HAS_ANTHROPIC = False

try:
    from openai import OpenAI  # used for ALL OpenAI-compatible free providers
    _HAS_OPENAI = True
except ImportError:  # pragma: no cover
    _HAS_OPENAI = False


# --- provider selection ----------------------------------------------------
def _provider() -> str:
    """Decide which brain to use, in priority order."""
    if os.environ.get("LLM_API_KEY") and os.environ.get("LLM_BASE_URL"):
        return "free" if _HAS_OPENAI else "rules"
    if _HAS_ANTHROPIC and os.environ.get("ANTHROPIC_API_KEY"):
        return "anthropic"
    return "rules"


def llm_available() -> bool:
    return _provider() != "rules"


def brain_label() -> str:
    p = _provider()
    if p == "free":
        return "free LLM (%s @ %s)" % (
            os.environ.get("LLM_MODEL", "default"),
            os.environ.get("LLM_BASE_URL", ""))
    if p == "anthropic":
        return "claude:%s" % config.MODEL
    return "rule-based fallback"


# --- structured-output schema (Anthropic path) -----------------------------
CLASSIFY_SCHEMA = {
    "type": "object",
    "properties": {
        "status": {"type": "string", "enum": config.ALL_STATUSES},
        "severity": {"type": "string", "enum": ["low", "medium", "high"]},
        "sentiment": {"type": "string", "enum": ["positive", "neutral", "negative"]},
        "confidence": {"type": "number"},
        "summary": {"type": "string"},
        "pending_actions": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["status", "severity", "sentiment", "confidence", "summary", "pending_actions"],
    "additionalProperties": False,
}

_CLASSIFY_SYSTEM = (
    "You are an operations analyst for Eko, a Distribution-as-a-Service platform "
    "whose partners are micro-entrepreneurs (kirana stores, mobile shops, CSC centres) "
    "running banking and payment services. You triage partner follow-ups.\n\n"
    "Classify the partner's current state:\n"
    "- status: ON_TRACK (active, no concern), PENDING (waiting on partner or us, "
    "low risk), DELAYED (something overdue, needs a nudge), HIGH_RISK (churn, money/"
    "settlement problem, angry partner, or hardware down).\n"
    "- severity: low | medium | high (business impact).\n"
    "- sentiment: positive | neutral | negative (the partner's apparent mood).\n"
    "- confidence: 0.0-1.0 — how sure you are given the limited notes. Be honest; "
    "low confidence is a valid and useful signal.\n"
    "- summary: one crisp sentence an ops lead can read.\n"
    "- pending_actions: concrete next steps (what WE owe the partner).\n"
)

_REMINDER_SYSTEM = (
    "You write short, warm, professional follow-up messages (WhatsApp style) from "
    "Eko's partner-success team to micro-entrepreneur partners. Keep it under 60 words, "
    "friendly and specific to their situation, in simple English with light Hinglish if "
    "natural. No emojis overload (at most one). End with a clear, low-friction ask."
)


def _partner_prompt(partner: Partner, days_since_contact: int) -> str:
    return (
        "Partner record:\n"
        "  name: %s (owner: %s)\n"
        "  region: %s | segment: %s\n"
        "  monthly_volume_inr: %s\n"
        "  days_since_last_contact: %d\n"
        "  follow-ups already sent: %d\n"
        "  awaiting partner response: %s\n"
        "  open_issue: %s\n"
        "  notes: %s\n"
        % (
            partner.name, partner.owner, partner.region, partner.segment,
            partner.monthly_volume_inr, days_since_contact, partner.followups_sent,
            partner.awaiting_response, partner.open_issue or "none", partner.notes,
        )
    )


# --- public API ------------------------------------------------------------
def classify(partner: Partner, days_since_contact: int) -> Classification:
    """Return a Classification using the active brain, falling back to rules."""
    provider = _provider()
    try:
        if provider == "free":
            return _classify_openai(partner, days_since_contact)
        if provider == "anthropic":
            return _classify_anthropic(partner, days_since_contact)
    except Exception as exc:  # noqa: BLE001 — never crash the run
        print("  [llm] classify failed (%s), using rules: %s"
              % (provider, exc))
    return _classify_rules(partner, days_since_contact)


def draft_reminder(partner: Partner, cls: Classification) -> Tuple[str, str]:
    """Return (message_text, source). Falls back to a template."""
    provider = _provider()
    prompt = (
        "Write a follow-up message to %s (owner %s, %s). "
        "Their situation: %s Pending from our side: %s"
        % (partner.name, partner.owner, partner.region, cls.summary,
           "; ".join(cls.pending_actions) or "general check-in")
    )
    try:
        if provider == "free":
            text = _chat_openai(_REMINDER_SYSTEM, prompt, max_tokens=300)
            if text:
                return text.strip(), "free-llm"
        elif provider == "anthropic":
            client = anthropic.Anthropic()
            resp = client.messages.create(
                model=config.MODEL, max_tokens=300,
                system=_REMINDER_SYSTEM,
                messages=[{"role": "user", "content": prompt}])
            text = "".join(b.text for b in resp.content if b.type == "text").strip()
            if text:
                return text, "claude"
    except Exception as exc:  # noqa: BLE001
        print("  [llm] reminder draft failed (%s), using template: %s"
              % (provider, exc))

    ask = partner.open_issue or "Let us know if you need any help."
    text = (
        "Namaste %s ji, this is Eko Partner Success. Just checking in on %s. "
        "%s Reply here and we'll sort it out quickly. Thank you for being our partner!"
        % (partner.owner.split()[0], partner.name, ask)
    )
    return text, "template"


# --- Anthropic / Claude path ----------------------------------------------
def _classify_anthropic(partner: Partner, days: int) -> Classification:
    client = anthropic.Anthropic()
    resp = client.messages.create(
        model=config.MODEL, max_tokens=700,
        system=_CLASSIFY_SYSTEM,
        messages=[{"role": "user", "content": _partner_prompt(partner, days)}],
        output_config={"format": {"type": "json_schema", "schema": CLASSIFY_SCHEMA}},
    )
    text = next(b.text for b in resp.content if b.type == "text")
    return _classification_from_json(json.loads(text), source="claude")


# --- Free / OpenAI-compatible path (Groq, Gemini, OpenRouter, ...) ---------
def _openai_client() -> "OpenAI":
    return OpenAI(api_key=os.environ["LLM_API_KEY"],
                  base_url=os.environ["LLM_BASE_URL"])


def _chat_openai(system: str, user: str, max_tokens: int,
                 force_json: bool = False) -> str:
    client = _openai_client()
    model = os.environ.get("LLM_MODEL", "llama-3.3-70b-versatile")
    kwargs = {
        "model": model,
        "max_tokens": max_tokens,
        "messages": [{"role": "system", "content": system},
                     {"role": "user", "content": user}],
    }
    if force_json:
        # Most free providers support this; if not, we retry without it below.
        kwargs["response_format"] = {"type": "json_object"}
    try:
        resp = client.chat.completions.create(**kwargs)
    except Exception:  # noqa: BLE001 — provider may reject response_format
        if force_json:
            kwargs.pop("response_format", None)
            resp = client.chat.completions.create(**kwargs)
        else:
            raise
    return resp.choices[0].message.content or ""


def _classify_openai(partner: Partner, days: int) -> Classification:
    instruction = (
        _CLASSIFY_SYSTEM
        + "\nRespond with ONLY a JSON object with exactly these keys: "
        "status, severity, sentiment, confidence (number 0-1), summary, "
        "pending_actions (array of strings). No prose, no markdown fences."
    )
    text = _chat_openai(instruction, _partner_prompt(partner, days),
                        max_tokens=700, force_json=True)
    data = _extract_json(text)
    return _classification_from_json(data, source="free-llm")


# --- shared helpers --------------------------------------------------------
def _extract_json(text: str) -> dict:
    """Tolerantly pull a JSON object out of a model response."""
    text = text.strip()
    text = re.sub(r"^```(?:json)?", "", text).strip()
    text = re.sub(r"```$", "", text).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if not match:
            raise
        return json.loads(match.group(0))


def _classification_from_json(data: dict, source: str) -> Classification:
    status = str(data.get("status", config.STATUS_PENDING)).upper()
    if status not in config.ALL_STATUSES:
        status = config.STATUS_PENDING
    return Classification(
        status=status,
        severity=str(data.get("severity", "medium")).lower(),
        sentiment=str(data.get("sentiment", "neutral")).lower(),
        confidence=float(data.get("confidence", 0.5)),
        summary=str(data.get("summary", "")).strip(),
        pending_actions=list(data.get("pending_actions", [])),
        source=source,
    )


# --- Rule-based fallback (no LLM needed) -----------------------------------
def _classify_rules(partner: Partner, days_since_contact: int) -> Classification:
    issue = (partner.open_issue or "").lower()
    notes = partner.notes.lower()
    high_risk_words = ("settlement", "paisa", "nahi aaya", "upset", "churn",
                       "competitor", "error", "down", "switched", "stopped")
    negative = any(w in (issue + " " + notes) for w in
                   ("upset", "nahi aaya", "wait", "error", "stopped", "switched"))

    pending = []
    if partner.open_issue:
        pending.append("Resolve: %s" % partner.open_issue)
    if partner.awaiting_response:
        pending.append("Follow up — awaiting partner response")

    if any(w in (issue + " " + notes) for w in high_risk_words):
        status, severity = config.STATUS_HIGH_RISK, "high"
    elif partner.followups_sent >= config.MAX_FOLLOWUPS_BEFORE_ESCALATION:
        status, severity = config.STATUS_DELAYED, "high"
    elif days_since_contact >= config.ESCALATE_AFTER_DAYS:
        status, severity = config.STATUS_DELAYED, "medium"
    elif partner.open_issue or partner.awaiting_response:
        status, severity = config.STATUS_PENDING, "medium"
    else:
        status, severity = config.STATUS_ON_TRACK, "low"

    sentiment = "negative" if negative else (
        "positive" if status == config.STATUS_ON_TRACK else "neutral")

    detail = partner.open_issue or ("active, no open issues"
                                    if status == config.STATUS_ON_TRACK
                                    else "needs a follow-up")
    summary = "%s: %s" % (partner.name, detail.rstrip("."))
    confidence = 0.6 if status != config.STATUS_HIGH_RISK else 0.7
    return Classification(
        status=status, severity=severity, sentiment=sentiment,
        confidence=confidence, summary=summary, pending_actions=pending,
        source="rules",
    )
