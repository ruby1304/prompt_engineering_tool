import json
import os
from pathlib import Path
from typing import Dict, List, Optional, Any

# 创建必要的目录
BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
CONFIG_FILE = DATA_DIR / "config.json"
TEMPLATES_DIR = DATA_DIR / "templates"
TEST_SETS_DIR = DATA_DIR / "test_sets"
RESULTS_DIR = DATA_DIR / "results"
PROVIDERS_DIR = DATA_DIR / "providers"  # 新增：服务提供商配置目录
SYSTEM_TEMPLATES_DIR = DATA_DIR / "system_templates"  # 新增：系统提示词模板目录

for directory in [DATA_DIR, TEMPLATES_DIR, TEST_SETS_DIR, RESULTS_DIR, PROVIDERS_DIR, SYSTEM_TEMPLATES_DIR]:
    directory.mkdir(exist_ok=True, parents=True)

# 默认提供商配置
DEFAULT_PROVIDER_CONFIG = {
    "name": "",
    "display_name": "",
    "api_key": "",
    "api_url": "",
    "models": [],
    "api_type": "rest",  # 可选：rest, websocket 等
    "headers": {},  # 自定义请求头
    "parameters": {}  # 自定义参数
}

# 默认配置
DEFAULT_CONFIG = {
    "api_keys": {
        # "openai": "",
        # "anthropic": "",
        # "google": "",
        "xai": "",
        "azure": ""
    },
    "models": {
        # "openai": ["gpt-3.5-turbo", "gpt-4", "gpt-4o"],
        # "anthropic": ["claude-3-opus-20240229", "claude-3-sonnet-20240229", "claude-3-haiku-20240307"],
        # "google": ["gemini-1.0-pro", "gemini-1.5-pro"],
        "xai": ["grok-3"],
        "azure": ["gpt-4o"]
    },
    "custom_providers": [],  # 新增：用户添加的自定义提供商列表
    "evaluator_model": "gpt-4o",
    "default_params": {
        "temperature": 0.7,
        "max_tokens": 1000,
        "top_p": 1.0
    },
    "use_local_evaluation": False,
    "system_templates": {  # 新增：系统提示词模板类型
        "evaluator": "evaluator_template",
        "optimizer": "optimizer_template",
        "criteria_generator": "criteria_generator_template",
        "testcase_generator": "testcase_generator_template"
    }
}

