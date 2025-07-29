from typing import TypedDict, Annotated, Sequence, Dict, Any, List, Optional
from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages

class AgentState(TypedDict):
    user_input: str  # 用户输入的数据
    intent: Optional[str]  # 用户意图，由意图识别节点提取
    product_lines: Optional[List[str]] # 限制产品线搜索范围
    product_params: Dict[str, Any]  # 产品参数，意图识别参数提取
    scenario: Optional[str]  # 场景描述，由意图识别参数提取
    product_info: List[Dict[str, Any]]  # 产品信息列表，由产品查询节点填充
    parameter_info: List[Dict[str, Any]]  # 产品参数列表
    clarification_needed: bool  # 是否需要澄清问题
    clarification_answer: str  # 用户对澄清问题的回答
    clarification_count: int  # 用户澄清了几次问题
    response: str  # 最终响应，由响应生成节点填充
    messages: Annotated[Sequence[BaseMessage], add_messages]  # 对话消息列表