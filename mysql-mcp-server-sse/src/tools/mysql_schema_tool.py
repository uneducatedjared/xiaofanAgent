"""
MySQL表结构高级查询工具
提供索引、约束、表状态等高级元数据查询功能
"""

import json
import logging
import re
from typing import Any, Dict, List, Optional, Union
from mcp.server.fastmcp import FastMCP

from .metadata_base_tool import MetadataToolBase, ParameterValidationError, QueryExecutionError
from src.db.mysql_operations import get_db_connection, execute_query
from src.validators import SQLValidators

logger = logging.getLogger("mysql_server")

async def execute_schema_query(
    query: str, 
    params: Optional[Dict[str, Any]] = None, 
    operation_type: str = "元数据查询",
    stream_results: bool = False,
    batch_size: int = 1000
) -> str:
    """
    执行表结构查询
    
    Args:
        query: SQL查询语句
        params: 查询参数 (可选)
        operation_type: 操作类型描述
        stream_results: 是否使用流式处理获取大型结果集
        batch_size: 批处理大小，分批获取结果时的每批记录数量
        
    Returns:
        查询结果的JSON字符串
    """
    async with get_db_connection() as connection:
        results = await execute_query(
            connection, 
            query, 
            params, 
            batch_size=batch_size, 
            stream_results=stream_results
        )
        return MetadataToolBase.format_results(results, operation_type)