# 默认系统提示词模板
DEFAULT_SYSTEM_TEMPLATES = {
    "evaluator_template": {
        "name": "evaluator_template",
        "description": "用于评估模型响应的提示词模板",
        "template": """你是一个专业的AI响应质量评估专家。请对以下AI生成的响应进行评估:

原始提示词: {{prompt}}

模型响应:
{{model_response}}

期望输出:
{{expected_output}}

评估标准:
{{evaluation_criteria}}

请按以下格式给出评估分数和分析:
{
  "scores": {
    "accuracy": <0-100分，评估响应与期望输出的准确度>,
    "completeness": <0-100分，评估响应是否涵盖了所有期望的要点>,
    "relevance": <0-100分，评估响应与原始提示词的相关性>,
    "clarity": <0-100分，评估响应的清晰度和可理解性>
  },
  "analysis": "<详细分析，包括优点和改进建议>",
  "overall_score": <0-100分，综合评分>
}

仅返回JSON格式的评估结果，不要包含其他文本。""",
        "variables": {
            "prompt": {
                "description": "原始提示词",
                "default": "请分析这段文本的情感"
            },
            "model_response": {
                "description": "模型生成的响应",
                "default": "文本表达了积极的情感。"
            },
            "expected_output": {
                "description": "期望的输出",
                "default": "这段文本表达了积极的情感，情感分数为0.8。"
            },
            "evaluation_criteria": {
                "description": "评估标准",
                "default": "{\n  \"accuracy\": \"评估响应与期望输出的匹配程度\",\n  \"completeness\": \"评估响应是否包含所有必要信息\"\n}"
            }
        },
        "is_system": True
    },
    "optimizer_template": {
        "name": "optimizer_template",
        "description": "用于优化提示词的提示词模板",
        "template": """你是一个专业的提示词工程优化专家。请基于详细的评估分析，为原始提示词生成3个针对性优化版本。

原始提示词:
{{original_prompt}}

评估结果摘要:
{{results_summary}}

主要问题分析:
{{problem_analysis}}

优化指导:
{{optimization_guidance}}

请生成3个不同的优化版本，每个版本针对不同的问题方向。对每个版本，请详细说明:
1. 应用的优化策略
2. 如何解决发现的问题
3. 预期的效果改进

请按以下JSON格式返回优化结果:
```json
{
  "optimized_prompts": [
    {
      "prompt": "优化后的提示词内容1",
      "strategy": "应用的优化策略说明",
      "problem_addressed": "针对解决的主要问题",
      "expected_improvements": "预期的效果改进",
      "reasoning": "为什么这种修改能解决问题"
    },
    {
      "prompt": "优化后的提示词内容2",
      "strategy": "应用的优化策略说明",
      "problem_addressed": "针对解决的主要问题",
      "expected_improvements": "预期的效果改进",
      "reasoning": "为什么这种修改能解决问题"
    },
    {
      "prompt": "优化后的提示词内容3",
      "strategy": "应用的优化策略说明",
      "problem_addressed": "针对解决的主要问题",
      "expected_improvements": "预期的效果改进",
      "reasoning": "为什么这种修改能解决问题"
    }
  ]
}
```
仅返回JSON格式的优化结果，不要包含其他文本。""",
        "variables": {
            "original_prompt": {
                "description": "原始提示词",
                "default": "你是一个助手。请回答用户的问题。"
            },
            "results_summary": {
                "description": "评估结果摘要",
                "default": "整体得分: 70分\n准确性: 65分\n完整性: 75分\n相关性: 80分\n清晰度: 60分"
            },
            "problem_analysis": {
                "description": "问题分析",
                "default": "主要问题是在准确性和清晰度方面表现不佳"
            },
            "optimization_guidance": {
                "description": "优化指导",
                "default": "提供更明确的角色定义，添加输出格式要求，提高响应的完整性"
            }
        },
        "is_system": True
    },
    "criteria_generator_template": {
        "name": "criteria_generator_template",
        "description": "用于生成评估标准的提示词模板",
        "template": """你是一位资深的AI模型评估专家。请根据以下测试用例信息，为AI回答生成全面的评估标准。

测试用例描述:
{{case_description}}

用户输入:
{{user_input}}

期望输出:
{{expected_output}}

请生成以下四个维度的评估标准，描述应该具体且可衡量：
1. accuracy（准确性）- 评估响应与期望输出的匹配程度
2. completeness（完整性）- 评估响应是否包含所有必要信息
3. relevance（相关性）- 评估响应与提示词和用户输入的相关程度
4. clarity（清晰度）- 评估响应的表达是否清晰易懂

使用以下JSON格式返回评估标准:
```json
{
  "accuracy": "具体描述准确性的评估标准",
  "completeness": "具体描述完整性的评估标准",
  "relevance": "具体描述相关性的评估标准",
  "clarity": "具体描述清晰度的评估标准"
}
```

只返回JSON格式的评估标准，不要包含其他解释。""",
        "variables": {
            "case_description": {
                "description": "测试用例描述",
                "default": "情感分析测试"
            },
            "user_input": {
                "description": "用户输入",
                "default": "我今天感到非常高兴，一切都很顺利！"
            },
            "expected_output": {
                "description": "期望输出",
                "default": "{\n  \"sentiment\": \"positive\",\n  \"score\": 0.9,\n  \"analysis\": \"文本表达了强烈的积极情感\"\n}"
            }
        },
        "is_system": True
    },
    "testcase_generator_template": {
        "name": "testcase_generator_template",
        "description": "用于自动生成测试用例的提示词模板",
        "template": """你是一位专业的测试用例设计专家。请根据以下测试结果，设计一组高质量的测试用例，用于评估AI模型的性能。

评估模型: {{model}}
测试目标: {{test_purpose}}

以下是一个已有的测试用例及其评估结果的示例：
{{example_test_case}}

请设计3个新的测试用例，确保它们涵盖不同的场景和边界条件，能够全面测试模型的性能。每个测试用例应包含：
1. 用例ID
2. 描述
3. 用户输入
4. 期望输出
5. 评估标准（针对准确性、完整性、相关性和清晰度）

请按以下JSON格式返回测试用例：
```json
{
  "test_cases": [
    {
      "id": "唯一的测试用例ID",
      "description": "测试用例描述",
      "user_input": "发送给模型的用户输入文本",
      "expected_output": "期望模型生成的输出",
      "evaluation_criteria": {
        "accuracy": "准确性评估标准",
        "completeness": "完整性评估标准",
        "relevance": "相关性评估标准",
        "clarity": "清晰度评估标准"
      }
    },
    ...
  ]
}
```

请确保每个测试用例的输入和预期输出是真实可用的，能够实际用于测试。评估标准应该明确具体，便于衡量模型的表现。只返回JSON格式的测试用例，不要包含其他解释。""",
        "variables": {
            "model": {
                "description": "要测试的模型名称",
                "default": "gpt-4"
            },
            "test_purpose": {
                "description": "测试目的",
                "default": "测试模型在多种场景下的回答质量"
            },
            "example_test_case": {
                "description": "示例测试用例",
                "default": "用例ID: test-1\n描述: 测试模型对简单问题的回答\n用户输入: \"什么是机器学习？\"\n期望输出: \"机器学习是人工智能的一个子领域，它允许计算机系统从数据中学习和改进，而无需明确编程。\"\n评估结果: 准确性得分 85/100，完整性得分 75/100"
            }
        },
        "is_system": True
    }
}

