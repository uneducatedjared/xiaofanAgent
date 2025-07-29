"""
MySQL元数据查询工具
提供表结构等元数据信息查询功能
"""

import json
import logging
import re
from typing import Any, Dict, List, Optional
from mcp.server.fastmcp import FastMCP

from .metadata_base_tool import MetadataToolBase, ParameterValidationError, QueryExecutionError
from src.db.mysql_operations import get_db_connection, execute_query
from src.validators import SQLValidators

logger = logging.getLogger("mysql_server")

def register_metadata_tools(mcp: FastMCP):
    """
    注册MySQL元数据查询工具到MCP服务器
    
    Args:
        mcp: FastMCP服务器实例
    """
    logger.debug("注册MySQL元数据查询工具...")
    
    @mcp.tool()
    @MetadataToolBase.handle_query_error
    async def mysql_show_tables(database: Optional[str] = None, pattern: Optional[str] = None,
                               limit: int = 100, exclude_views: bool = False) -> str:
        """
        获取数据库中的表列表，支持筛选和限制结果数量
        
        Args:
            database: 数据库名称 (可选，默认使用当前连接的数据库)
            pattern: 表名匹配模式 (可选, 例如 '%user%')
            limit: 返回结果的最大数量 (默认100，设为0表示无限制)
            exclude_views: 是否排除视图 (默认为False)
            
        Returns:
            表列表的JSON字符串
        """
        # 参数验证
        if database:
            MetadataToolBase.validate_parameter(
                "database", database, 
                SQLValidators.validate_database_name,
                "数据库名称只能包含字母、数字和下划线"
            )
            
        if pattern:
            MetadataToolBase.validate_parameter(
                "pattern", pattern,
                SQLValidators.validate_like_pattern,
                "模式只能包含字母、数字、下划线和通配符(%_)"
            )
            
        MetadataToolBase.validate_parameter(
            "limit", limit,
            lambda x: SQLValidators.validate_integer(x, min_value=0),
            "返回结果的最大数量必须是非负整数"
        )
        
        # 基础查询
        base_query = "SHOW FULL TABLES" if exclude_views else "SHOW TABLES"
        if database:
            base_query += f" FROM `{database}`"
        if pattern:
            base_query += f" LIKE '{pattern}'"
            
        logger.debug(f"执行查询: {base_query}")
        
        # 执行查询 - 使用异步上下文管理器
        async with get_db_connection() as connection:
            results = await execute_query(connection, base_query)
            
            # 如果需要排除视图，且使用的是SHOW FULL TABLES
            if exclude_views and "FULL" in base_query:
                filtered_results = []
                
                # 查找表名和表类型字段
                if results:
                    # 确定表名和表类型字段名
                    field_names = list(results[0].keys())
                    table_type_field = None
                    table_field = None
                    
                    # 查找表类型字段 - 这通常是'Table_type'，但也检查其他可能的名称
                    possible_type_fields = ['Table_type', 'table_type', 'type']
                    for field in possible_type_fields:
                        if field in field_names:
                            table_type_field = field
                            break
                    
                    # 查找表名字段 - 这可能是结果中的第一个字段
                    for field in field_names:
                        if field != table_type_field:  # 表名不会是类型字段
                            if field.lower() in ['table', 'name', 'table_name', 'tables_in_']:
                                table_field = field
                                break
                    
                    # 如果没找到明确的表名字段，使用第一个非类型字段
                    if not table_field and len(field_names) > 0:
                        for field in field_names:
                            if field != table_type_field:
                                table_field = field
                                break
                
                    # 只有当我们能确定表名和类型字段时才进行过滤
                    if table_field and table_type_field:
                        logger.debug(f"表名字段: {table_field}, 表类型字段: {table_type_field}")
                        # 只保留基表 (BASE TABLE)，排除视图和其他对象
                        for item in results:
                            if item[table_type_field] == 'BASE TABLE':
                                filtered_results.append(item)
                    else:
                        # 如果无法确定字段，保留所有结果并记录警告
                        logger.warning("无法确定表类型字段，无法排除视图")
                        filtered_results = results
                else:
                    filtered_results = []
            else:
                filtered_results = results
                
            # 限制返回数量
            if limit > 0 and len(filtered_results) > limit:
                limited_results = filtered_results[:limit]
                is_limited = True
            else:
                limited_results = filtered_results
                is_limited = False
                
            # 构造元数据
            metadata_info = {
                "metadata_info": {
                    "operation_type": "表列表查询",
                    "result_count": len(limited_results),
                    "total_count": len(results),
                    "filtered": {
                        "database": database,
                        "pattern": pattern,
                        "exclude_views": exclude_views and "FULL" in base_query,
                        "limited": is_limited
                    }
                },
                "results": limited_results
            }
            
            return json.dumps(metadata_info, default=str)
    
    @mcp.tool()
    @MetadataToolBase.handle_query_error
    async def mysql_show_columns(table: str, database: Optional[str] = None) -> str:
        """
        获取表的列信息
        
        Args:
            table: 表名
            database: 数据库名称 (可选，默认使用当前连接的数据库)
            
        Returns:
            表列信息的JSON字符串
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
            
        query = f"SHOW COLUMNS FROM `{table}`" if not database else f"SHOW COLUMNS FROM `{database}`.`{table}`"
        logger.debug(f"执行查询: {query}")
        
        return await MetadataToolBase.execute_metadata_query(query, operation_type="表列信息查询")

    @mcp.tool()
    @MetadataToolBase.handle_query_error
    async def mysql_describe_table(table: str, database: Optional[str] = None) -> str:
        """
        描述表结构
        
        Args:
            table: 表名
            database: 数据库名称 (可选，默认使用当前连接的数据库)
            
        Returns:
            表结构描述的JSON字符串
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
            
        query = f"DESCRIBE `{table}`" if not database else f"DESCRIBE `{database}`.`{table}`"
        logger.debug(f"执行查询: {query}")
        
        return await MetadataToolBase.execute_metadata_query(query, operation_type="表结构描述查询")

    @mcp.tool()
    @MetadataToolBase.handle_query_error
    async def mysql_show_create_table(table: str, database: Optional[str] = None) -> str:
        """
        获取表的创建语句
        
        Args:
            table: 表名
            database: 数据库名称 (可选，默认使用当前连接的数据库)
            
        Returns:
            表创建语句的JSON字符串
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
            
        table_ref = f"`{table}`" if not database else f"`{database}`.`{table}`"
        query = f"SHOW CREATE TABLE {table_ref}"
        logger.debug(f"执行查询: {query}")
        
        return await MetadataToolBase.execute_metadata_query(query, operation_type="表创建语句查询")