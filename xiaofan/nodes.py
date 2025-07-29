from langchain_deepseek import ChatDeepSeek # Assuming this is available or you have it installed
import os
from dotenv import load_dotenv
import json
from typing import Dict, Any, List
from langgraph.prebuilt import ToolNode
from state import AgentState
from tools import get_tools_async
import re
import asyncio
from langgraph.prebuilt import create_react_agent
from langchain.schema import HumanMessage, SystemMessage
from knowledge_base import client, embedding_model, collection_name
load_dotenv()

llm = ChatDeepSeek(
    model="deepseek-chat",
    temperature=0,
    max_retries=2,
    api_key=os.getenv("DEEPSEEK_API_KEY"),
    base_url="https://api.deepseek.com/v1" # DeepSeek API base URL
)

'''
意图理解节点
1. 是根据型号查询数据库，返回对应的产品信息进行推荐，也可以提取多个产品型号进行对比
2. 是模糊查询用户给品类/应用场景 产品
'''
def intent_detection(state: AgentState) -> AgentState:
    user_input = state.get("user_input", "")
    print(state)
    # 定义提示词，引导LLM识别用户意图
    prompt = f"""
    请分析以下用户查询的意图，并以JSON格式返回结果：
    例如：
    1. query_knowledgebase: 用户查询的内容和产品/应用场景无关无关，直接返回
    {{
        "query_type": "detail_search | mumble_search | query_knowledgebase",
        "query": "{user_input}"
    }}
    2. mumble_search: 用户查询的内容涉及品类/应用场景，但没有具体的产品型号或参数。例如 “测试地暖的场景，应该选择哪些热成像仪。”
    2. detail_search: 用户查询的内容涉及具体的产品型号或参数。参数和型号主要指字母和数字的组合，比如SF-1323，这样的是产品型号。10V 6A 这样的是产品参数。只有用户的查询中有这些数据，才会被归为detail_search，如果没有这些数据，其他场景为mumble_search。
    返回JSON的条件如下
    如果用户查询的内容涉及具体产品型号或者参数，返回"detail_search"类型，如果用户查询的没有涉及具体的产品型号或者参数，返回"mumble_search"类型,。
    如果是detail_search，从以下的产品线选择一个最相关的产品线填写到json中。
    如果是mumble_search，从以下的产品线选择两个最相关的产品线填写到json中。
    产品线包括：
    1. 电动气动工具
    2. 电子焊接工具
    3. 测试仪器
    4. 电源/负载
    5. 测试仪表
    6. 实验仪器
    7. 热成像仪
    8. 手动五金工具
    9. 辅料耗材
    10. 工业控制
    11. 工业物联网
    如果找不到相关的产品线，请在clarification_needed中返回True
    请确保 'product_lines' 字段总是包含一个列表，即使只有一个产品线。

    用户查询: "{user_input}"

    返回的JSON格式如下：
    {{
        "query_type": "detail_search | mumble_search | query_knowledgebase",
        "query": "{user_input}",
        "product_lines": ["product_line1", "product_line2""]，
        "parameters": {{
            "models": ["model1", "model2"]  # 如果是detail_search，提取具体的产品型号，产品型号可选，可以为空列表
            "criteria": {{
                "parameter1": "value1",
                "parameter2": "value2" 
            }} # 如果是detail_search， 提取具体的产品参数，参数个数可选，可以为空对象
        }}
        "clarification_needed": false,  # 如果需要澄清问题，返回True
    }}
    """
    # 调用LLM获取意图分析结果
    try:
        response_content = llm.invoke(prompt).content
        # Assuming the LLM returns a JSON string that needs parsing
        json_match = re.search(r'```json\s*([\s\S]*?)\s*```', response_content)
        intent_data = json.loads(json_match.group(1))
    except json.JSONDecodeError as e:
        print(f"Error decoding JSON from LLM response: {response_content}")
        # Handle cases where LLM doesn't return valid JSON
        intent_data = {
            "query_type": None,
            "product_lines": [],
            "parameters": {"models": [], "criteria": {}},
            "clarification_needed": True,
        }
    except Exception as e:
        print(f"Error invoking LLM: {e}")
        # Handle other exceptions
        intent_data = {
            "query_type": None,
            "product_lines": [],
            "parameters": {"models": [], "criteria": {}},
            "clarification_needed": True,
        }
    state["intent"] = intent_data.get("query_type")
    state["product_lines"] = intent_data.get("product_lines", [] )
    state["product_params"] = intent_data.get("parameters", {"models": [], "criteria": {}})
    state["clarification_needed"] = intent_data.get("clarification_needed", False)
    print(state)
    return state

