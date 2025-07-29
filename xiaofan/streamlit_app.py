import streamlit as st
from graph import build_graph, initialize_qdrant_knowledge_base
import traceback

# 页面配置
st.set_page_config(
    page_title="XiaoFan AI Agent 测试",
    page_icon="🤖",
    layout="wide"
)

# 初始化
@st.cache_resource
def init_agent():
    """初始化 Agent 和知识库"""
    try:
        initialize_qdrant_knowledge_base('.')
        graph = build_graph()
        return graph
    except Exception as e:
        st.error(f"初始化失败: {str(e)}")
        return None

def main():
    st.title("🤖 XiaoFan AI Agent 测试界面")
    st.markdown("---")
    
    # 初始化 Agent
    graph = init_agent()
    if not graph:
        st.stop()
    
    # 侧边栏 - 测试配置
    with st.sidebar:
        st.header("⚙️ 测试配置")
        
        # 预设测试用例
        st.subheader("快速测试")
        test_cases = {
            "产品详细查询": "RX-350的测温范围是多少？能否测到-40度到1500度", 
            "产品推荐": "推荐适合户外场景的热成像仪", # 实际还有一个品应该做推荐
            "知识库查询": "如何对政府部门介绍公司", # 通过测试




            
            "自定义": ""
        }
        
        selected_case = st.selectbox("选择测试用例", list(test_cases.keys()))
        
        # 显示调试信息
        show_debug = st.checkbox("显示调试信息", value=True)
        
        # 清空对话历史
        if st.button("🗑️ 清空历史"):
            st.session_state.messages = []
            st.rerun()
    
    # 主界面 - 对话区域
    col1, col2 = st.columns([2, 1] if show_debug else [1, 0])
    
    with col1:
        st.subheader("💬 对话区域")
        
        # 初始化对话历史
        if "messages" not in st.session_state:
            st.session_state.messages = []
        
        # 显示对话历史
        chat_container = st.container(height=400)
        with chat_container:
            for message in st.session_state.messages:
                with st.chat_message(message["role"]):
                    st.write(message["content"])
                    if message["role"] == "assistant" and "debug_info" in message:
                        with st.expander("调试信息"):
                            st.json(message["debug_info"])
        
        # 输入区域
        user_input = st.chat_input("请输入您的问题...")
        
        # 使用预设测试用例
        if selected_case != "自定义" and test_cases[selected_case]:
            if st.button(f"🚀 测试: {selected_case}"):
                user_input = test_cases[selected_case]
        
        # 处理用户输入
        if user_input:
            # 添加用户消息到历史
            st.session_state.messages.append({"role": "user", "content": user_input})
            
            # 显示用户消息
            with chat_container:
                with st.chat_message("user"):
                    st.write(user_input)
            
            # 处理 AI 响应
            with chat_container:
                with st.chat_message("assistant"):
                    with st.spinner("AI 正在思考..."):
                        try:
                            # 调用 Agent
                            inputs = {"user_input": user_input}
                            result = graph.invoke(inputs)
                            
                            # 提取响应内容
                            response_content = result.get("response", "抱歉，我无法生成回复。")
                            
                            # 显示响应
                            st.write(response_content)
                            
                            # 准备调试信息
                            debug_info = {
                                "intent": result.get("intent", "未识别"),
                                "clarification_needed": result.get("clarification_needed", False),
                                "product_info": result.get("product_info", None),
                                "product_params": result.get("product_params", None),
                                "full_state": result
                            }
                            
                            # 添加助手消息到历史
                            assistant_message = {
                                "role": "assistant", 
                                "content": response_content,
                                "debug_info": debug_info
                            }
                            st.session_state.messages.append(assistant_message)
                            
                        except Exception as e:
                            error_msg = f"处理请求时出错: {str(e)}"
                            st.error(error_msg)
                            st.session_state.messages.append({
                                "role": "assistant", 
                                "content": error_msg,
                                "debug_info": {"error": traceback.format_exc()}
                            })
            
            st.rerun()
    
    # 调试面板
    if show_debug and col2:
        with col2:
            st.subheader("🐛 调试面板")
            
            if st.session_state.messages:
                # 显示最新的状态信息
                latest_message = st.session_state.messages[-1]
                if latest_message["role"] == "assistant" and "debug_info" in latest_message:
                    debug_info = latest_message["debug_info"]
                    
                    st.write("**最新状态:**")
                    st.json({
                        "意图": debug_info.get("intent", "未知"),
                        "需要澄清": debug_info.get("clarification_needed", False),
                        "产品信息": bool(debug_info.get("product_info")),
                        "产品参数": bool(debug_info.get("product_params"))
                    })
                    
                    # 完整状态展开
                    with st.expander("完整状态信息"):
                        st.json(debug_info.get("full_state", {}))
            else:
                st.info("开始对话以查看调试信息")
    
    # 底部信息
    st.markdown("---")
    with st.expander("ℹ️ 使用说明"):
        st.markdown("""
        ### 功能说明
        - **产品详细查询**: 查询具体产品的详细参数
        - **产品推荐**: 根据场景推荐合适的产品
        - **知识库查询**: 查询公司相关信息
        
        ### 测试方法
        1. 使用侧边栏的预设测试用例快速测试
        2. 在对话框中输入自定义问题
        3. 观察调试面板了解 Agent 的决策过程
        
        ### 调试信息
        - **意图**: Agent 识别的用户意图
        - **需要澄清**: 是否需要进一步澄清
        - **状态信息**: Agent 内部状态数据
        """)

if __name__ == "__main__":
    main()