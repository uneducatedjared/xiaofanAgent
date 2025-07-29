import re
import logging
from typing import List, Set

from ..config import SQLRiskLevel, EnvironmentType, SecurityConfig, SQLConfig
from .sql_parser import SQLParser

logger = logging.getLogger(__name__)

class SQLOperationType:
    """SQL操作类型分析器"""
    
    def __init__(self):
        # 环境类型从配置读取
        self.env_type = SecurityConfig.ENV_TYPE
        
        # 操作类型集合从配置读取
        self.ddl_operations = SQLConfig.DDL_OPERATIONS
        self.dml_operations = SQLConfig.DML_OPERATIONS
        self.metadata_operations = SQLConfig.METADATA_OPERATIONS
        
        # 风险等级配置从配置读取
        self.allowed_risk_levels = SecurityConfig.ALLOWED_RISK_LEVELS
        self.blocked_patterns = SecurityConfig.BLOCKED_PATTERNS
        
        logger.info(f"SQL分析器初始化 - 环境: {self.env_type.value}")
        logger.info(f"允许的风险等级: {[level.name for level in self.allowed_risk_levels]}")

    def analyze_risk(self, sql_query: str) -> dict:
        """
        分析SQL查询的风险级别和影响范围
        
        Args:
            sql_query: SQL查询语句
            
        Returns:
            dict: 包含风险分析结果的字典
        """
        sql_query = sql_query.strip()
        
        # 处理空SQL
        if not sql_query:
            return {
                'operation': '',
                'operation_type': 'UNKNOWN',
                'is_dangerous': True,
                'affected_tables': [],
                'estimated_impact': {
                    'operation': '',
                    'estimated_rows': 0,
                    'needs_where': False,
                    'has_where': False
                },
                'risk_level': SQLRiskLevel.HIGH,
                'is_allowed': False
            }
            
        # 使用SQLParser解析SQL
        parsed_sql = SQLParser.parse_query(sql_query)
        operation = parsed_sql['operation_type']
        
        # 基本风险分析
        risk_analysis = {
            'operation': operation,
            'operation_type': parsed_sql['category'],
            'is_dangerous': self._check_dangerous_patterns(sql_query),
            'affected_tables': parsed_sql['tables'],
            'estimated_impact': self._estimate_impact(sql_query, parsed_sql)
        }
        
        # 计算风险等级
        risk_level = self._calculate_risk_level(sql_query, operation, risk_analysis['is_dangerous'], parsed_sql['has_where'])
        risk_analysis['risk_level'] = risk_level
        risk_analysis['is_allowed'] = risk_level in self.allowed_risk_levels
        
        return risk_analysis

    def _calculate_risk_level(self, sql_query: str, operation: str, is_dangerous: bool, has_where: bool) -> SQLRiskLevel:
        """
        计算操作风险等级
        
        规则：
        1. 危险操作（匹配危险模式）=> CRITICAL
        2. 生产环境非SELECT操作 => CRITICAL
        3. DDL操作：
           - CREATE/ALTER => HIGH
           - DROP/TRUNCATE => CRITICAL
        4. DML操作：
           - SELECT => LOW
           - INSERT => MEDIUM
           - UPDATE/DELETE（有WHERE）=> MEDIUM
           - UPDATE（无WHERE）=> HIGH
           - DELETE（无WHERE）=> CRITICAL
        5. 元数据操作：
           - SHOW/DESC/DESCRIBE等 => LOW
        6. 多语句SQL通常被认为是高风险的
        """
        # 解析SQL获取额外信息
        parsed_sql = SQLParser.parse_query(sql_query)
        
        # 危险操作
        if is_dangerous:
            return SQLRiskLevel.CRITICAL
        
        # 生产环境特别规则
        if self.env_type == EnvironmentType.PRODUCTION:
            # 生产环境中只允许SELECT和元数据操作
            if operation != 'SELECT' and parsed_sql['category'] != 'METADATA':
                return SQLRiskLevel.CRITICAL
            
            # 生产环境中的多语句SQL视为高风险
            if parsed_sql.get('multi_statement', False):
                return SQLRiskLevel.HIGH
            
        # 多语句SQL在任何环境中都是更高风险的
        if parsed_sql.get('multi_statement', False):
            # 至少中等风险，如果包含DDL则为高风险或严重风险
            if parsed_sql['category'] == 'DDL':
                return SQLRiskLevel.HIGH
            elif parsed_sql['category'] == 'DML' and operation not in {'SELECT'}:
                return SQLRiskLevel.HIGH
            return SQLRiskLevel.MEDIUM
            
        # 元数据操作
        if operation in self.metadata_operations:
            return SQLRiskLevel.LOW  # 元数据查询视为低风险操作
            
        # DDL操作
        if operation in self.ddl_operations:
            if operation in {'DROP', 'TRUNCATE'}:
                return SQLRiskLevel.CRITICAL
            return SQLRiskLevel.HIGH
            
        # DML操作
        if operation == 'SELECT':
            # 对于不带LIMIT的大型SELECT, 风险可能提高
            if not parsed_sql['has_limit'] and self.env_type == EnvironmentType.PRODUCTION:
                return SQLRiskLevel.MEDIUM
            return SQLRiskLevel.LOW
        elif operation == 'INSERT':
            return SQLRiskLevel.MEDIUM
        elif operation == 'UPDATE':
            return SQLRiskLevel.HIGH if not has_where else SQLRiskLevel.MEDIUM
        elif operation == 'DELETE':
            # 无WHERE条件的DELETE操作视为CRITICAL风险
            return SQLRiskLevel.CRITICAL if not has_where else SQLRiskLevel.MEDIUM
            
        # 默认情况
        return SQLRiskLevel.HIGH

    def _check_dangerous_patterns(self, sql_query: str) -> bool:
        """检查是否匹配危险操作模式"""
        sql_upper = sql_query.upper()
        
        # 解析SQL以获取更多信息
        parsed_sql = SQLParser.parse_query(sql_query)
        
        # 检查是否为多语句SQL - 大多数情况下使用多语句SQL可能是危险的
        if parsed_sql.get('multi_statement', False) and self.env_type == EnvironmentType.PRODUCTION:
            # 生产环境中的多语句SQL视为危险
            return True
        
        # 对敏感关键字的检查
        for pattern in self.blocked_patterns:
            if re.search(pattern, sql_upper, re.IGNORECASE):
                return True
                
        return False

    def _estimate_impact(self, sql_query: str, parsed_sql: dict) -> dict:
        """
        估算查询影响范围
        
        Args:
            sql_query: 原始SQL查询
            parsed_sql: 解析后的SQL信息
            
        Returns:
            dict: 包含预估影响的字典
        """
        operation = parsed_sql['operation_type']
        
        impact = {
            'operation': operation,
            'estimated_rows': 0,
            'needs_where': operation in {'UPDATE', 'DELETE'},
            'has_where': parsed_sql['has_where']
        }
        
        # 根据环境类型调整估算
        if self.env_type == EnvironmentType.PRODUCTION:
            if operation == 'SELECT':
                impact['estimated_rows'] = 100
            else:
                impact['estimated_rows'] = float('inf')  # 生产环境中非SELECT操作视为影响无限行
        else:
            if operation == 'SELECT':
                impact['estimated_rows'] = 100
            elif operation in {'UPDATE', 'DELETE'}:
                impact['estimated_rows'] = 1000 if impact['has_where'] else float('inf')
        
        return impact 