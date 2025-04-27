import json
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any, Set

from config import TEST_SETS_DIR, save_test_set, load_test_set, get_test_set_list, delete_test_set


def generate_unique_id(prefix="case") -> str:
    """生成唯一的测试用例ID，确保不会重复

    Args:
        prefix: ID前缀

    Returns:
        唯一ID字符串
    """
    timestamp = int(time.time())
    unique_part = str(uuid.uuid4())[:8]  # 使用UUID的一部分，避免ID太长
    return f"{prefix}_{timestamp}_{unique_part}"


def get_shortened_id(case_id: str) -> str:
    """从完整ID中提取缩短版用于显示
    
    Args:
        case_id: 完整的测试用例ID
        
    Returns:
        缩短的ID，适合显示
    """
    if not case_id:
        return "未知ID"
        
    # 如果是自定义ID（不包含下划线），则直接返回
    if "_" not in case_id:
        return case_id
        
    # 如果是系统生成的ID (case_timestamp_uuid)，只返回uuid部分或截取部分
    parts = case_id.split("_")
    if len(parts) >= 3:
        return parts[-1][:6]  # 只显示UUID的前6位
    
    return case_id  # 无法解析时返回原始ID


def ensure_unique_id(case: Dict, existing_ids: Optional[Set[str]] = None) -> str:
    """确保测试用例有唯一ID，如果重复或不存在则生成新ID
    
    Args:
        case: 测试用例字典
        existing_ids: 已存在的ID集合
        
    Returns:
        唯一的ID
    """
    if existing_ids is None:
        existing_ids = set()
        
    # 如果ID不存在或在现有ID集合中，生成新ID
    if not case.get("id") or case.get("id") in existing_ids:
        new_id = generate_unique_id()
        case["id"] = new_id
    
    # 返回唯一ID
    return case["id"]


def create_new_test_set(name: Optional[str] = None, description: str = "") -> Dict:
    """创建新的测试集
    
    Args:
        name: 测试集名称，如果不提供则自动生成
        description: 测试集描述
        
    Returns:
        新创建的测试集字典
    """
    if not name:
        name = f"新测试集_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        
    return {
        "name": name,
        "description": description,
        "variables": {},
        "cases": [
            {
                "id": generate_unique_id(),
                "description": "测试用例1",
                "variables": {},
                "user_input": "这里填写用户的输入内容。",
                "expected_output": "这里填写期望的模型输出内容。评估将基于此内容判断模型响应的质量。",
                "evaluation_criteria": {
                    "accuracy": "评估响应与期望输出的匹配程度",
                    "completeness": "评估响应是否包含所有必要信息",
                    "relevance": "评估响应与提示词的相关性",
                    "clarity": "评估响应的清晰度和可理解性"
                }
            }
        ]
    }


def merge_test_sets(test_set_names: List[str]) -> Dict:
    """合并多个测试集
    
    Args:
        test_set_names: 要合并的测试集名称列表
        
    Returns:
        合并后的测试集字典
    """
    merged_cases = []
    seen_ids = set()
    merged_variables = {}
    
    for name in test_set_names:
        ts = load_test_set(name)
        if isinstance(ts.get("variables"), dict):
            merged_variables.update(ts["variables"])
        for case in ts.get("cases", []):
            cid = case.get("id")
            if cid in seen_ids:
                case = dict(case)
                case["id"] = generate_unique_id()
            seen_ids.add(case["id"])
            merged_cases.append(case)
    
    return {
        "name": f"合并集_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
        "description": f"由{', '.join(test_set_names)}合并而成",
        "variables": merged_variables,
        "cases": merged_cases
    }


