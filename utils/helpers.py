"""
辅助函数模块，包含用于减少代码重复的通用功能
"""

import json
import re
from typing import Dict, Any, Optional, List, Tuple, Callable

from .constants import JSON_CODE_BLOCK_PATTERNS, DEFAULT_EVALUATION_CRITERIA

EFFICIENCY_CONFIG = {
    "ideal_token_count": 500,  # 期望的token数，对应高分
    "barely_pass_token_count": 1500  # 勉强及格的token数，对应低分
}


def extract_json_from_text(text: str) -> str:
    """
    从文本中提取JSON内容，处理多种常见的代码块格式
    
    Args:
        text: 包含JSON的文本
    
    Returns:
        str: 提取的JSON文本，如果无法提取则返回原文本
    """
    if not text:
        return text
        
    # 尝试使用不同的代码块模式
    for start_pattern, end_pattern in JSON_CODE_BLOCK_PATTERNS:
        if start_pattern in text:
            parts = text.split(start_pattern, 1)
            if len(parts) > 1:
                json_text = parts[1].split(end_pattern, 1)[0].strip()
                return json_text

    # 如果未找到代码块，返回原始文本
    return text.strip()


def fix_json_errors(json_text: str) -> str:
    """
    修复常见的JSON格式错误
    
    Args:
        json_text: 待修复的JSON文本
    
    Returns:
        str: 修复后的JSON文本
    """
    # 1. 替换未配对的引号
    quote_count = json_text.count('"') 
    if quote_count % 2 != 0:
        # 有未配对的引号，尝试通过在结尾添加引号来修复
        json_text += '"'
    
    # 2. 移除尾部的逗号（如 {"key": "value",} ）
    json_text = re.sub(r',\s*}', '}', json_text)
    json_text = re.sub(r',\s*]', ']', json_text)
    
    # 3. 修复缺少的大括号或中括号
    open_braces = json_text.count('{')
    close_braces = json_text.count('}')
    if open_braces > close_braces:
        json_text += "}" * (open_braces - close_braces)
    
    open_brackets = json_text.count('[')
    close_brackets = json_text.count(']')
    if open_brackets > close_brackets:
        json_text += "]" * (open_brackets - close_brackets)
    
    return json_text


def parse_json_response(text: str) -> Tuple[Dict[str, Any], Optional[str]]:
    """
    解析模型返回的JSON响应，处理常见的格式问题
    
    Args:
        text: 模型返回的文本
        
    Returns:
        Tuple[Dict, Optional[str]]: 元组，包含解析后的JSON数据和可能的错误信息
    """
    if not text:
        return {}, "空响应内容"
    
    try:
        # 提取JSON文本
        json_text = extract_json_from_text(text)
        
        # 修复常见的JSON错误
        json_text = fix_json_errors(json_text)
        
        # 尝试解析JSON
        result = json.loads(json_text)
        return result, None
        
    except json.JSONDecodeError as e:
        return {}, f"JSON解析错误: {str(e)}"
    except Exception as e:
        return {}, f"处理JSON响应时出错: {str(e)}"


def ensure_test_case_fields(case: Dict[str, Any]) -> Dict[str, Any]:
    """
    确保测试用例包含所有必要的字段，如果缺失则添加默认值
    
    Args:
        case: 测试用例字典
    
    Returns:
        Dict: 补充了默认字段的测试用例
    """
    import time
    import uuid
    
    # 克隆测试用例以避免修改原始对象
    case_copy = dict(case)
    
    # 确保有唯一ID
    if "id" not in case_copy or not case_copy["id"]:
        case_copy["id"] = f"gen_{int(time.time())}_{uuid.uuid4().hex[:8]}"
    
    # 确保有描述
    if "description" not in case_copy or not case_copy["description"]:
        case_copy["description"] = f"自动生成的测试用例 {case_copy['id']}"
    
    # 确保有评估标准
    if "evaluation_criteria" not in case_copy or not case_copy["evaluation_criteria"]:
        case_copy["evaluation_criteria"] = dict(DEFAULT_EVALUATION_CRITERIA)
    
    # 确保有变量字段
    if "variables" not in case_copy:
        case_copy["variables"] = {}
        
    return case_copy