def load_config() -> Dict:
    """加载配置文件，如不存在则创建默认配置"""
    if not CONFIG_FILE.exists():
        save_config(DEFAULT_CONFIG)
        return DEFAULT_CONFIG
    
    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def save_config(config: Dict) -> None:
    """保存配置到文件"""
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2, ensure_ascii=False)

def update_api_key(provider: str, key: str) -> None:
    """更新指定提供商的API密钥"""
    config = load_config()
    
    # 检查是否为内置提供商
    if provider in config["api_keys"]:
        config["api_keys"][provider] = key
    else:
        # 检查是否为自定义提供商
        provider_found = False
        for custom_provider in config.get("custom_providers", []):
            if custom_provider == provider:
                provider_found = True
                # 更新自定义提供商配置文件
                provider_config = load_provider_config(provider)
                provider_config["api_key"] = key
                save_provider_config(provider, provider_config)
                break
        
        if not provider_found:
            # 如果是新提供商，添加到自定义提供商列表
            if "custom_providers" not in config:
                config["custom_providers"] = []
            config["custom_providers"].append(provider)
            
            # 创建新提供商配置文件
            provider_config = dict(DEFAULT_PROVIDER_CONFIG)
            provider_config["name"] = provider
            provider_config["display_name"] = provider.capitalize()
            provider_config["api_key"] = key
            save_provider_config(provider, provider_config)
    
    save_config(config)

def get_api_key(provider: str) -> str:
    """获取指定提供商的API密钥"""
    config = load_config()
    
    # 检查是否为内置提供商
    if provider in config["api_keys"]:
        return config["api_keys"].get(provider, "")
    else:
        # 检查是否为自定义提供商
        provider_config = load_provider_config(provider)
        return provider_config.get("api_key", "")

def get_available_models() -> Dict[str, List[str]]:
    """获取所有可用的模型列表，包括自定义提供商的模型"""
    config = load_config()
    models = dict(config["models"])
    
    # 添加自定义提供商的模型
    for provider_name in config.get("custom_providers", []):
        provider_config = load_provider_config(provider_name)
        models[provider_name] = provider_config.get("models", [])
    
    return models

def get_template_list() -> List[str]:
    """获取所有提示词模板列表"""
    return [f.name.replace(".json", "") for f in TEMPLATES_DIR.glob("*.json")]

def get_system_template_list() -> List[str]:
    """获取所有系统提示词模板列表"""
    return [f.name.replace(".json", "") for f in SYSTEM_TEMPLATES_DIR.glob("*.json")]

def get_all_templates() -> Dict[str, List[str]]:
    """获取所有模板，分为普通模板和系统模板"""
    return {
        "normal": get_template_list(),
        "system": get_system_template_list()
    }

def save_template(name: str, template: Dict) -> None:
    """保存提示词模板"""
    # 根据是否是系统模板决定保存位置
    if template.get("is_system", False):
        file_path = SYSTEM_TEMPLATES_DIR / f"{name}.json"
    else:
        file_path = TEMPLATES_DIR / f"{name}.json"

    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(template, f, indent=2, ensure_ascii=False)

def load_template(name: str) -> Dict:
    """加载提示词模板"""
    # 先检查普通模板
    template_path = TEMPLATES_DIR / f"{name}.json"
    if template_path.exists():
        with open(template_path, "r", encoding="utf-8") as f:
            return json.load(f)
    
    # 再检查系统模板
    system_template_path = SYSTEM_TEMPLATES_DIR / f"{name}.json"
    if system_template_path.exists():
        with open(system_template_path, "r", encoding="utf-8") as f:
            return json.load(f)
    
    # 如果都不存在，抛出错误
    raise FileNotFoundError(f"模板 '{name}' 不存在")

def initialize_system_templates():
    """初始化系统提示词模板"""
    for template_name, template_data in DEFAULT_SYSTEM_TEMPLATES.items():
        system_template_path = SYSTEM_TEMPLATES_DIR / f"{template_name}.json"
        if not system_template_path.exists():
            save_template(template_name, template_data)
    
    # 更新配置文件中的系统模板引用
    config = load_config()
    if "system_templates" not in config:
        config["system_templates"] = DEFAULT_CONFIG["system_templates"]
        save_config(config)