def import_test_set_from_json(test_set_data: Dict) -> Dict:
    """从JSON数据导入测试集，确保数据完整性
    
    Args:
        test_set_data: 导入的测试集JSON数据
        
    Returns:
        处理后的测试集字典
    """
    # 确保cases字段存在且每个case都有正确的结构
    if "cases" in test_set_data:
        ids_seen = set()
        for case in test_set_data["cases"]:
            # 确保ID唯一
            ensure_unique_id(case, ids_seen)
            ids_seen.add(case["id"])
            
            # 确保基本字段存在
            if "description" not in case:
                case["description"] = "未命名测试用例"
                
            if "variables" not in case or not isinstance(case["variables"], dict):
                case["variables"] = {}
            
            if "user_input" not in case:
                case["user_input"] = ""
                
            if "expected_output" not in case:
                case["expected_output"] = ""
            
            # 确保评估标准字段存在
            if "evaluation_criteria" not in case or not isinstance(case["evaluation_criteria"], dict):
                case["evaluation_criteria"] = {
                    "accuracy": "评估准确性的标准",
                    "completeness": "评估完整性的标准",
                    "relevance": "评估相关性的标准",
                    "clarity": "评估清晰度的标准"
                }
                
    # 确保全局变量字段存在
    if "variables" not in test_set_data or not isinstance(test_set_data["variables"], dict):
        test_set_data["variables"] = {}
        
    # 确保名称和描述字段存在
    if "name" not in test_set_data or not test_set_data["name"]:
        test_set_data["name"] = f"导入测试集_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        
    if "description" not in test_set_data:
        test_set_data["description"] = "导入的测试集"
    
    return test_set_data


def add_test_case(test_set: Dict, case_data: Dict) -> Dict:
    """向测试集添加一个新的测试用例
    
    Args:
        test_set: 测试集字典
        case_data: 测试用例数据
        
    Returns:
        添加了新测试用例的测试集
    """
    if "cases" not in test_set:
        test_set["cases"] = []
    
    # 确保测试用例有唯一ID
    ids_seen = set(case.get("id", "") for case in test_set["cases"])
    ensure_unique_id(case_data, ids_seen)
    
    # 确保测试用例有必要的字段
    if "description" not in case_data:
        case_data["description"] = f"测试用例 {len(test_set['cases']) + 1}"
    if "variables" not in case_data:
        case_data["variables"] = {}
    if "evaluation_criteria" not in case_data:
        case_data["evaluation_criteria"] = {
            "accuracy": "评估响应与期望输出的匹配程度",
            "completeness": "评估响应是否包含所有必要信息",
            "relevance": "评估响应与提示词的相关性",
            "clarity": "评估响应的清晰度和可理解性"
        }
    
    test_set["cases"].append(case_data)
    return test_set


def update_test_case(test_set: Dict, case_id: str, updated_data: Dict) -> Dict:
    """更新测试集中的特定测试用例
    
    Args:
        test_set: 测试集字典
        case_id: 要更新的测试用例ID
        updated_data: 更新的测试用例数据
        
    Returns:
        更新后的测试集
    """
    for i, case in enumerate(test_set.get("cases", [])):
        if case.get("id") == case_id:
            # 确保ID不变
            updated_data["id"] = case_id
            test_set["cases"][i] = updated_data
            break
    
    return test_set


def delete_test_case(test_set: Dict, case_id: str) -> Dict:
    """从测试集中删除特定测试用例
    
    Args:
        test_set: 测试集字典
        case_id: 要删除的测试用例ID
        
    Returns:
        删除后的测试集
    """
    test_set["cases"] = [case for case in test_set.get("cases", []) if case.get("id") != case_id]
    return test_set


def filter_test_cases(test_set: Dict, search_query: str) -> List[Dict]:
    """根据搜索查询过滤测试用例
    
    Args:
        test_set: 测试集字典
        search_query: 搜索查询字符串
        
    Returns:
        过滤后的测试用例列表
    """
    if not search_query:
        return test_set.get("cases", [])
    
    search_query = search_query.lower()
    
    return [
        case for case in test_set.get("cases", []) if (
            search_query.lower() in case.get("id", "").lower() or
            search_query.lower() in case.get("description", "").lower() or
            search_query.lower() in case.get("user_input", "").lower() or
            search_query.lower() in case.get("expected_output", "").lower()
        )
    ]


def sort_test_cases(cases: List[Dict], sort_by: str) -> List[Dict]:
    """根据指定字段对测试用例进行排序
    
    Args:
        cases: 测试用例列表
        sort_by: 排序方式
        
    Returns:
        排序后的测试用例列表
    """
    sort_options = {
        "ID (升序)": lambda cases: sorted(cases, key=lambda x: x.get("id", "")),
        "ID (降序)": lambda cases: sorted(cases, key=lambda x: x.get("id", ""), reverse=True),
        "描述 (升序)": lambda cases: sorted(cases, key=lambda x: x.get("description", "")),
        "描述 (降序)": lambda cases: sorted(cases, key=lambda x: x.get("description", ""), reverse=True),
    }
    
    if sort_by in sort_options:
        return sort_options[sort_by](cases)
    
    return cases