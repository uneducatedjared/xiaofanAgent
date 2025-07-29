import sqlparse
import re
import logging
from typing import List, Set, Tuple, Optional, Dict

from ..config import SQLConfig

logger = logging.getLogger(__name__)

class SQLParser:
    """
    SQL解析器 - 使用sqlparse库提供更精确的SQL解析功能
    """
    
    @staticmethod
    def parse_query(sql_query: str) -> Dict:
        """
        解析SQL查询，返回解析结果
        
        Args:
            sql_query: SQL查询语句
            
        Returns:
            Dict: 包含解析结果的字典
        """
        if not sql_query or not sql_query.strip():
            return {
                'operation_type': '',
                'tables': [],
                'has_where': False,
                'has_limit': False,
                'is_valid': False,
                'normalized_query': '',
                'category': 'UNKNOWN',
                'multi_statement': False,
                'statement_count': 0
            }
            
        try:
            # 标准化和格式化SQL
            formatted_sql = SQLParser._format_sql(sql_query)
            # 解析SQL语句 - 可能有多个语句
            parsed = sqlparse.parse(formatted_sql)
            
            # 检查是否有多个语句
            is_multi_statement = len(parsed) > 1
            statement_count = len(parsed)
            
            if not parsed:
                return {
                    'operation_type': '',
                    'tables': [],
                    'has_where': False,
                    'has_limit': False,
                    'is_valid': False,
                    'normalized_query': formatted_sql,
                    'category': 'UNKNOWN',
                    'multi_statement': False,
                    'statement_count': 0
                }
            
            # 默认分析第一个语句，但记录多语句信息
            stmt = parsed[0]
            
            # 获取操作类型
            operation_type = SQLParser._get_operation_type(stmt)
            
            # 确定操作类别
            category = SQLParser._get_operation_category(operation_type)
            
            # 提取表名 - 汇总所有语句中的表名
            tables = set()
            has_where = False
            has_limit = False
            
            for statement in parsed:
                # 将各语句涉及的表合并
                tables.update(SQLParser._extract_tables(statement))
                
                # 检查任一语句是否有WHERE子句
                if SQLParser._has_where_clause(statement):
                    has_where = True
                
                # 检查任一语句是否有LIMIT子句
                if SQLParser._has_limit_clause(statement):
                    has_limit = True
            
            # 对于多语句，获取最高风险的操作类型
            if is_multi_statement and len(parsed) > 1:
                operations = []
                categories = []
                for statement in parsed:
                    op = SQLParser._get_operation_type(statement)
                    operations.append(op)
                    categories.append(SQLParser._get_operation_category(op))
                
                # 风险优先级: DDL > DML > METADATA
                if 'DDL' in categories:
                    category = 'DDL'
                    # 在DDL操作中找出优先级最高的
                    # DROP/TRUNCATE > ALTER > CREATE
                    if 'DROP' in operations or 'TRUNCATE' in operations:
                        operation_type = 'DROP' if 'DROP' in operations else 'TRUNCATE'
                    elif 'ALTER' in operations:
                        operation_type = 'ALTER'
                    elif 'CREATE' in operations:
                        operation_type = 'CREATE'
                elif 'DML' in categories:
                    category = 'DML'
                    # 在DML操作中找出优先级最高的 
                    # DELETE > UPDATE > INSERT > SELECT
                    if 'DELETE' in operations:
                        operation_type = 'DELETE'
                    elif 'UPDATE' in operations:
                        operation_type = 'UPDATE'
                    elif 'INSERT' in operations:
                        operation_type = 'INSERT'
                    elif 'SELECT' in operations:
                        operation_type = 'SELECT'
            
            return {
                'operation_type': operation_type,
                'tables': list(tables),
                'has_where': has_where,
                'has_limit': has_limit,
                'is_valid': True,
                'normalized_query': formatted_sql,
                'category': category,
                'multi_statement': is_multi_statement,
                'statement_count': statement_count
            }
            
        except Exception as e:
            logger.error(f"SQL解析错误: {str(e)}")
            # 回退到简单的字符串解析
            result = SQLParser._fallback_parse(sql_query)
            # 添加多语句检测，简单检测分号
            result['multi_statement'] = ';' in sql_query.strip()
            result['statement_count'] = sql_query.count(';') + 1 if sql_query.strip() else 0
            return result
    
    @staticmethod
    def _format_sql(sql_query: str) -> str:
        """标准化SQL查询格式"""
        # 去除多余空白和注释
        return sqlparse.format(
            sql_query,
            strip_comments=True,
            reindent=True, 
            keyword_case='upper'
        )
    
    @staticmethod
    def _get_operation_type(stmt: sqlparse.sql.Statement) -> str:
        """获取SQL操作类型"""
        # 获取第一个token
        if stmt.tokens and stmt.tokens[0].ttype is sqlparse.tokens.DML:
            return stmt.tokens[0].value.upper()
        elif stmt.tokens and stmt.tokens[0].ttype is sqlparse.tokens.DDL:
            return stmt.tokens[0].value.upper()
        elif stmt.tokens and stmt.tokens[0].ttype is sqlparse.tokens.Keyword:
            return stmt.tokens[0].value.upper()
        
        # 如果无法确定，返回空字符串
        return ""
    
    @staticmethod
    def _get_operation_category(operation_type: str) -> str:
        """确定操作类别（DDL、DML或元数据）"""
        if operation_type in SQLConfig.DDL_OPERATIONS:
            return 'DDL'
        elif operation_type in SQLConfig.DML_OPERATIONS:
            return 'DML'
        elif operation_type in SQLConfig.METADATA_OPERATIONS:
            return 'METADATA'
        else:
            return 'UNKNOWN'
    
    @staticmethod
    def _extract_tables(stmt: sqlparse.sql.Statement) -> List[str]:
        """从SQL语句中提取所有表名"""
        tables = []
        
        # 根据操作类型处理表名提取
        operation_type = SQLParser._get_operation_type(stmt)
        
        # 递归函数用于深入处理复杂的SQL结构
        def extract_from_token_list(token_list):
            local_tables = []
            in_from_clause = False
            in_join_clause = False
            
            for token in token_list.tokens:
                # 检测FROM子句
                if token.ttype is sqlparse.tokens.Keyword and token.value.upper() == 'FROM':
                    in_from_clause = True
                    continue
                
                # 检测JOIN子句
                if token.ttype is sqlparse.tokens.Keyword and 'JOIN' in token.value.upper():
                    in_join_clause = True
                    continue
                
                # 在FROM或JOIN子句后提取表名
                if in_from_clause or in_join_clause:
                    if isinstance(token, sqlparse.sql.Identifier):
                        # 直接引用的表名
                        if token.get_real_name():
                            local_tables.append(token.get_real_name())
                    elif isinstance(token, sqlparse.sql.IdentifierList):
                        # 多个表，如FROM table1, table2
                        for identifier in token.get_identifiers():
                            if identifier.get_real_name():
                                local_tables.append(identifier.get_real_name())
                    elif isinstance(token, sqlparse.sql.Function):
                        # 处理子查询中的函数，可能包含表
                        local_tables.extend(extract_from_token_list(token))
                    elif isinstance(token, sqlparse.sql.Parenthesis):
                        # 可能是子查询
                        if token.tokens and isinstance(token.tokens[1], sqlparse.sql.Statement):
                            # 是子查询，递归解析
                            local_tables.extend(SQLParser._extract_tables(token.tokens[1]))
                        else:
                            # 其他括号结构，递归处理
                            local_tables.extend(extract_from_token_list(token))
                    
                    # 重置标志以避免收集其他部分的标识符
                    if token.ttype in (sqlparse.tokens.Keyword, sqlparse.tokens.Punctuation):
                        in_from_clause = False
                        in_join_clause = False
                
                # 递归处理其他TokenList
                if isinstance(token, sqlparse.sql.TokenList) and not isinstance(token, sqlparse.sql.Identifier):
                    local_tables.extend(extract_from_token_list(token))
            
            return local_tables
        
        # 特殊处理DML语句
        if operation_type == 'UPDATE':
            # UPDATE语句通常在第一个标识符中包含表名
            for i, token in enumerate(stmt.tokens):
                if token.ttype is sqlparse.tokens.DML and token.value.upper() == 'UPDATE':
                    if i+1 < len(stmt.tokens):
                        if isinstance(stmt.tokens[i+1], sqlparse.sql.Identifier):
                            tables.append(stmt.tokens[i+1].get_real_name())
                        elif isinstance(stmt.tokens[i+1], sqlparse.sql.IdentifierList):
                            # 多表更新
                            for identifier in stmt.tokens[i+1].get_identifiers():
                                if identifier.get_real_name():
                                    tables.append(identifier.get_real_name())
                    break
        elif operation_type == 'INSERT':
            # INSERT语句
            into_found = False
            for i, token in enumerate(stmt.tokens):
                if token.ttype is sqlparse.tokens.Keyword and token.value.upper() == 'INTO':
                    into_found = True
                elif into_found and isinstance(token, sqlparse.sql.Identifier):
                    tables.append(token.get_real_name())
                    break
                elif into_found and isinstance(token, sqlparse.sql.Function):
                    # 处理INSERT INTO table(...)
                    if token.get_name():
                        tables.append(token.get_name())
                    break
        elif operation_type == 'DELETE':
            # DELETE FROM table
            from_found = False
            for i, token in enumerate(stmt.tokens):
                if token.ttype is sqlparse.tokens.Keyword and token.value.upper() == 'FROM':
                    from_found = True
                elif from_found and isinstance(token, sqlparse.sql.Identifier):
                    tables.append(token.get_real_name())
                    break
                elif from_found and isinstance(token, sqlparse.sql.IdentifierList):
                    for identifier in token.get_identifiers():
                        if identifier.get_real_name():
                            tables.append(identifier.get_real_name())
                    break
        elif operation_type in {'CREATE', 'ALTER', 'DROP', 'TRUNCATE'}:
            # DDL语句
            table_found = False
            for i, token in enumerate(stmt.tokens):
                if token.ttype is sqlparse.tokens.Keyword and token.value.upper() == 'TABLE':
                    table_found = True
                elif table_found and isinstance(token, sqlparse.sql.Identifier):
                    tables.append(token.get_real_name())
                    break
        else:
            # 对于其他语句，通过递归处理提取表名
            tables.extend(extract_from_token_list(stmt))
        
        # 移除可能的重复项
        return list(set([table for table in tables if table]))
    
    @staticmethod
    def _has_where_clause(stmt: sqlparse.sql.Statement) -> bool:
        """检查SQL语句是否包含WHERE子句"""
        for token in stmt.tokens:
            if isinstance(token, sqlparse.sql.Where):
                return True
        return False
    
    @staticmethod
    def _has_limit_clause(stmt: sqlparse.sql.Statement) -> bool:
        """检查SQL语句是否包含LIMIT子句"""
        # LIMIT通常作为一个关键字出现
        for token in stmt.tokens:
            if token.ttype is sqlparse.tokens.Keyword and token.value.upper() == 'LIMIT':
                return True
            # 处理更复杂的语句结构
            elif isinstance(token, sqlparse.sql.TokenList):
                for subtoken in token.tokens:
                    if subtoken.ttype is sqlparse.tokens.Keyword and subtoken.value.upper() == 'LIMIT':
                        return True
        return False
    
    @staticmethod
    def _fallback_parse(sql_query: str) -> Dict:
        """当高级解析失败时，回退到基本字符串解析"""
        sql_upper = sql_query.strip().upper()
        parts = sql_upper.split()
        
        operation_type = parts[0] if parts else ""
        
        # 确定操作类别
        category = 'UNKNOWN'
        if operation_type in SQLConfig.DDL_OPERATIONS:
            category = 'DDL'
        elif operation_type in SQLConfig.DML_OPERATIONS:
            category = 'DML'
        elif operation_type in SQLConfig.METADATA_OPERATIONS:
            category = 'METADATA'
        
        # 基本的表名提取
        tables = []
        for i, word in enumerate(parts):
            if word in {'FROM', 'JOIN', 'UPDATE', 'INTO', 'TABLE'}:
                if i + 1 < len(parts):
                    table = parts[i + 1].strip('`;')
                    if table not in {'SELECT', 'WHERE', 'SET'}:
                        tables.append(table)
        
        # 简单检查WHERE子句
        has_where = 'WHERE' in sql_upper
        
        # 简单检查LIMIT子句
        has_limit = 'LIMIT' in sql_upper
        
        return {
            'operation_type': operation_type,
            'tables': list(set(tables)),
            'has_where': has_where,
            'has_limit': has_limit,
            'is_valid': bool(operation_type),
            'normalized_query': sql_query,
            'category': category
        } 