class ProgressTracker:
    """
    通用进度追踪类，用于多层级进度追踪和回调
    """
    
    def __init__(self, 
                total_steps: int = 1, 
                callback: Optional[Callable] = None, # Callback signature: (current, total, description, data)
                parent: Optional['ProgressTracker'] = None,
                description: str = ""):
        """
        初始化进度追踪器
        
        Args:
            total_steps: 总步骤数
            callback: 进度回调函数，接收(current, total, description, data)
            parent: 父级追踪器（用于嵌套进度）
            description: 进度描述
        """
        self.total = max(1, total_steps)  # 避免除零错误
        self.current = 0
        self.callback = callback
        self.parent = parent
        self.description = description
        
    def update(self, steps: int = 1, description: Optional[str] = None, data_update: Optional[Dict] = None) -> None:
        """
        更新进度
        
        Args:
            steps: 前进的步骤数量
            description: 更新的进度描述（可选）
            data_update: 传递给回调的附加数据字典
        """
        self.current = min(self.total, self.current + steps)
        desc_to_use = description if description is not None else self.description
        
        # Prepare data for the current callback
        current_callback_data = data_update if data_update is not None else {}

        if self.callback:
            self.callback(self.current, self.total, desc_to_use, current_callback_data)
            
        if self.parent:
            # When updating a parent, the 'steps' for the parent is fractional based on child's progress.
            # The 'data_update' for the parent's callback should include info about the child's state.
            parent_step_contribution = steps / self.total # This is how much this child contributed to one step of parent
            
            # Data to pass to parent's callback, indicating it's from a child update
            parent_data_update = {
                'child_description': desc_to_use,
                'child_current': self.current,
                'child_total': self.total,
                'child_data': current_callback_data # Pass along data from the child
            }
            # Merge with any existing data_update if it was meant for the parent specifically (though less common)
            if data_update and self.parent.callback: # if data_update was for parent
                 parent_data_update.update(data_update)

            self.parent.update(parent_step_contribution, self.parent.description, data_update=parent_data_update)
            
    def complete(self, description: Optional[str] = None, data_to_add: Optional[Dict] = None) -> None:
        """
        标记进度为完成
        
        Args:
            description: 更新的进度描述（可选）
            data_to_add: 完成时传递给回调的附加数据
        """
        remaining_steps = self.total - self.current
        if remaining_steps >= 0: # Ensure we only update if not already past total
            self.update(remaining_steps, description, data_update=data_to_add)


def calculate_prompt_efficiency(prompt_tokens: int, variable_token_weights: Optional[Dict[str, int]] = None) -> int:
    """
    计算提示词效率分数，考虑系统变量的token权重

    Args:
        prompt_tokens: 提示词的token数量
        variable_token_weights: 系统变量的token权重字典（可选）

    Returns:
        int: 效率分数(0-100)
    """
    ideal = EFFICIENCY_CONFIG["ideal_token_count"]
    barely_pass = EFFICIENCY_CONFIG["barely_pass_token_count"]

    # 如果提供了变量权重，调整token数
    if variable_token_weights:
        adjusted_tokens = sum(variable_token_weights.values())
        prompt_tokens += adjusted_tokens

    if prompt_tokens <= ideal:
        return 100  # 期望token数及以下，满分

    if prompt_tokens >= barely_pass:
        return 0  # 勉强及格的token数及以上，最低分

    # 线性插值计算分数
    score_range = 100 - 0
    token_range = barely_pass - ideal
    score = 100 - ((prompt_tokens - ideal) / token_range) * score_range
    return max(0, min(100, int(score)))