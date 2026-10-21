from typing import Annotated, TypedDict
from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages
class AgentState(TypedDict):
    # return {"messages": [model_with_tools.invoke([sys_msg] +)]}
    messages: Annotated[list[BaseMessage], add_messages]
    summary: str 