# 调用知识库内容查询数据
def query_knowledgebase(state: AgentState) -> AgentState:
    """
    处理通用知识查询，利用知识库文档内容回答用户问题。
    """
    user_input = state.get("user_input", "")
    print(f"Handling knowledge base query for: {user_input}")
    try:
        # 1. Embed the user's query
        query_vector = list(embedding_model.embed(["query: " + user_input]))[0]
        print(query_vector)
        # 2. Search Qdrant for relevant documents
        search_result = client.search(
            collection_name=collection_name,  # 指定要搜索的集合
            query_vector=query_vector,         # 查询向量（用户问题的向量表示）
            limit=3,                           # 返回最相似的3个结果
            append_payload=True                # 是否返回向量附带的元数据（如文本内容、来源）
        )
        # 3. Extract relevant content
        context_docs = []
        for hit in search_result:
            context_docs.append(hit.payload.get("text", ""))

        if context_docs:
            context = "\n\n".join(context_docs)
            print("Retrieved context from knowledge base:\n", context)
        else:
            context = "No relevant information found in the knowledge base"
            print(context)

        prompt =f"""
        请根据以下知识库内容回答用户的问题，如果知识库内容中没有足够的信息来回答问题，请说明你无法找到相关信息，请勿编造信息。
        用户问题：{user_input}
        知识库内容：{context}
        """
        response = llm.invoke(prompt).content
        state["response"] = response
        print(f"Generated response based on knowledge base: {response}")
    except Exception as e:
        print(f"Error querying knowledge base: {e}")
        state["response"] = "抱歉，查询知识库出现问题，请稍后再试。"
    return state


# 场景匹配产品
from langchain.schema import HumanMessage, AIMessage
from pydantic import BaseModel
class aiJson(BaseModel):
    product_info: Dict[str, Any] # 产品信息列表
    parameter_info: Dict[str, Any]   # 产品参数列表



def mumble_search(state: AgentState) -> AgentState:
    tools = asyncio.run(get_tools_async())
    agent = create_react_agent(llm, tools, response_format=aiJson)
    user_input = state.get("user_input", "")
    product_lines = state.get("product_lines", [])
    clarification_answer = state.get("clarification_answer", "")
    if(clarification_answer== ""):
        prompt = f"""
你现在是产品数据库检索助手。数据库表结构如下：
- id: int
- product_line: varchar(100)
- category: varchar(100)
- model: varchar(50)
- features: text
- application_scenarios: text
- parameters: json

请根据用户输入内容（user_input），在限定的产品线（product_lines）范围内，检索相关的产品。
检索时优先考虑 application_scenarios、features、字段的匹配度，返回最符合用户需求的产品信息。

用户输入: {user_input}
限定产品线: {', '.join(product_lines)}

请以 JSON 格式返回产品列表，每个产品包含：model、features、application_scenarios、parameters 的核心信息。
"""
    else:
        prompt = f"""
你现在是产品数据库检索助手。数据库表结构如下：
- id: int
- product_line: varchar(100)
- category: varchar(100)
- model: varchar(50)
- features: text
- application_scenarios: text
- parameters: json

请先查询出在限定的产品线（product_lines）范围内，检索所有的产品。再根据用户的输入的内容为需求特征进行联想，提取用户需求的关键参数，从筛选出来的产品列表中选择3-5个参数较为符合的产品。
用户输入: {clarification_answer}
限定产品线: {', '.join(product_lines)}

请以 JSON 格式返回产品列表，每个产品包含：model、features、application_scenarios、parameters 的核心信息。
"""
    try:
        print(clarification_answer)
        print(product_lines)
        inputs_for_agent = {"messages": [HumanMessage(content=prompt)]}
        result = asyncio.run(agent.ainvoke(inputs_for_agent))
        print(f"Type of result: {type(result)}")
        print(f"Content of result: {result}")
        state["product_info"] = result["structured_response"]

    except Exception as e:
            print(f"其他错误: {e}")
    return state

