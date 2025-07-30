import streamlit as st
from graph import build_graph, initialize_qdrant_knowledge_base
import traceback

# 设置页面配置
st.set_page_config(
    page_title="小凡智能体",
    page_icon="🤖",
    layout="centered"
)

# 添加自定义CSS以增大对话框尺寸
st.markdown("""
<style>
    .main .block-container {
        max-width: 90%;  /* 增大主容器宽度 */
        padding-top: 2rem;
        padding-right: 2rem;
        padding-left: 2rem;
        padding-bottom: 2rem;
    }
    
    .stChatFloatingInputContainer {
        min-height: 80px;  /* 增大输入框高度 */
    }
    
    .stChatMessage {
        padding: 1.2rem;  /* 增大消息框内边距 */
        border-radius: 0.75rem;
    }
</style>
""", unsafe_allow_html=True)

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
    st.title("🤖 小凡智能体")
    
    # 初始化 Agent
    graph = init_agent()
    if not graph:
        st.stop()
    
    # 初始化对话历史
    if "messages" not in st.session_state:
        st.session_state.messages = []
    
    # 清空历史按钮（简化版，放在右上角）
    col1, col2 = st.columns([4, 1])
    with col2:
        if st.button("🗑️ 清空历史"):
            st.session_state.messages = []
            st.rerun()
    
    # 对话区域
    chat_container = st.container()
    with chat_container:
        for message in st.session_state.messages:
            with st.chat_message(message["role"]):
                st.write(message["content"])
    
    # 输入区域
    user_input = st.chat_input("请输入您的问题...")
    
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
                        
                        # 添加助手消息到历史
                        st.session_state.messages.append({
                            "role": "assistant", 
                            "content": response_content
                        })
                        
                    except Exception as e:
                        error_msg = f"处理请求时出错: {str(e)}"
                        st.error(error_msg)
                        st.session_state.messages.append({
                            "role": "assistant", 
                            "content": error_msg
                        })
        
        st.rerun()

if __name__ == "__main__":
    main()