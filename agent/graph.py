# from IPython.display import display, Markdown, Image
from typing import Annotated, TypedDict
from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage, RemoveMessage
from langchain_openai import ChatOpenAI
from langgraph.graph import StateGraph, END
from langgraph.prebuilt import ToolNode
from langgraph.graph import MessagesState
from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph.message import add_messages
from datetime import date
from dotenv import load_dotenv
import sys
import os
from agent.tools import sheets as sh
from agent.tools import helpers as hlp
from agent.state import AgentState
from agent.tools.class_lookup import ClassIndex
import streamlit as st
load_dotenv()

os.environ["OPENAI_API_KEY"] = st.secrets["OPENAI_API_KEY"]

_class_index = None
try:
    SHEET_ID = st.secrets["SHEET_ID"]
except Exception:
    SHEET_ID = os.getenv("SHEET_ID")

def get_class_index(ws):
    global _class_index

    if _class_index is None:
        class_list = [row[0] for row in ws.get_all_values()[1:] if row]
        _class_index = ClassIndex(class_list)

    return _class_index                      
tools = [ sh.class_info, sh.update_progress, sh.get_next_lesson, sh.update_assignment, sh.get_progress]

model = ChatOpenAI(model="gpt-4o", api_key = st.secrets["OPENAI_API_KEY"], temperature=0)
model_with_tools = model.bind_tools(tools)

tool_node = ToolNode(tools)

def make_sys_message():
    today = date.today().isoformat()
    return SystemMessage(content=f"Today's date is {today}. You are a helpful assistant whose job is to assist with Google Sheets operations. The id of the Google Sheet is {SHEET_ID}. You have access to the following tools: get_variations_for_date, class_info, update_progress, get_next_lesson, get_schedule_for_date, read_sheet, update_assignment. Use these tools to answer questions about the sheet.The Google Sheet has the following tabs: 'classes', 'curriculum', 'progress','assignments', 'schedule' and 'variations'. The 'classes' tab has columns for 'class id', 'level', and 'teacher'. The 'curriculum' tab has columns for 'lesson_number', 'topic', 'level', 'slides_url' and 'notes'. The 'progress' tab has columns for 'class_id', 'lesson_number', 'status', 'last_slide', 'date', and 'notes'. The status column is a dropdown, with the values 'not_started', 'in_progress', 'completed', and 'skipped'. The 'assignments' tab has columns for 'class_id', 'lesson_number', 'assignment_type', 'context', 'status', 'due_date', and 'note'. The 'status' column is a dropdown with the options 'pending', 'overdue', and 'not_started'. The 'schedule' tab has columns for month, week, day, time_start, time_end, class_id, teacher, note and version. All of the data in the 'schedule' tab is from the 2025-2026 school year, starting in October 2025 and ending in May 2026. The 'variations' tab has columns for date, class_id, change_type, detail, and source_email. When I ask you a question, you should first determine if you need to use one of the tools to answer it. If you do, you should call the appropriate tool with the correct parameters. When you call update_progress and then immediately call get_next_lesson for the same class in the same response, pass the same status and last_slide values you just wrote to get_next_lesson's override_status and override_last_slide parameters, so the lesson recommendation is based on the values you just set rather than a possibly-stale read.If you don't need to use a tool, you should answer the question directly. You should always provide your reasoning for your answer. When you have answered the question you should end your response. When your answer includes a lesson, cite the lesson number as well as the lesson topic.")
                      
def call_llm(state):
    messages = [m for m in state["messages"] if not isinstance(m, RemoveMessage)]
    summary = state.get("summary", "")
    if summary:
        messages = [SystemMessage(content=summary)] + messages
    response = model_with_tools.invoke([make_sys_message()] + messages)
    return {"messages": [response]}

def should_continue(state: AgentState):
    last_message = state["messages"][-1]
    if last_message.tool_calls:
        return "tools"
    if len(state["messages"]) > 10:
        return "summarize"
    return "end"

def summarize_conversation(state: AgentState):
    from langchain_core.messages import AIMessage, ToolMessage

    summary = state.get("summary", "")
    summary_message = (
        f"Distill the above chat messages into a single summary. Prepend with 'Summary of conversation so far: '. Existing summary: {summary}"
        if summary else
        "Distill the above chat messages into a single summary. Prepend with 'Summary of conversation so far: '."
    )

    messages = state["messages"]
    response = model.invoke(messages + [HumanMessage(content=summary_message)])
    
    # Only delete messages that aren't part of a tool call/response pair
    safe_to_delete = []
    for m in messages[:-2]:
        if isinstance(m, ToolMessage):
            continue  # never delete tool results in isolation
        if isinstance(m, AIMessage) and m.tool_calls:
            continue  # never delete an AIMessage that has tool calls
        safe_to_delete.append(RemoveMessage(id=m.id))
   
    return {"summary": response.content, "messages": safe_to_delete}
workflow = StateGraph(AgentState)
workflow.add_node("agent", call_llm)
workflow.add_node("tools", tool_node)
workflow.add_node("summarize", summarize_conversation)
workflow.add_conditional_edges(
    "agent", should_continue, {"tools": "tools", "summarize": "summarize" ,"end": END}
)

workflow.add_edge("tools", "agent")

workflow.add_edge("summarize", END)

workflow.set_entry_point("agent")
memory = MemorySaver()
app = workflow.compile(checkpointer=memory)
# display(Image(app.get_graph().draw_mermaid_png()))