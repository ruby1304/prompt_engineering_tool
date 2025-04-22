import streamlit as st
from config import get_available_models, load_provider_config, get_provider_list

def render_model_selector():
    """渲染模型选择界面"""
    st.title("🤖 模型选择")
    
    available_models = get_available_models()
    provider_list = get_provider_list()
    
    st.info("""
    在这里查看和管理可用的模型。您可以设置偏好的评估模型，并查看各模型的能力和价格信息。
    """)
    
    # 创建提供商选项卡
    tabs = st.tabs(provider_list)
    
    for i, provider in enumerate(provider_list):
        with tabs[i]:
            st.subheader(f"{provider.capitalize()}模型")
            
            models = available_models.get(provider, [])
            
            if not models:
                st.warning(f"未找到{provider}模型配置")
            else:
                # 获取提供商配置
                provider_config = load_provider_config(provider)
                is_custom = "custom_providers" in st.session_state and provider in st.session_state.custom_providers
                
                # 如果是自定义提供商，显示配置信息
                if is_custom:
                    st.info(f"""
                    **提供商信息**:
                    - 显示名称: {provider_config.get('display_name', provider.capitalize())}
                    - API基础URL: {provider_config.get('base_url', '未设置')}
                    - API类型: {provider_config.get('api_type', 'http')}
                    - 消息格式: {provider_config.get('message_format', 'openai')}
                    """)
                
                # 显示模型信息
                for model in models:
                    with st.expander(f"{model}"):
                        # 尝试获取模型详细信息 - 从配置或预定义信息
                        display_model_info(provider, model)
    
    # 评估模型设置
    st.divider()
    st.subheader("评估模型设置")
    
    # 获取当前配置
    from config import load_config, save_config
    
    config = load_config()
    current_evaluator = config.get("evaluator_model", "gpt-4")
    
    # 创建所有可用模型的列表
    all_models = []
    for provider, models in available_models.items():
        for model in models:
            all_models.append(f"{model} ({provider})")
    
    # 查找当前评估模型的索引
    current_index = 0
    for i, model_str in enumerate(all_models):
        if model_str.startswith(current_evaluator + " "):
            current_index = i
            break
    
    new_evaluator_str = st.selectbox(
        "选择评估模型",
        all_models,
        index=current_index if current_index < len(all_models) else 0,
        help="评估模型用于评估生成结果的质量"
    )
    
    # 从显示字符串中提取模型名称
    if new_evaluator_str:
        new_evaluator = new_evaluator_str.split(" (")[0]
        
        if st.button("保存评估模型设置"):
            config["evaluator_model"] = new_evaluator
            save_config(config)
            st.success(f"评估模型已设置为: {new_evaluator}")
    
    # 添加本地评估开关
    use_local = config.get("use_local_evaluation", False)
    new_use_local = st.checkbox(
        "使用本地评估（不调用API）", 
        value=use_local,
        help="选中此项将使用本地评估方法，而不调用评估模型API"
    )
    
    if new_use_local != use_local:
        config["use_local_evaluation"] = new_use_local
        save_config(config)
        st.success(f"本地评估设置已更新: {'启用' if new_use_local else '禁用'}")

def display_model_info(provider, model):
    """显示模型信息"""
    # 获取提供商配置
    provider_config = load_provider_config(provider)
    
    # 预定义模型信息
    predefined_models = {
        "gpt-3.5-turbo": {
            "capability": "良好的理解和生成能力，适合一般性任务",
            "context_window": "16K tokens",
            "price": "$0.0005 / 1K tokens (输入), $0.0015 / 1K tokens (输出)",
            "advantages": "价格低廉，响应速度快",
            "limitations": "复杂推理能力较弱，知识截止日期较早"
        },
        "gpt-4": {
            "capability": "很强的理解和推理能力，适合复杂任务",
            "context_window": "8K tokens",
            "price": "$0.03 / 1K tokens (输入), $0.06 / 1K tokens (输出)",
            "advantages": "较强的推理能力，更好的指令遵循能力",
            "limitations": "价格较高，响应速度较慢"
        },
    }
    
    # 如果是预定义模型，显示详细信息
    if model in predefined_models:
        model_info = predefined_models[model]
        st.write(f"""
        ### {model}
        - **能力**: {model_info['capability']}
        - **上下文窗口**: {model_info['context_window']}
        - **价格**: {model_info['price']}
        - **优势**: {model_info['advantages']}
        - **局限**: {model_info['limitations']}
        """)
    else:
        # 显示基本信息
        price_input = provider_config.get("price_input", 0)
        price_output = provider_config.get("price_output", 0)
        
        st.write(f"""
        ### {model}
        - **提供商**: {provider_config.get('display_name', provider.capitalize())}
        - **价格**: ${price_input:.6f} / 1K tokens (输入), ${price_output:.6f} / 1K tokens (输出)
        """)

if __name__ == "__main__":
    render_model_selector()
