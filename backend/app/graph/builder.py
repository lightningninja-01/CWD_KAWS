"""
Graph builder — assembles the LangGraph StateGraph from the node factories,
wiring the two conditional branches:

  1. Context Retriever → (has inbound image?) → Media Interpreter → LLM Reasoning
                                              → skip ─────────────↗
  2. LLM Reasoning → (needs_human?) → Handover → END
                                    → Dispatcher → END

Compiled once at app startup and reused for every conversation turn —
compiling a LangGraph is relatively expensive and the graph shape never
changes at runtime.
"""
from langgraph.graph import END, StateGraph

from app.graph.dependencies import GraphDependencies
from app.graph.nodes.acknowledge import build_acknowledge_node
from app.graph.nodes.context_retriever import build_context_retriever_node
from app.graph.nodes.dispatcher import build_dispatcher_node
from app.graph.nodes.handover import build_handover_node
from app.graph.nodes.llm_reasoning import build_llm_reasoning_node, route_agent_action
from app.graph.nodes.media_interpreter import build_media_interpreter_node, should_interpret_media
from app.graph.nodes.tool_execution import build_tool_execution_node
from app.graph.state import ConversationState


def build_conversation_graph(deps: GraphDependencies):
    graph = StateGraph(ConversationState)

    graph.add_node("acknowledge", build_acknowledge_node(deps))
    graph.add_node("context_retriever", build_context_retriever_node(deps))
    graph.add_node("media_interpreter", build_media_interpreter_node(deps))
    graph.add_node("llm_reasoning", build_llm_reasoning_node(deps))
    graph.add_node("tool_execution", build_tool_execution_node(deps))
    graph.add_node("handover", build_handover_node(deps))
    graph.add_node("dispatcher", build_dispatcher_node(deps))

    graph.set_entry_point("acknowledge")
    graph.add_edge("acknowledge", "context_retriever")

    graph.add_conditional_edges(
        "context_retriever",
        should_interpret_media,
        {"interpret": "media_interpreter", "skip": "llm_reasoning"},
    )
    graph.add_edge("media_interpreter", "llm_reasoning")

    graph.add_conditional_edges(
        "llm_reasoning",
        route_agent_action,
        {
            "handover": "handover",
            "dispatch": "dispatcher",
            "tool_execution": "tool_execution"
        },
    )
    
    # Loop back from tool_execution to llm_reasoning
    graph.add_edge("tool_execution", "llm_reasoning")

    graph.add_edge("handover", END)
    graph.add_edge("dispatcher", END)

    return graph.compile()
