import os
import sys
import streamlit as st
from datetime import datetime

os.environ.setdefault("PYTHONIOENCODING", "utf-8")

from scenarios import load_dataset, pick_scenario, build_persona
from chatbot_client import MockChatbotClient, HttpChatbotClient
from agent import run_scenario_steps
from config import ANTHROPIC_API_KEY, CHATBOT_ENDPOINT

st.set_page_config(
    page_title="AcquaLombardia — Chatbot Evaluator",
    page_icon="💧",
    layout="wide",
)

st.title("💧 AcquaLombardia — Chatbot Evaluator")
st.caption("Simula clienti reali e valuta qualità e timing del chatbot")

# ── Dataset (cached) ──────────────────────────────────────────────────────────

@st.cache_data(show_spinner="Caricamento dataset scenari...")
def get_dataset():
    return load_dataset()

dataset = get_dataset()
categories = sorted({s.get("category_label", "") for s in dataset if s.get("category_label")})

# ── Sidebar ───────────────────────────────────────────────────────────────────

with st.sidebar:
    st.header("⚙️ Impostazioni")

    use_mock = st.toggle("Mock chatbot", value=True,
                         help="Usa il chatbot simulato invece dell'endpoint reale")

    if not use_mock:
        custom_endpoint = st.text_input("Chatbot endpoint", value=CHATBOT_ENDPOINT)
    else:
        custom_endpoint = CHATBOT_ENDPOINT

    has_api_key = bool(ANTHROPIC_API_KEY)
    use_no_llm = st.toggle(
        "Modalità scripted (no API key)",
        value=not has_api_key,
        disabled=not has_api_key,
        help="Cliente con risposte predefinite — non richiede ANTHROPIC_API_KEY",
    )
    if not has_api_key:
        st.caption("⚠️ ANTHROPIC_API_KEY non trovata — modalità scripted attiva.")

    st.divider()

    selected_category = st.selectbox("Categoria", ["(casuale)"] + categories)
    n_runs = st.slider("Scenari da valutare", 1, 10, 1)

    st.divider()
    st.caption(f"Dataset: **{len(dataset):,}** scenari  |  Categorie: **{len(categories)}**")

# ── Session state ─────────────────────────────────────────────────────────────

if "history" not in st.session_state:
    st.session_state.history = []

# ── Controls ──────────────────────────────────────────────────────────────────

col_run, col_clear, _ = st.columns([1, 1, 6])
run_clicked = col_run.button("▶ Avvia", type="primary", use_container_width=True)
if col_clear.button("🗑 Reset", use_container_width=True):
    st.session_state.history = []
    st.rerun()

# ── Evaluation runs ───────────────────────────────────────────────────────────

if run_clicked:
    chatbot = MockChatbotClient() if use_mock else HttpChatbotClient(custom_endpoint)
    cat_filter = None if selected_category == "(casuale)" else selected_category

    for run_idx in range(n_runs):
        scenario = pick_scenario(dataset, category=cat_filter)
        persona = build_persona(scenario)

        label = (
            f"**{persona['complaint_id']}** · {persona['category']} "
            f"| {persona['name']} ({persona['customer_id']})"
        )
        with st.expander(label, expanded=True):
            chat_area = st.container()
            score_slot = st.empty()

            for step in run_scenario_steps(persona, chatbot, no_llm=use_no_llm):

                if step["type"] == "customer":
                    with chat_area:
                        with st.chat_message("user", avatar="🧑"):
                            st.write(step["text"])

                elif step["type"] == "bot":
                    with chat_area:
                        with st.chat_message("assistant", avatar="🤖"):
                            st.write(step["text"])
                            st.caption(f"⏱ {step['latency']:.1f}s")

                elif step["type"] == "scores":
                    scores = step["scores"]
                    q = scores["quality_score"]
                    t = scores["timing_score"]

                    with score_slot.container():
                        st.divider()
                        c1, c2, c3, c4 = st.columns(4)
                        c1.metric("Qualità", f"{q}/5", f"{'★'*q}{'☆'*(5-q)}")
                        c2.metric("Timing", f"{t}/5", f"{'★'*t}{'☆'*(5-t)}")
                        c3.metric("Latenza media", f"{scores['avg_latency_s']:.2f}s")
                        c4.metric("Turni", len(step["conversation"]))
                        if scores.get("quality_reasoning"):
                            st.info(scores["quality_reasoning"])

                    st.session_state.history.append({
                        "Ora": datetime.now().strftime("%H:%M:%S"),
                        "Scenario": persona["complaint_id"],
                        "Categoria": persona["category"],
                        "Cliente": persona["name"],
                        "Qualità": q,
                        "Timing": t,
                        "Latenza (s)": scores["avg_latency_s"],
                        "Turni": len(step["conversation"]),
                    })

# ── History ───────────────────────────────────────────────────────────────────

if st.session_state.history:
    import pandas as pd

    st.divider()
    st.subheader("📊 Riepilogo sessione")

    df = pd.DataFrame(st.session_state.history)
    avg_q = df["Qualità"].mean()
    avg_t = df["Timing"].mean()

    m1, m2, m3 = st.columns(3)
    m1.metric("Qualità media", f"{avg_q:.2f}/5", f"{'★'*round(avg_q)}{'☆'*(5-round(avg_q))}")
    m2.metric("Timing medio",  f"{avg_t:.2f}/5", f"{'★'*round(avg_t)}{'☆'*(5-round(avg_t))}")
    m3.metric("Scenari totali", len(df))

    st.dataframe(
        df,
        use_container_width=True,
        hide_index=True,
        column_config={
            "Qualità": st.column_config.ProgressColumn("Qualità", min_value=1, max_value=5, format="%d ★"),
            "Timing":  st.column_config.ProgressColumn("Timing",  min_value=1, max_value=5, format="%d ★"),
        },
    )
