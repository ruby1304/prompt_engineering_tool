import streamlit as st
import json
import pandas as pd
from typing import Dict, List
from config import (
    get_provider_list, load_provider_config, add_custom_provider, 
    remove_custom_provider, update_api_key, add_model_to_provider,
    remove_model_from_provider, DEFAULT_PROVIDER_CONFIG
)

def render_provider_manager():
    st.title("🌐 模型提供商管理")
    
    st.markdown("""
    在这里管理您的模型提供商。您可以设置API密钥、基础URL、支持的模型等信息，
    以便在测试和优化过程中使用这些提供商的模型。
    """)
    
    # 获取提供商列表
    provider_list = get_provider_list()
    
    # 创建选项卡
    tab1, tab2 = st.tabs(["提供商管理", "添加新提供商"])
    
    with tab1:
        if not provider_list:
            st.info("暂无提供商，请先添加提供商")
        else:
            # 创建提供商选择器
            selected_provider = st.selectbox(
                "选择提供商",
                provider_list
            )
            
            if selected_provider:
                display_provider_details(selected_provider)
    
    with tab2:
        create_new_provider()

def display_provider_details(provider_name: str):
    """显示提供商详细信息"""
    # 加载提供商配置
    provider_config = load_provider_config(provider_name)
    
    # 显示提供商基本信息
    st.subheader(f"提供商: {provider_config.get('display_name', provider_name)}")
    
    # 提供商类型
    is_custom = "custom_providers" in st.session_state and provider_name in st.session_state.custom_providers
    provider_type = "自定义提供商" if is_custom else "内置提供商"
    st.markdown(f"**类型**: {provider_type}")
    
    # API密钥
    api_key = provider_config.get("api_key", "")
    new_api_key = st.text_input(
        "API密钥",
        value=api_key if api_key else "",
        type="password",
        help="输入您的API密钥"
    )
    
    if st.button("保存API密钥", key=f"save_key_{provider_name}"):
        update_api_key(provider_name, new_api_key)
        st.success(f"{provider_name} API密钥已保存")
    
    # 如果是自定义提供商，显示更多配置选项
    if is_custom:
        with st.expander("提供商高级配置"):
            # 基础URL
            base_url = provider_config.get("base_url", "")
            new_base_url = st.text_input(
                "API基础URL",
                value=base_url,
                help="输入API基础URL，例如: https://api.example.com"
            )
            if base_url != new_base_url:
                provider_config["base_url"] = new_base_url
                add_custom_provider(provider_config)
            
            # API类型
            api_type = provider_config.get("api_type", "http")
            new_api_type = st.selectbox(
                "API类型",
                ["http", "sdk", "local"],
                index=["http", "sdk", "local"].index(api_type) if api_type in ["http", "sdk", "local"] else 0
            )
            if api_type != new_api_type:
                provider_config["api_type"] = new_api_type
                add_custom_provider(provider_config)
            
            # 消息格式
            message_format = provider_config.get("message_format", "openai")
            new_message_format = st.selectbox(
                "消息格式",
                ["openai", "text"],
                index=["openai", "text"].index(message_format) if message_format in ["openai", "text"] else 0
            )
            if message_format != new_message_format:
                provider_config["message_format"] = new_message_format
                add_custom_provider(provider_config)
            
            # API端点
            endpoints = provider_config.get("endpoints", {})
            chat_endpoint = endpoints.get("chat", "/chat/completions")
            new_chat_endpoint = st.text_input(
                "聊天完成端点",
                value=chat_endpoint,
                help="聊天完成API端点，例如: /chat/completions"
            )
            if chat_endpoint != new_chat_endpoint:
                if "endpoints" not in provider_config:
                    provider_config["endpoints"] = {}
                provider_config["endpoints"]["chat"] = new_chat_endpoint
                add_custom_provider(provider_config)
            
            # 请求头
            st.subheader("请求头")
            
            headers = provider_config.get("headers", {
                "Content-Type": "application/json",
                "Authorization": "Bearer {api_key}"
            })
            
            headers_df = pd.DataFrame({
                "键": list(headers.keys()),
                "值": list(headers.values())
            })
            
            edited_headers = st.data_editor(
                headers_df,
                num_rows="dynamic",
                use_container_width=True
            )
            
            if not headers_df.equals(edited_headers):
                # 更新请求头
                new_headers = {}
                for _, row in edited_headers.iterrows():
                    if not pd.isna(row["键"]) and not pd.isna(row["值"]):
                        new_headers[row["键"]] = row["值"]
                
                provider_config["headers"] = new_headers
                add_custom_provider(provider_config)
            
            # 参数映射
            st.subheader("参数映射")
            
            params_mapping = provider_config.get("params_mapping", {
                "model": "model",
                "messages": "messages",
                "temperature": "temperature",
                "max_tokens": "max_tokens",
                "top_p": "top_p"
            })
            
            mapping_df = pd.DataFrame({
                "标准参数": list(params_mapping.keys()),
                "提供商参数": list(params_mapping.values())
            })
            
            edited_mapping = st.data_editor(
                mapping_df,
                num_rows="dynamic",
                use_container_width=True
            )
            
            if not mapping_df.equals(edited_mapping):
                # 更新参数映射
                new_mapping = {}
                for _, row in edited_mapping.iterrows():
                    if not pd.isna(row["标准参数"]) and not pd.isna(row["提供商参数"]):
                        new_mapping[row["标准参数"]] = row["提供商参数"]
                
                provider_config["params_mapping"] = new_mapping
                add_custom_provider(provider_config)
            
            # 删除提供商按钮
            if st.button("删除此提供商", type="primary", key=f"delete_{provider_name}"):
                remove_custom_provider(provider_name)
                st.success(f"已删除提供商: {provider_name}")
                st.experimental_rerun()
    
    # 模型管理
    st.subheader("模型管理")
    
    # 显示现有模型
    models = provider_config.get("models", [])
    
    if not models:
        st.info("暂无模型，请添加模型")
    else:
        st.write("当前支持的模型:")
        
        for i, model in enumerate(models):
            col1, col2 = st.columns([3, 1])
            
            with col1:
                st.write(f"- {model}")
            
            with col2:
                if st.button("移除", key=f"remove_model_{i}"):
                    remove_model_from_provider(provider_name, model)
                    st.success(f"已移除模型: {model}")
                    st.experimental_rerun()
    
    # 添加新模型
    with st.form("add_model_form"):
        st.subheader("添加新模型")
        
        new_model = st.text_input(
            "模型名称",
            help="输入新模型的名称"
        )
        
        submit_button = st.form_submit_button("添加模型")
        
        if submit_button and new_model:
            add_model_to_provider(provider_name, new_model)
            st.success(f"已添加模型: {new_model}")
            st.experimental_rerun()

