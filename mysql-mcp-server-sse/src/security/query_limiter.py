import logging
from typing import Tuple

from ..config import SecurityConfig, SQLConfig
from .sql_parser import SQLParser

logger = logging.getLogger(__name__)

class QueryLimiter:
    """查询安全检查器"""
    
    def __init__(self):
        # 从配置中获取启用状态
        self.enable_check = SecurityConfig.ENABLE_QUERY_CHECK

    def check_query(self, sql_query: str) -> Tuple[bool, str]:
        """
        检查SQL查询是否安全
        
        Args:
            sql_query: SQL查询语句
            
        Returns:
            Tuple[bool, str]: (是否允许执行, 错误信息)
        """
        if not self.enable_check:
            return True, ""
            
        # 使用SQLParser解析SQL
        parsed_sql = SQLParser.parse_query(sql_query)
        operation_type = parsed_sql['operation_type']
        
        # 检查是否为无 WHERE 子句的更新/删除操作
        if operation_type in {'UPDATE', 'DELETE'} and not parsed_sql['has_where']:
            error_msg = f"{operation_type}操作必须包含WHERE子句"
            logger.warning(f"查询被限制: {error_msg}")
            return False, error_msg
            
        return True, "" 