def get_system_template(template_type: str) -> Dict:
    """根据类型获取系统提示词模板"""
    config = load_config()
    template_name = config.get("system_templates", {}).get(template_type)
    
    if not template_name:
        # 如果配置中没有，使用默认值
        template_name = DEFAULT_CONFIG["system_templates"].get(template_type)
    
    # 尝试加载模板
    try:
        return load_template(template_name)
    except FileNotFoundError:
        # 如果找不到，返回默认模板
        return DEFAULT_SYSTEM_TEMPLATES.get(template_type, {})

def save_test_set(name: str, test_set: Dict) -> None:
    """保存测试集"""
    with open(TEST_SETS_DIR / f"{name}.json", "w", encoding="utf-8") as f:
        json.dump(test_set, f, indent=2, ensure_ascii=False)

def load_test_set(name: str) -> Dict:
    """加载测试集"""
    with open(TEST_SETS_DIR / f"{name}.json", "r", encoding="utf-8") as f:
        return json.load(f)

def save_result(name: str, result: Dict) -> None:
    """保存测试结果"""
    with open(RESULTS_DIR / f"{name}.json", "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)

def load_result(name: str) -> Dict:
    """加载测试结果"""
    with open(RESULTS_DIR / f"{name}.json", "r", encoding="utf-8") as f:
        return json.load(f)

def get_result_list() -> List[str]:
    """获取所有测试结果列表"""
    return [f.name.replace(".json", "") for f in RESULTS_DIR.glob("*.json")]

def get_test_set_list() -> List[str]:
    """获取所有测试集列表"""
    return [f.name.replace(".json", "") for f in TEST_SETS_DIR.glob("*.json")]

def save_provider_config(provider_name: str, config: Dict) -> None:
    """保存提供商配置"""
    config_path = PROVIDERS_DIR / f"{provider_name}.json"
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2, ensure_ascii=False)

def load_provider_config(provider_name: str) -> Dict:
    """加载提供商配置"""
    config_path = PROVIDERS_DIR / f"{provider_name}.json"
    if not config_path.exists():
        return dict(DEFAULT_PROVIDER_CONFIG)
    
    with open(config_path, "r", encoding="utf-8") as f:
        return json.load(f)

def get_provider_list() -> List[str]:
    """获取所有提供商列表，包括内置和自定义提供商"""
    config = load_config()
    providers = list(config["api_keys"].keys())
    providers.extend(config.get("custom_providers", []))
    return providers

def add_model_to_provider(provider: str, model: str) -> None:
    """向提供商添加新模型"""
    config = load_config()
    
    # 检查是否为内置提供商
    if provider in config["models"]:
        if model not in config["models"][provider]:
            config["models"][provider].append(model)
            save_config(config)
    else:
        # 检查是否为自定义提供商
        provider_config = load_provider_config(provider)
        if "models" not in provider_config:
            provider_config["models"] = []
        
        if model not in provider_config["models"]:
            provider_config["models"].append(model)
            save_provider_config(provider, provider_config)

def remove_model_from_provider(provider: str, model: str) -> None:
    """从提供商移除模型"""
    config = load_config()
    
    # 检查是否为内置提供商
    if provider in config["models"]:
        if model in config["models"][provider]:
            config["models"][provider].remove(model)
            save_config(config)
    else:
        # 检查是否为自定义提供商
        provider_config = load_provider_config(provider)
        if "models" in provider_config and model in provider_config["models"]:
            provider_config["models"].remove(model)
            save_provider_config(provider, provider_config)

def add_custom_provider(provider_config: Dict) -> None:
    """添加自定义提供商"""
    config = load_config()
    
    provider_name = provider_config["name"]
    
    # 添加到自定义提供商列表
    if "custom_providers" not in config:
        config["custom_providers"] = []
    
    if provider_name not in config["custom_providers"]:
        config["custom_providers"].append(provider_name)
        save_config(config)
    
    # 保存提供商配置
    save_provider_config(provider_name, provider_config)

def remove_custom_provider(provider_name: str) -> None:
    """移除自定义提供商"""
    config = load_config()
    
    # 从自定义提供商列表中移除
    if "custom_providers" in config and provider_name in config["custom_providers"]:
        config["custom_providers"].remove(provider_name)
        save_config(config)
    
    # 删除提供商配置文件
    config_path = PROVIDERS_DIR / f"{provider_name}.json"
    if config_path.exists():
        config_path.unlink()
