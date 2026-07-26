"""
Data-bot — a simple chat agent sitting on top of your procurement data.
Run:  streamlit run app.py
"""

import io

import speech_recognition as sr
import streamlit as st

from agent import run_agent

st.set_page_config(page_title="Data-bot", page_icon="🤖", layout="centered")

st.markdown(
    """
    <style>
    #MainMenu, footer, header {visibility: hidden;}
    .block-container {max-width: 760px; padding-top: 2.5rem;}
    .source-pill {
        display: inline-block; padding: 2px 10px; margin-right: 6px;
        border-radius: 12px; font-size: 0.78rem; font-weight: 600;
        background: rgba(120, 120, 120, 0.15);
    }
    </style>
    """,
    unsafe_allow_html=True,
)

st.markdown("## Data-bot")
st.caption("Ask a question by typing or by voice. Answers show exactly which query or document was used.")

if "messages" not in st.session_state:
    st.session_state.messages = []  # [{role, content, tool_calls?, sources?}]


def transcribe(audio_bytes: bytes) -> str | None:
    recognizer = sr.Recognizer()
    with sr.AudioFile(io.BytesIO(audio_bytes)) as source:
        audio = recognizer.record(source)
    try:
        return recognizer.recognize_google(audio)
    except (sr.UnknownValueError, sr.RequestError):
        return None


def ask(question: str) -> None:
    st.session_state.messages.append({"role": "user", "content": question})
    history = [{"role": m["role"], "content": m["content"]} for m in st.session_state.messages[:-1]]
    with st.spinner("Working..."):
        result = run_agent(question, history)
    st.session_state.messages.append(
        {
            "role": "assistant",
            "content": result["answer"],
            "tool_calls": result.get("tool_calls", []),
            "sources": result.get("sources", []),
        }
    )


def render_tool_call(call: dict) -> None:
    if call["tool"] == "query_database":
        st.caption("SQL query")
        st.code(call["input"].get("sql", ""), language="sql")
        st.caption("Result")
        st.code(call["result"], language="json")
    else:
        st.caption(f"Document search: \"{call['input'].get('query', '')}\"")
        st.text(call["result"])


for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])
        if msg["role"] == "assistant" and msg.get("tool_calls"):
            if msg.get("sources"):
                pills = "".join(f'<span class="source-pill">{s}</span>' for s in msg["sources"])
                st.markdown(pills, unsafe_allow_html=True)
            with st.expander(f"How this was found ({len(msg['tool_calls'])} query call(s))"):
                for i, call in enumerate(msg["tool_calls"]):
                    if i > 0:
                        st.divider()
                    render_tool_call(call)

st.markdown("**Ask by voice**")
audio = st.audio_input("Record a question", label_visibility="collapsed")
if audio is not None and audio != st.session_state.get("_last_audio"):
    st.session_state._last_audio = audio
    text = transcribe(audio.getvalue())
    if text:
        ask(text)
        st.rerun()
    else:
        st.warning("Couldn't understand that — please try again or type your question below.")

typed = st.chat_input("Type a question about vendors, contracts, POs, or invoices...")
if typed:
    ask(typed)
    st.rerun()
