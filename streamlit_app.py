"""
streamlit_app.py

Simple chat frontend for the teaching assistant agent.

Run with:
    streamlit run streamlit_app.py

Expects the same environment as the notebook: credentials.json in the
project root, OPENAI_API_KEY set, and the same Google Sheet ID.
"""

import uuid
import streamlit as st
from langchain_core.messages import HumanMessage, AIMessage

# Import your compiled graph and any setup needed.
# Adjust this import to match wherever your graph lives once it's out
# of the notebook — e.g. `from agent.graph import app`
from agent.graph import app

st.set_page_config(page_title="Teaching Assistant Agent", page_icon="📚")
st.title("📚 Teaching Assistant Agent")
st.caption("Ask about any class — progress, schedule, assignments, or what to teach next.")

# --- Session state setup ---
# Streamlit reruns the whole script on every interaction, so the thread_id
# and message history must live in session_state, not as plain variables,
# or the conversation would reset on every message.
if "thread_id" not in st.session_state:
    st.session_state.thread_id = str(uuid.uuid4())

if "messages" not in st.session_state:
    st.session_state.messages = []  # list of {"role": ..., "content": ...} for display only

config = {"configurable": {"thread_id": st.session_state.thread_id}}

# --- Render existing conversation ---
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

# --- Sidebar: new conversation button ---
with st.sidebar:
    st.markdown("### Session")
    st.caption(f"Thread: `{st.session_state.thread_id[:8]}...`")
    if st.button("Start new conversation"):
        st.session_state.thread_id = str(uuid.uuid4())
        st.session_state.messages = []
        st.rerun()

# --- Chat input ---
user_input = st.chat_input("Ask about a class, schedule, or progress...")

if user_input:
    # Show the user's message immediately
    st.session_state.messages.append({"role": "user", "content": user_input})
    with st.chat_message("user"):
        st.markdown(user_input)

    # Run the agent
    with st.chat_message("assistant"):
        with st.spinner("Thinking..."):
            final_response = None
            tool_calls_made = []

            for event in app.stream(
                {"messages": [HumanMessage(content=user_input)]},
                config=config,
                stream_mode="updates",
            ):
                # Track tool calls for an optional "what it checked" expander
                if "tools" in event:
                    for m in event["tools"]["messages"]:
                        tool_calls_made.append(m.name)
                if "agent" in event:
                    last_msg = event["agent"]["messages"][-1]
                    if isinstance(last_msg, AIMessage) and last_msg.content:
                        final_response = last_msg.content

            if tool_calls_made:
                with st.expander(f"Checked: {', '.join(tool_calls_made)}"):
                    st.caption("Tools called while answering this question.")

            response_text = final_response or "I wasn't able to find an answer to that."
            st.markdown(response_text)

    st.session_state.messages.append({"role": "assistant", "content": response_text})