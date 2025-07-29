"""
MySQL元数据工具基类
提供元数据查询工具的共享功能
"""

import json
import logging
from typing import Any, Dict, List, Optional, Union, Callable
import functools

from src.db.mysql_operations import get_db_connection, execute_query
from src.validators import SQLValidators, ValidationError

logger = logging.getLogger("mysql_server")

class MySQLToolError(Exception):
    """MySQL工具异常基类"""
    pass

class ParameterValidationError(MySQLToolError):
    """参数验证错误"""
    pass

class QueryExecutionError(MySQLToolError):
    """查询执行错误"""
    pass

class MetadataToolBase:
    """
    元数据查询工具基类
    提供共享功能：
    - 错误处理
    - 结果格式化
    - 参数验证
    - 异常处理
    """
    
    @staticmethod
    def validate_parameter(param_name: str, param_value: Any, validator: Callable[[Any], bool], 
                          error_message: str) -> None:
        """
        验证参数是否有效
        
        Args:
            param_name: 参数名称
            param_value: 参数值
            validator: 验证函数
            error_message: 错误消息
            
        Raises:
            ParameterValidationError: 当参数验证失败时
        """
        try:
            SQLValidators.validate_parameter(param_name, param_value, validator, "参数验证")
        except ValidationError as e:
            raise ParameterValidationError(str(e))
    
    @staticmethod
    def format_results(results: List[Dict[str, Any]], operation_type: str = "元数据查询") -> str:
        """
        格式化查询结果为JSON字符串
        
        Args:
            results: 查询结果列表
            operation_type: 操作类型描述
            
        Returns:
            格式化后的JSON字符串
        """
        try:
            # 添加元数据头部信息
            metadata_info = {
                "metadata_info": {
                    "operation_type": operation_type,
                    "result_count": len(results)
                },
                "results": results
            }
            return json.dumps(metadata_info, default=str)
        except Exception as e:
            logger.error(f"结果格式化失败: {str(e)}")
            # 如果格式化失败，尝试直接序列化结果
            return json.dumps({"error": f"结果格式化失败: {str(e)}"})
    
    @staticmethod
    def handle_query_error(func):
        """
        装饰器: 统一处理查询执行过程中的错误
        """
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            try:
                return await func(*args, **kwargs)
            except ParameterValidationError as e:
                logger.error(f"参数验证错误: {str(e)}")
                return json.dumps({
                    "error": f"参数错误: {str(e)}",
                    "error_type": "ParameterValidationError"
                })
            except QueryExecutionError as e:
                logger.error(f"查询执行错误: {str(e)}")
                return json.dumps({
                    "error": f"查询执行失败: {str(e)}",
                    "error_type": "QueryExecutionError"
                })
            except Exception as e:
                logger.error(f"未预期的错误: {str(e)}")
                return json.dumps({
                    "error": f"操作失败: {str(e)}",
                    "error_type": "UnexpectedError"
                })
        return wrapper
        
    @staticmethod
    async def execute_metadata_query(query: str, params: Optional[Dict[str, Any]] = None, 
                                    operation_type: str = "元数据查询") -> str:
        """
        执行元数据查询并返回格式化结果
        
        Args:
            query: SQL查询语句
            params: 查询参数 (可选)
            operation_type: 操作类型描述
            
        Returns:
            查询结果的JSON字符串
        """
        try:
            async with get_db_connection() as connection:
                results = await execute_query(connection, query, params)
                return MetadataToolBase.format_results(results, operation_type)
        except Exception as e:
            logger.error(f"元数据查询执行失败: {str(e)}")
            raise QueryExecutionError(str(e)) from e  # 保留原始异常链 