import re
from typing import Any, Callable, Optional

class ValidationError(Exception):
    """验证错误异常"""
    pass

class SQLValidators:
    """SQL相关验证器集合"""
    
    # 正则表达式常量
    IDENTIFIER_PATTERN = r'^[a-zA-Z0-9_]+$'
    PATTERN_PATTERN = r'^[a-zA-Z0-9_%]+$'
    
    @staticmethod
    def validate_identifier(name: str, entity_type: str = "标识符") -> bool:
        """
        验证SQL标识符是否合法安全（表名、数据库名、列名等）
        
        Args:
            name: 要验证的标识符
            entity_type: 实体类型名称，用于错误信息
            
        Returns:
            如果标识符安全返回True
            
        Raises:
            ValidationError: 当标识符包含不安全字符时
        """
        if not name:
            raise ValidationError(f"{entity_type}不能为空")
            
        if not re.match(SQLValidators.IDENTIFIER_PATTERN, name):
            raise ValidationError(f"无效的{entity_type}: {name}, {entity_type}只能包含字母、数字和下划线")
        return True
    
    @staticmethod
    def validate_table_name(name: str) -> bool:
        """验证表名是否合法安全"""
        return SQLValidators.validate_identifier(name, "表名")
    
    @staticmethod
    def validate_database_name(name: str) -> bool:
        """验证数据库名是否合法安全"""
        return SQLValidators.validate_identifier(name, "数据库名")
    
    @staticmethod
    def validate_column_name(name: str) -> bool:
        """验证列名是否合法安全"""
        return SQLValidators.validate_identifier(name, "列名")
    
    @staticmethod
    def validate_like_pattern(pattern: str) -> bool:
        """
        验证LIKE查询模式是否安全
        
        Args:
            pattern: 要验证的模式字符串
            
        Returns:
            如果模式安全返回True
            
        Raises:
            ValidationError: 当模式包含不安全字符时
        """
        if not pattern:
            raise ValidationError("模式不能为空")
            
        if not re.match(SQLValidators.PATTERN_PATTERN, pattern):
            raise ValidationError(f"无效的模式: {pattern}, 模式只能包含字母、数字、下划线和通配符(%_)")
        return True
    
    @staticmethod
    def validate_integer(value: int, min_value: Optional[int] = None, max_value: Optional[int] = None) -> bool:
        """
        验证整数值是否在允许范围内
        
        Args:
            value: 要验证的整数值
            min_value: 最小允许值（可选）
            max_value: 最大允许值（可选）
            
        Returns:
            如果值合法返回True
            
        Raises:
            ValidationError: 当值不合法时
        """
        if not isinstance(value, int):
            raise ValidationError(f"值必须是整数，当前类型: {type(value).__name__}")
            
        if min_value is not None and value < min_value:
            raise ValidationError(f"值必须大于或等于 {min_value}")
            
        if max_value is not None and value > max_value:
            raise ValidationError(f"值必须小于或等于 {max_value}")
            
        return True
    
    @staticmethod
    def validate_parameter(param_name: str, param_value: Any, validator: Callable, error_prefix: str = "") -> bool:
        """
        通用参数验证函数
        
        Args:
            param_name: 参数名称
            param_value: 参数值
            validator: 验证函数
            error_prefix: 错误信息前缀
            
        Returns:
            如果验证通过返回True
            
        Raises:
            ValidationError: 当验证失败时
        """
        if param_value is None:
            return True  # 允许None值
            
        try:
            return validator(param_value)
        except ValidationError as e:
            prefix = f"{error_prefix}: " if error_prefix else ""
            raise ValidationError(f"{prefix}{param_name} - {str(e)}")
        except Exception as e:
            prefix = f"{error_prefix}: " if error_prefix else ""
            raise ValidationError(f"{prefix}{param_name} - 验证失败: {str(e)}") 