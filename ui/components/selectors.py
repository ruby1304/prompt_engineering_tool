# ui/components/selectors.py
import streamlit as st
from config import get_available_models
from models.api_clients import get_provider_from_model

def select_single_model(key_prefix="model", help_text=None):
    """单模型选择器组件
    
    Args:
        key_prefix: 组件键前缀
        help_text: 帮助文本
    
    Returns:
        tuple: (model, provider) 选择的模型名称和提供商
    """
    # 动态获取所有可用模型
    available_models = get_available_models()
    all_models = []
    
    # 创建统一的模型列表，包含提供商信息
    for provider, models in available_models.items():
        for model in models:
            all_models.append((provider, model))
    
    # 创建格式化的选项列表，显示提供商信息
    model_options = [f"{model} ({provider})" for provider, model in all_models]
    model_map = {f"{model} ({provider})": (model, provider) for provider, model in all_models}
    
    # 如果没有可用模型，显示提示
    if not model_options:
        st.warning("未找到可用模型，请先在API管理页面配置模型")
        return None, None
    
    selected_model_option = st.selectbox(
        "选择模型",
        model_options,
        key=f"{key_prefix}_model_selector",
        help=help_text
    )
    
    # 返回选择的模型和提供商
    if selected_model_option:
        model, provider = model_map[selected_model_option]
        return model, provider
    
    return None, None

def select_multiple_models(key_prefix="multi_model", help_text=None):
    """多模型选择器组件
    
    Args:
        key_prefix: 组件键前缀
        help_text: 帮助文本
    
    Returns:
        list: 包含 {"model": model, "provider": provider} 字典的列表
    """
    # 动态获取所有可用模型
    available_models = get_available_models()
    all_models = []
    
    # 创建统一的模型列表，包含提供商信息
    for provider, models in available_models.items():
        for model in models:
            all_models.append((provider, model))
    
    # 创建格式化的选项列表，显示提供商信息
    model_options = [f"{model} ({provider})" for provider, model in all_models]
    model_map = {f"{model} ({provider})": (model, provider) for provider, model in all_models}
    
    # 如果没有可用模型，显示提示
    if not model_options:
        st.warning("未找到可用模型，请先在API管理页面配置模型")
        return []
    
    selected_model_options = st.multiselect(
        "选择模型",
        model_options,
        key=f"{key_prefix}_multi_model_selector",
        help=help_text
    )
    
    # 返回选择的模型和提供商列表
    selected_models = []
    for option in selected_model_options:
        model, provider = model_map[option]
        selected_models.append({"model": model, "provider": provider})
    
    return selected_models

def select_template(template_list, label="选择模板", key_prefix="template", help_text=None, allow_multiple=False):
    """模板选择器组件
    
    Args:
        template_list: 模板名称列表
        label: 选择器标签
        key_prefix: 组件键前缀
        help_text: 帮助文本
        allow_multiple: 是否允许多选
    
    Returns:
        str或list: 选择的模板名称或名称列表
    """
    if not template_list:
        st.warning("未找到模板，请先创建模板")
        return [] if allow_multiple else None
    
    if allow_multiple:
        selected = st.multiselect(
            label,
            template_list,
            key=f"{key_prefix}_template_selector",
            help=help_text
        )
    else:
        selected = st.selectbox(
            label,
            template_list,
            key=f"{key_prefix}_template_selector",
            help=help_text
        )
    
    return selected

def select_test_set(test_set_list, label="选择测试集", key_prefix="test_set", help_text=None):
    """测试集选择器组件
    
    Args:
        test_set_list: 测试集名称列表
        label: 选择器标签
        key_prefix: 组件键前缀
        help_text: 帮助文本
    
    Returns:
        str: 选择的测试集名称
    """
    if not test_set_list:
        st.warning("未找到测试集，请先创建测试集")
        return None
    
    selected = st.selectbox(
        label,
        test_set_list,
        key=f"{key_prefix}_test_set_selector",
        help=help_text
    )
    
    return selected

def select_provider(provider_list, label="选择提供商", key_prefix="provider", help_text=None):
    """提供商选择器组件
    
    Args:
        provider_list: 提供商名称列表
        label: 选择器标签
        key_prefix: 组件键前缀
        help_text: 帮助文本
    
    Returns:
        str: 选择的提供商名称
    """
    if not provider_list:
        st.warning("未找到提供商，请先添加提供商")
        return None
    
    selected = st.selectbox(
        label,
        provider_list,
        key=f"{key_prefix}_provider_selector",
        help=help_text
    )
    
    return selected

def select_optimization_strategy(key_prefix="strategy", help_text=None):
    """优化策略选择器组件
    
    Args:
        key_prefix: 组件键前缀
        help_text: 帮助文本
    
    Returns:
        str: 选择的优化策略
    """
    strategies = {
        "balanced": "平衡优化 - 兼顾所有评估维度",
        "accuracy": "准确性优化 - 注重内容的准确性和事实正确性",
        "completeness": "完整性优化 - 注重回答的全面性和深度",
        "conciseness": "简洁性优化 - 注重表达的简洁和高效",
        "creativity": "创造性优化 - 注重内容的新颖性和创意性"
    }
    
    strategy_options = list(strategies.keys())
    
    selected = st.selectbox(
        "选择优化策略",
        strategy_options,
        format_func=lambda x: strategies.get(x, x),
        key=f"{key_prefix}_strategy_selector",
        help=help_text
    )
    
    return selected


# ui/components/selectors.py 中添加

def select_evaluator_model(key_prefix="evaluator", help_text=None):
    """评估模型选择器组件
    
    Args:
        key_prefix: 组件键前缀
        help_text: 帮助文本
    
    Returns:
        tuple: (model, provider) 选择的模型名称和提供商
    """
    # 获取所有可用模型
    available_models = get_available_models()
    all_models = []
    
    # 创建统一的模型列表，包含提供商信息
    for provider, models in available_models.items():
        for model in models:
            all_models.append((provider, model))
    
    # 创建格式化的选项列表，显示提供商信息
    model_options = [f"{model} ({provider})" for provider, model in all_models]
    model_map = {f"{model} ({provider})": (model, provider) for provider, model in all_models}
    
    # 如果没有可用模型，显示提示
    if not model_options:
        st.warning("未找到可用模型，请先在API管理页面配置模型")
        return None, None
    
    # 尝试找到合适的默认选项（优先选择高能力模型）
    default_index = 0
    preferred_models = ["gpt-4", "claude-3-opus", "claude-3-sonnet", "gemini-1.5-pro", "grok-3"]
    for i, option in enumerate(model_options):
        for preferred in preferred_models:
            if preferred.lower() in option.lower():
                default_index = i
                break
    
    selected_model_option = st.selectbox(
        "评估模型",
        model_options,
        index=default_index,
        key=f"{key_prefix}_model_selector",
        help=help_text or "选择用于评估响应质量的模型"
    )
    
    # 返回选择的模型和提供商
    if selected_model_option:
        model, provider = model_map[selected_model_option]
        return model, provider
    
    return None, None
