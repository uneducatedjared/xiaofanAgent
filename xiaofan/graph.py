from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import MemorySaver
from state import AgentState
from knowledge_base import initialize_qdrant_knowledge_base
from nodes import (
    intent_detection,
    mumble_search,
    detail_search,
    clarification,
    response_generation,
    query_knowledgebase
)

def xiaofanAgent():
    graph = StateGraph(AgentState)
    graph.add_edge(START, "intent_detection")

    graph.add_node("intent_detection", intent_detection)
    graph.add_node("detail_search", detail_search)
    graph.add_node("mumble_search", mumble_search)
    graph.add_node("query_knowledgebase", query_knowledgebase)
    graph.add_node("clarification", clarification)
    graph.add_node("response_generation", response_generation)

    graph.set_entry_point("intent_detection")

    # intent_detection分支
    graph.add_conditional_edges(
    "intent_detection",
    lambda state: (
        "clarification" if state.get("clarification_needed", False)
        else "mumble_search" if state.get("intent", "") == "mumble_search"
        else "detail_search" if state.get("intent", "") == "detail_search"
        else "query_knowledgebase" if state.get("intent", "") == "query_knowledgebase"
        else "clarification" 
    )
)

    # detail_search分支
    graph.add_conditional_edges(
        "detail_search",
        lambda state: (
            "clarification" if not state.get("product_params")
            else "response_generation"
        )
    )

    # mumble_search分支
    graph.add_conditional_edges(
        "mumble_search",
        lambda state: (
            "clarification" if not state.get("product_info")
            else "response_generation"
        )
    )

    # clarification分支
    graph.add_conditional_edges(
        "clarification",
        lambda state: (
            "intent_detection" if state.get("clarification_answer")
            else "clarification"
        )
    )

    graph.add_edge("response_generation", END)

    return graph

def build_graph():
    memory = MemorySaver()
    builder = xiaofanAgent()
    # return builder.compile(checkpointer=memory)
    return builder.compile()

graph = build_graph()

# 入口参数要和AgentState字段一致
# inputs = {
#     "user_input": "RX-350的测温范围是多少？能否测到-40度到1500度"
# }

# inputs = {
#     "user_input": "推荐适合户外场景的热成像仪"
# }

# inputs = {
#     "user_input": "如何对政府部门介绍公司"
# }


# initialize_qdrant_knowledge_base('.')
# graph.invoke(inputs)