# RX-350的测温范围是多少？能否测到-40度到1500度
# 参数匹配产品
def detail_search(state: AgentState) -> AgentState:
    tools = asyncio.run(get_tools_async())
    agent = create_react_agent(llm, tools, response_format=aiJson)
    user_input = state.get("user_input", "")
    product_lines = state.get("product_lines", [])
    product_params = state.get("product_params", {"models": [], "criteria": {}})
    models = product_params.get("models", [])
    criteria = product_params.get("criteria", {})

    prompt = f"""
    你现在是产品数据库的检索助手，数据库表结构如下
    - id: int
    - product_line: varchar(100)
    - category: varchar(100)
    - model: varchar(50)
    - features: text
    - application_scenarios: text
    - parameters: json
    请根据用户输入的具体产品的型号或参数，从数据库精确检索相关产品，优先使用 'models' 中提取的产品型号和'parameter'中提取的产品参数进行精确匹配。
    
    用户查询：{user_input}
    限定产品线：{','.join(product_lines)}
    提取的产品型号{','.join(models) if models else " "}
    提取的产品参数{json.dumps(criteria, ensure_ascii=False) if criteria else " "}

    请以 JSON 格式返回产品列表，每个产品包含：model，features，parameters的和用户查询有关的信息
    如果未能找到任何产品，请返回一个空的JSON数组
    """
    try:
        inputs_for_agent = {"messages": [HumanMessage(content=prompt)]}
        print(inputs_for_agent)
        result = asyncio.run(agent.ainvoke(inputs_for_agent))
        print(f"Type of result: {type(result)}")
        print(f"Content of result: {result}")
        state["product_info"] = result["structured_response"]
        state["parameter_info"] = result["structured_response"]
        print("更新后的state是：",state)
    except Exception as e:
        print(f"Error during detail search: {e}")
    return state

# 澄清问题节点+错误处理节点，处理intent问题和数据无法搜索到的问题
def clarification(state: AgentState) -> AgentState:
    """
    处理澄清请求，获取用户的澄清回答，并更新状态。
    """
    print("小凡不是很懂您的需求，请详细描述您所遇到的场景。")
    clarification_answer = input()
    state["clarification_answer"] = clarification_answer
    state["clarification_needed"] = False
    current_count = state.get("clarification_count", 0)
    state["clarification_count"] = current_count + 1
    return state

# 结果生成节点
def response_generation(state: AgentState):
    """根据状态中的产品信息和用户意图生成最终回答"""
    intent = state.get("intent", "")
    product_info = state.get("product_info", [])
    parameter_info = state.get("parameter_info", [])
    user_input = state.get("user_input", "")

    # 构建提示词（聚焦核心信息，明确生成规则）
    if(intent == "mumble_search"):
        prompt = f"""
        请根据以下信息生成用户所需的推荐回答：
        1. 用户查询：{json.dumps(user_input, ensure_ascii=False)}
        2. 产品信息：{json.dumps(product_info.model_dump(), ensure_ascii=False)}
        3. 产品参数：{json.dumps(parameter_info, ensure_ascii=False)}

        生成要求：
        - 若没有相关产品信息，返回“抱歉，我没有找到相关产品。”
        - 若有产品信息，按以下逻辑生成：
        1. 先说明推荐结论
        2. 按产品相关性排序（优先展示更匹配用户查询的型号）
        3. 每个产品需要保留3-5个核心参数和特点，避免冗余
        4. 最后补充选择建议
        - 语言简洁，总长度控制在300字内
        """
    else:
        prompt = f"""
        请根据以下信息生成用户所需的推荐回答：
        1. 用户查询：{json.dumps(user_input, ensure_ascii=False)}
        2. 产品信息：{json.dumps(product_info.model_dump(), ensure_ascii=False)}

        生成要求：
        - 必须优先读取并使用提供的产品信息和参数，禁止忽略已有数据
        - 若有产品信息和参数，按以下逻辑生成：
        1. 明确对比用户查询与产品参数（如用户问“测温范围”，需直接引用产品的“温度测量范围”参数）
        2. 先说明结论（如“满足/不满足，因产品XX参数为XX”）
        3. 推荐相关产品（优先推荐提供的产品，若不满足可补充适配建议）
        4. 每个产品保留3-5个核心参数（需从提供的参数中选取）
        5. 最后补充1条针对性选择建议（结合用户查询场景）
        - 语言简洁，总长度控制在300字内
        """
    # 调用LLM生成回答并更新状态
    try:
        print(prompt)
        response = llm.invoke(prompt).content
        state["response"] = response
        print(response)
    except Exception as e:
        print(f"生成回答时出错：{e}")
        state["response"] = "抱歉，暂时无法生成推荐结果，请稍后重试。"
    return state