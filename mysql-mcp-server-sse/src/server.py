from mcp.server.fastmcp import FastMCP
import logging
import asyncio
from dotenv import load_dotenv
import atexit
import signal
import importlib
import pkgutil
import inspect
import threading

# 加载环境变量 - 移到最前面确保所有模块导入前环境变量已加载
load_dotenv()

# 导入自定义模块 - 确保在load_dotenv之后导入
from src.config import ServerConfig, SecurityConfig, DatabaseConfig, ConnectionPoolConfig
from src.tools.mysql_tool import register_mysql_tool
from src.tools.mysql_metadata_tool import register_metadata_tools
from src.tools.mysql_info_tool import register_info_tools
from src.tools.mysql_schema_tool import register_schema_tools

# 配置日志
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("mysql_server") # 创建一个名为mysql_server的日志管理器实例

# 记录环境变量加载情况
logger.debug("已加载环境变量")
logger.debug(f"当前允许的风险等级: {SecurityConfig.ALLOWED_RISK_LEVELS_STR}")
logger.debug(f"当前环境类型: {SecurityConfig.ENV_TYPE.value}")
logger.debug(f"是否允许敏感信息查询: {SecurityConfig.ALLOW_SENSITIVE_INFO}")

# 尝试导入MySQL连接器
try:
    import aiomysql
    logger.debug("aiomysql连接器导入成功")
    mysql_available = True
except ImportError as e:
    logger.critical(f"无法导入aiomysql连接器: {str(e)}")
    logger.critical("请确保已安装aiomysql包: pip install aiomysql")
    mysql_available = False

# 从配置获取服务器配置
host = ServerConfig.HOST
port = ServerConfig.PORT
logger.debug(f"服务器配置: host={host}, port={port}")

# 创建MCP服务器实例
logger.debug("正在创建MCP服务器实例...")
mcp = FastMCP("MySQL Query Server", "cccccccccc", host=host, port=port, debug=True, endpoint='/sse')
logger.debug("MCP服务器实例创建完成")

def auto_register_tools(mcp):
    """
    自动扫描src.tools目录下所有register_开头的函数并注册到mcp
    """
    import src.tools
    package = src.tools
    for finder, name, ispkg in pkgutil.iter_modules(package.__path__, package.__name__ + "."):
        # 如果是包跳过
        if ispkg:
            continue
        # 如果是文件继续执行
        module = importlib.import_module(name) # 等价import name 
        for func_name, func in inspect.getmembers(module, inspect.isfunction):
            if func_name.startswith("register_") and func_name.endswith("tool") or func_name.endswith("tools"):
                try:
                    func(mcp)
                    logger.info(f"自动注册工具: {name}.{func_name}")
                except Exception as e:
                    logger.error(f"自动注册工具失败: {name}.{func_name} - {e}")

# 注册MySQL基础查询工具
auto_register_tools(mcp)
logger.debug("已自动注册所有MySQL工具")

# 启动连接池定时回收任务
def _start_pool_cleanup_task():
    """启动后台线程定期回收连接池资源"""
    import time
    from src.db.mysql_operations import _cleanup_unused_pools
    def _loop():
        while True:
            try:
                _cleanup_unused_pools()
            except Exception as e:
                logger.warning(f"定时回收连接池异常: {e}")
            time.sleep(300)  # 每5分钟回收一次
    t = threading.Thread(target=_loop, daemon=True)
    t.start()

# 用于保存事件循环和初始化状态
_server_data = {
    'loop': None,
    'db_initialized': False
}

def cleanup_resources():
    """清理资源，关闭连接池"""
    if _server_data['loop'] and _server_data['db_initialized']:
        try:
            # 导入连接池关闭函数
            from src.db.mysql_operations import close_all_pools
            
            # 创建关闭任务并运行
            logger.info("正在关闭所有数据库连接池...")
            close_task = close_all_pools()
            
            # 在当前事件循环中运行
            if _server_data['loop'].is_running():
                future = asyncio.run_coroutine_threadsafe(close_task, _server_data['loop'])
                future.result(timeout=5)  # 等待最多5秒
            else:
                # 如果循环已经停止，创建新的循环运行清理任务
                temp_loop = asyncio.new_event_loop()
                temp_loop.run_until_complete(close_task)
                temp_loop.close()
                
            logger.info("数据库连接池已关闭")
        except Exception as e:
            logger.error(f"关闭数据库连接池时出错: {str(e)}")

# 注册退出处理函数
atexit.register(cleanup_resources) # 退出自动调用

# 注册信号处理
def signal_handler(sig, frame):
    """处理终止信号"""
    logger.info(f"收到信号 {sig}，正在清理资源...")
    cleanup_resources()
    # 正常退出
    exit(0)

# 注册常见的终止信号
signal.signal(signal.SIGINT, signal_handler)  # Ctrl+C
signal.signal(signal.SIGTERM, signal_handler)  # kill

async def init_database():
    """初始化数据库连接池"""
    try:
        from src.db.mysql_operations import init_db_pool, get_db_config
        
        # 获取数据库配置
        db_config = get_db_config()
        
        # 获取连接池配置
        pool_config = ConnectionPoolConfig.get_config()
        min_size = pool_config['minsize']
        max_size = pool_config['maxsize']
        
        # 记录连接池配置
        logger.info(f"连接池配置: 最小连接数={min_size}, 最大连接数={max_size}, 回收时间={pool_config['pool_recycle']}秒")
        logger.info(f"连接池功能状态: {'启用' if pool_config['enabled'] else '禁用'}")
        
        if not db_config.get('db'):
            logger.warning("未设置数据库名称，请检查环境变量MYSQL_DATABASE")
            print("警告: 未设置数据库名称，请检查环境变量MYSQL_DATABASE")
            # 初始化连接池但不要求指定数据库
            await init_db_pool(require_database=False)
        else:
            # 正常初始化连接池
            await init_db_pool()
            
        logger.info("数据库连接池初始化完成")
        _server_data['db_initialized'] = True
    except Exception as e:
        logger.error(f"数据库连接池初始化失败: {str(e)}")
        print(f"警告: 数据库连接池初始化失败: {str(e)}")

def start_server():
    """启动SSE服务器的同步包装器"""
    logger.debug("开始启动MySQL查询服务器...")
    
    print(f"开始启动MySQL查询SSE服务器...")
    print(f"服务器监听在 {host}:{port}/sse")
    
    try:
        # 检查MySQL配置是否有效并初始化连接池
        if mysql_available:
            # 使用事件循环执行异步初始化函数
            _server_data['loop'] = asyncio.get_event_loop()
            _server_data['loop'].run_until_complete(init_database())
        
        # 使用run_app函数启动服务器
        logger.debug("调用mcp.run('sse')启动服务器...")
        mcp.run('sse')
    except Exception as e:
        logger.exception(f"服务器运行时发生错误: {str(e)}")
        print(f"服务器运行时发生错误: {str(e)}")
    finally:
        # 确保资源被清理
        cleanup_resources()
    
if __name__ == "__main__":
    # 确保初始化后工具才被注册
    start_server()