def register_schema_tools(mcp: FastMCP):
    """
    注册MySQL表结构高级查询工具到MCP服务器
    
    Args:
        mcp: FastMCP服务器实例
    """
    logger.debug("注册MySQL表结构高级查询工具...")
    
    @mcp.tool()
    @MetadataToolBase.handle_query_error
    async def mysql_show_indexes(table: str, database: Optional[str] = None) -> str:
        """
        获取表的索引信息
        
        Args:
            table: 表名
            database: 数据库名称 (可选，默认使用当前连接的数据库)
            
        Returns:
            表索引信息的JSON字符串
        """
        # 参数验证
        MetadataToolBase.validate_parameter(
            "table", table,
            SQLValidators.validate_table_name,
            "表名只能包含字母、数字和下划线"
        )
        
        if database:
            MetadataToolBase.validate_parameter(
                "database", database,
                SQLValidators.validate_database_name,
                "数据库名称只能包含字母、数字和下划线"
            )
        
        # 构建查询
        table_ref = f"`{table}`" if not database else f"`{database}`.`{table}`"
        query = f"SHOW INDEX FROM {table_ref}"
        logger.debug(f"执行查询: {query}")
        
        # 执行查询
        return await execute_schema_query(query, operation_type="表索引查询")
    
    @mcp.tool()
    @MetadataToolBase.handle_query_error
    async def mysql_show_table_status(database: Optional[str] = None, like_pattern: Optional[str] = None) -> str:
        """
        获取表状态信息
        
        Args:
            database: 数据库名称 (可选，默认使用当前连接的数据库)
            like_pattern: 表名匹配模式 (可选，例如 '%user%')
            
        Returns:
            表状态信息的JSON字符串
        """
        # 参数验证
        if database:
            MetadataToolBase.validate_parameter(
                "database", database,
                SQLValidators.validate_database_name,
                "数据库名称只能包含字母、数字和下划线"
            )
            
        if like_pattern:
            MetadataToolBase.validate_parameter(
                "like_pattern", like_pattern,
                SQLValidators.validate_like_pattern,
                "模式只能包含字母、数字、下划线和通配符(%_)"
            )
        
        # 构建查询
        if database:
            query = f"SHOW TABLE STATUS FROM `{database}`"
        else:
            query = "SHOW TABLE STATUS"
            
        if like_pattern:
            query += f" LIKE '{like_pattern}'"
            
        logger.debug(f"执行查询: {query}")
        
        # 执行查询
        return await execute_schema_query(query, operation_type="表状态查询")
    
    @mcp.tool()
    @MetadataToolBase.handle_query_error
    async def mysql_show_foreign_keys(table: str, database: Optional[str] = None) -> str:
        """
        获取表的外键约束信息
        
        Args:
            table: 表名
            database: 数据库名称 (可选，默认使用当前连接的数据库)
            
        Returns:
            表外键约束信息的JSON字符串
        """
        # 参数验证
        MetadataToolBase.validate_parameter(
            "table", table,
            SQLValidators.validate_table_name,
            "表名只能包含字母、数字和下划线"
        )
        
        if database:
            MetadataToolBase.validate_parameter(
                "database", database,
                SQLValidators.validate_database_name,
                "数据库名称只能包含字母、数字和下划线"
            )
        
        # 确定数据库名
        db_name = database
        if not db_name:
            # 获取当前数据库 - 使用异步上下文管理器
            async with get_db_connection() as connection:
                current_db_results = await execute_query(connection, "SELECT DATABASE() as db")
                if current_db_results and 'db' in current_db_results[0]:
                    db_name = current_db_results[0]['db']
        
        if not db_name:
            raise ValueError("无法确定数据库名称，请明确指定database参数")
        
        # 使用INFORMATION_SCHEMA查询外键 - 修改为使用命名参数
        query = """
        SELECT 
            CONSTRAINT_NAME, 
            TABLE_NAME,
            COLUMN_NAME,
            REFERENCED_TABLE_NAME,
            REFERENCED_COLUMN_NAME,
            UPDATE_RULE,
            DELETE_RULE
        FROM 
            INFORMATION_SCHEMA.KEY_COLUMN_USAGE kcu
        JOIN 
            INFORMATION_SCHEMA.REFERENTIAL_CONSTRAINTS rc
        ON 
            kcu.CONSTRAINT_NAME = rc.CONSTRAINT_NAME
        WHERE 
            kcu.TABLE_SCHEMA = %(table_schema)s 
            AND kcu.TABLE_NAME = %(table_name)s
            AND kcu.REFERENCED_TABLE_NAME IS NOT NULL
        """
        
        # 使用命名参数，键名与SQL中的占位符对应
        params = {"table_schema": db_name, "table_name": table}
        
        logger.debug(f"执行外键查询: {query}")
        logger.debug(f"参数: {params}")
        
        # 执行查询
        return await execute_schema_query(query, params, operation_type="表外键查询")
    
    @mcp.tool()
    @MetadataToolBase.handle_query_error
    async def mysql_paginate_results(query: str, page: int = 1, page_size: int = 50) -> str:
        """
        分页执行查询以处理大型结果集
        
        Args:
            query: SQL查询语句
            page: 页码 (从1开始)
            page_size: 每页记录数 (默认50)
            
        Returns:
            分页结果的JSON字符串
        """
        # 参数验证
        MetadataToolBase.validate_parameter(
            "page", page,
            lambda x: SQLValidators.validate_integer(x, min_value=1),
            "页码必须是正整数"
        )
        
        MetadataToolBase.validate_parameter(
            "page_size", page_size,
            lambda x: SQLValidators.validate_integer(x, min_value=1, max_value=1000),
            "每页记录数必须是正整数且不超过1000"
        )
        
        # 计算偏移量
        offset = (page - 1) * page_size
        
        # 分离基础查询和LIMIT/OFFSET部分
        base_query = query.strip()
        if re.search(r'\bLIMIT\b', base_query, re.IGNORECASE):
            raise ValueError("查询语句已包含LIMIT子句，不能与分页功能一起使用")
            
        # 添加LIMIT和OFFSET
        paginated_query = f"{base_query} LIMIT {page_size} OFFSET {offset}"
        
        logger.debug(f"执行分页查询: {paginated_query}")
        logger.debug(f"页码: {page}, 每页记录数: {page_size}, 偏移量: {offset}")
        
        # 执行查询 - 使用异步上下文管理器
        async with get_db_connection() as connection:
            # 首先检查并验证查询
            # 确认查询安全性 - 限制查询类型，只允许SELECT查询
            if not base_query.strip().upper().startswith('SELECT'):
                raise ValueError("只支持SELECT查询进行分页")
                
            # 使用普通查询获取当前页结果（不需要流式处理，因为已经有LIMIT限制）
            results = await execute_query(connection, paginated_query)
            
            # 尝试获取总记录数 - 对于大型结果集使用流式处理
            try:
                # 由于无法参数化子查询，我们改为构建一个只返回计数的查询
                # 这仍有SQL注入风险，但我们已经验证查询只能是SELECT
                count_query = f"SELECT COUNT(*) as total FROM ({base_query}) as subquery"
                # 计数查询通常只返回一行，不需要流式处理
                count_results = await execute_query(connection, count_query)
                total = count_results[0]['total'] if count_results else 0
                
                # 根据总记录数计算是否是大型结果集
                is_large_resultset = total > 1000
                
                # 提示用户结果集大小
                if is_large_resultset:
                    logger.info(f"检测到大型结果集，共 {total} 条记录，建议使用较小的 page_size 值")
                
            except Exception as e:
                logger.warning(f"无法执行总数查询: {str(e)}")
                total = None
                is_large_resultset = False
                
            # 构造分页元数据
            pagination_info = {
                "metadata_info": {
                    "operation_type": "分页查询",
                    "result_count": len(results),
                    "pagination": {
                        "page": page,
                        "page_size": page_size,
                        "total_records": total,
                        "total_pages": (total + page_size - 1) // page_size if total else None,
                        "has_next": (page * page_size < total) if total is not None else len(results) == page_size,
                        "has_previous": page > 1,
                        "is_large_resultset": is_large_resultset if total is not None else None
                    }
                },
                "results": results
            }
            
            return json.dumps(pagination_info, default=str) 