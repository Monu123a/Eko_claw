"""Streamlit web UI for the Partner Follow-up Claw.

Run it with:
    streamlit run app.py

It wraps the same agent (src/agent.py) — the browser is just a friendlier way
to drive it and read the results. You choose the brain in the sidebar; any key
you paste is held in memory for the run only and is never written to disk.
"""

import json
import os
import tempfile
from datetime import date

import streamlit as st

from src import config, llm
from src.agent import FollowUpClaw

# --- presets for free, OpenAI-compatible providers -------------------------
PROVIDERS = {
    "Groq (free)": {
        "base_url": "https://api.groq.com/openai/v1",
        "model": "llama-3.3-70b-versatile",
        "help": "Free key (no card) at https://console.groq.com",
    },
    "Google Gemini (free)": {
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai/",
        "model": "gemini-2.0-flash",
        "help": "Free key (no card) at https://aistudio.google.com/app/apikey",
    },
}

ACTION_STYLE = {
    config.ACTION_ESCALATE: ("🔴", "Escalate"),
    config.ACTION_REMIND: ("🟡", "Send reminder"),
    config.ACTION_NONE: ("🟢", "No action"),
}


st.set_page_config(page_title="Partner Follow-up Claw", page_icon="🐾", layout="wide")


# --- helpers ---------------------------------------------------------------
def _clear_brain_env():
    for key in ("LLM_API_KEY", "LLM_BASE_URL", "LLM_MODEL",
                "ANTHROPIC_API_KEY", "ANTHROPIC_MODEL"):
        os.environ.pop(key, None)


def _apply_brain_env(brain, free_choice, api_key, model):
    """Set env vars so llm._provider() picks the chosen brain. In-memory only."""
    _clear_brain_env()
    if brain == "Free LLM" and api_key:
        os.environ["LLM_API_KEY"] = api_key
        os.environ["LLM_BASE_URL"] = PROVIDERS[free_choice]["base_url"]
        os.environ["LLM_MODEL"] = model
    elif brain == "Anthropic / Claude (paid)" and api_key:
        os.environ["ANTHROPIC_API_KEY"] = api_key
        os.environ["ANTHROPIC_MODEL"] = model
    # "Rule-based (free, offline)" -> leave everything cleared.


# --- sidebar: configuration ------------------------------------------------
st.sidebar.title("⚙️ Configuration")

brain = st.sidebar.radio(
    "Brain",
    ["Rule-based (free, offline)", "Free LLM", "Anthropic / Claude (paid)"],
    help="The free options never touch any paid API or your Claude subscription.",
)

free_choice, api_key, model = "Groq (free)", "", ""
if brain == "Free LLM":
    free_choice = st.sidebar.selectbox("Provider", list(PROVIDERS.keys()))
    st.sidebar.caption(PROVIDERS[free_choice]["help"])
    api_key = st.sidebar.text_input("API key", type="password",
                                    placeholder="paste your free key")
    model = st.sidebar.text_input("Model", value=PROVIDERS[free_choice]["model"])
elif brain == "Anthropic / Claude (paid)":
    st.sidebar.warning("This uses a paid Anthropic API key. Leave blank to stay free.")
    api_key = st.sidebar.text_input("ANTHROPIC_API_KEY", type="password")
    model = st.sidebar.text_input("Model", value=config.MODEL)

ref_date = st.sidebar.date_input("Reference date ('today')", value=date(2026, 6, 28))

st.sidebar.markdown("---")
uploaded = st.sidebar.file_uploader("Partner data (JSON)", type=["json"],
                                    help="Leave empty to use the sample data.")

run_clicked = st.sidebar.button("▶️  Run agent", type="primary", use_container_width=True)


# --- main ------------------------------------------------------------------
st.title("🐾 Partner Follow-up Claw")
st.caption("An autonomous agent that triages partner follow-ups, drafts reminders, "
           "and escalates high-risk or uncertain cases — for Eko's micro-entrepreneur partners.")