def create_new_provider():
    """创建新的提供商"""
    with st.form("add_provider_form"):
        st.subheader("添加新提供商")
        
        provider_name = st.text_input(
            "提供商标识",
            help="输入提供商的唯一标识，例如: 'openai', 'custom-api'（仅使用字母、数字和连字符）"
        )
        
        display_name = st.text_input(
            "显示名称",
            help="输入提供商的显示名称，例如: 'OpenAI', '自定义API'"
        )
        
        api_key = st.text_input(
            "API密钥",
            type="password",
            help="输入API密钥"
        )
        
        base_url = st.text_input(
            "API基础URL",
            help="输入API基础URL，例如: https://api.example.com"
        )
        
        api_type = st.selectbox(
            "API类型",
            ["http", "sdk", "local"],
            index=0,
            help="选择API类型"
        )
        
        message_format = st.selectbox(
            "消息格式",
            ["openai", "text"],
            index=0,
            help="选择消息格式，'openai'表示使用OpenAI风格的messages参数，'text'表示使用普通文本"
        )
        
        # 新增模型
        st.subheader("添加初始模型")
        models_input = st.text_area(
            "模型列表",
            help="输入模型名称，每行一个",
            height=100
        )
        
        # 价格信息
        col1, col2 = st.columns(2)
        with col1:
            price_input = st.number_input(
                "输入价格 (每1000 tokens)",
                min_value=0.0,
                value=0.001,
                step=0.0001,
                format="%.6f",
                help="每1000个输入tokens的价格（美元）"
            )
        
        with col2:
            price_output = st.number_input(
                "输出价格 (每1000 tokens)",
                min_value=0.0,
                value=0.002,
                step=0.0001,
                format="%.6f",
                help="每1000个输出tokens的价格（美元）"
            )
        
        # 高级选项
        with st.expander("高级选项"):
            # 请求头
            st.subheader("请求头")
            
            # 默认请求头
            default_headers = {
                "Content-Type": "application/json",
                "Authorization": "Bearer {api_key}"
            }
            
            headers_json = st.text_area(
                "请求头 (JSON格式)",
                value=json.dumps(default_headers, indent=2),
                height=150,
                help="输入请求头，使用JSON格式。使用{api_key}作为API密钥的占位符。"
            )
            
            # API端点
            st.subheader("API端点")
            
            chat_endpoint = st.text_input(
                "聊天完成端点",
                value="/chat/completions",
                help="聊天完成API端点，例如: /chat/completions"
            )
            
            # 参数映射
            st.subheader("参数映射")
            
            # 默认参数映射
            default_mapping = {
                "model": "model",
                "messages": "messages",
                "temperature": "temperature",
                "max_tokens": "max_tokens",
                "top_p": "top_p"
            }
            
            mapping_json = st.text_area(
                "参数映射 (JSON格式)",
                value=json.dumps(default_mapping, indent=2),
                height=150,
                help="输入参数映射，使用JSON格式。键为标准参数名，值为提供商参数名。"
            )
        
        submit_button = st.form_submit_button("添加提供商")
        
        if submit_button:
            if not provider_name or not display_name:
                st.error("提供商标识和显示名称不能为空")
                return
            
            # 解析模型列表
            models = []
            if models_input:
                models = [model.strip() for model in models_input.strip().split("\n") if model.strip()]
            
            # 解析请求头和参数映射
            try:
                headers = json.loads(headers_json)
            except json.JSONDecodeError:
                st.error("请求头JSON格式错误")
                return
            
            try:
                params_mapping = json.loads(mapping_json)
            except json.JSONDecodeError:
                st.error("参数映射JSON格式错误")
                return
            
            # 创建提供商配置
            provider_config = {
                "name": provider_name,
                "display_name": display_name,
                "api_key": api_key,
                "base_url": base_url,
                "api_type": api_type,
                "message_format": message_format,
                "models": models,
                "price_input": price_input,
                "price_output": price_output,
                "headers": headers,
                "endpoints": {
                    "chat": chat_endpoint
                },
                "params_mapping": params_mapping
            }
            
            # 添加提供商
            add_custom_provider(provider_config)
            st.success(f"已添加提供商: {display_name}")
            st.experimental_rerun()
