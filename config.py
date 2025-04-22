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

for directory in [DATA_DIR, TEMPLATES_DIR, TEST_SETS_DIR, RESULTS_DIR, PROVIDERS_DIR]:
    directory.mkdir(exist_ok=True, parents=True)

# 默认配置
DEFAULT_CONFIG = {
    "api_keys": {
        "openai": "",
        "anthropic": "",
        "google": "",
        "xai": ""
    },
    "models": {
        "openai": ["gpt-3.5-turbo", "gpt-4", "gpt-4o"],
        "anthropic": ["claude-3-opus-20240229", "claude-3-sonnet-20240229", "claude-3-haiku-20240307"],
        "google": ["gemini-1.0-pro", "gemini-1.5-pro"],
        "xai": ["grok-3"]
    },
    "custom_providers": [],  # 新增：用户添加的自定义提供商列表
    "evaluator_model": "gpt-4",
    "default_params": {
        "temperature": 0.7,
        "max_tokens": 1000,
        "top_p": 1.0
    },
    "use_local_evaluation": False
}

# 默认提供商配置模板
DEFAULT_PROVIDER_CONFIG = {
    "name": "",                   # 提供商名称
    "display_name": "",           # 显示名称
    "api_key": "",                # API密钥
    "base_url": "",               # API基础URL
    "models": [],                 # 支持的模型列表
    "api_type": "http",           # API类型: http, sdk, local
    "message_format": "openai",   # 消息格式: openai, text
    "price_input": 0.0,           # 输入价格 (每1000 tokens)
    "price_output": 0.0,          # 输出价格 (每1000 tokens)
    "headers": {                  # 请求头
        "Content-Type": "application/json",
        "Authorization": "Bearer {api_key}"
    },
    "endpoints": {                # API端点
        "chat": "/chat/completions"
    },
    "params_mapping": {           # 参数映射
        "model": "model",
        "messages": "messages",
        "temperature": "temperature",
        "max_tokens": "max_tokens",
        "top_p": "top_p"
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

def get_test_set_list() -> List[str]:
    """获取所有测试集列表"""
    return [f.name.replace(".json", "") for f in TEST_SETS_DIR.glob("*.json")]

def save_template(name, template):
    """保存提示词模板
    
    Args:
        name: 模板名称
        template: 模板数据
    """
    # 创建保存目录
    template_dir = DATA_DIR / "templates"
    template_dir.mkdir(exist_ok=True)
    
    # 保存模板
    template_path = template_dir / f"{name}.json"
    with open(template_path, "w", encoding="utf-8") as f:
        json.dump(template, f, ensure_ascii=False, indent=2)
    
    return template_path

def load_template(name: str) -> Dict:
    """加载提示词模板"""
    with open(TEMPLATES_DIR / f"{name}.json", "r", encoding="utf-8") as f:
        return json.load(f)

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