# Resolve the data path (sample or uploaded).
data_path = config.DEFAULT_DATA_PATH
if uploaded is not None:
    tmp = tempfile.NamedTemporaryFile("wb", suffix=".json", delete=False)
    tmp.write(uploaded.getvalue())
    tmp.close()
    data_path = tmp.name

with st.expander("👀 Preview partner data", expanded=False):
    try:
        with open(data_path, "r", encoding="utf-8") as fh:
            st.dataframe(json.load(fh), use_container_width=True)
    except Exception as exc:  # noqa: BLE001
        st.error("Could not read data: %s" % exc)


if run_clicked:
    _apply_brain_env(brain, free_choice, api_key, model)

    with st.spinner("Agent running — triage → decide → act → report ..."):
        claw = FollowUpClaw(reference_date=ref_date, verbose=False)
        report = claw.run(data_path)

    t = report["totals"]
    st.success("Done — brain used: **%s**" % report["brain"])

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Partners reviewed", t["partners_reviewed"])
    c2.metric("🟡 Reminders drafted", t["reminders_drafted"])
    c3.metric("🔴 Escalations", t["escalations_created"])
    c4.metric("🟢 No action", t["no_action"])

    # Overview table
    st.subheader("Decisions")
    rows = []
    for r in report["partners"]:
        emoji, label = ACTION_STYLE.get(r["decision"]["action"], ("", r["decision"]["action"]))
        cls = r["classification"]
        rows.append({
            "ID": r["id"],
            "Partner": r["name"],
            "Region": r["region"],
            "Status": cls["status"],
            "Severity": cls["severity"],
            "Confidence": round(cls["confidence"], 2),
            "Action": "%s %s" % (emoji, label),
        })
    st.dataframe(rows, use_container_width=True, hide_index=True)

    col_esc, col_rem = st.columns(2)

    with col_esc:
        st.subheader("🔴 Escalations (need a human)")
        escs = [r for r in report["partners"]
                if r["decision"]["action"] == config.ACTION_ESCALATE]
        if not escs:
            st.info("None.")
        for r in escs:
            cls = r["classification"]
            with st.expander("%s — %s  (%s)"
                             % (r["id"], r["name"], cls["severity"].upper())):
                st.write("**Summary:** %s" % cls["summary"])
                st.write("**Days since contact:** %d" % r["days_since_last_contact"])
                st.write("**Why escalated:**")
                for reason in r["decision"]["reasons"]:
                    st.write("- %s" % reason)
                if cls["pending_actions"]:
                    st.write("**Pending actions:**")
                    for a in cls["pending_actions"]:
                        st.write("- %s" % a)

    with col_rem:
        st.subheader("🟡 Drafted reminders")
        rems = [r for r in report["partners"]
                if r["decision"]["action"] == config.ACTION_REMIND]
        if not rems:
            st.info("None.")
        run_dir = report["_paths"]["run_dir"]
        for r in rems:
            with st.expander("%s — %s" % (r["id"], r["name"])):
                path = r["artifacts"].get("reminder")
                if path:
                    with open(os.path.join(run_dir, path), "r", encoding="utf-8") as fh:
                        st.write(fh.read())

    # Downloads
    st.subheader("⬇️ Download artifacts")
    paths = report["_paths"]
    d1, d2 = st.columns(2)
    with open(paths["report"], "r", encoding="utf-8") as fh:
        d1.download_button("run_report.json", fh.read(),
                           file_name="run_report.json", mime="application/json",
                           use_container_width=True)
    with open(paths["summary"], "r", encoding="utf-8") as fh:
        d2.download_button("summary.md", fh.read(),
                           file_name="summary.md", mime="text/markdown",
                           use_container_width=True)
    st.caption("All artifacts also saved to: `%s/`" % paths["run_dir"])
else:
    st.info("Configure the brain in the sidebar, then click **Run agent**. "
            "Default is the free, offline rule-based brain — no key needed.")
