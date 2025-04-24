import streamlit as st
import json
import pandas as pd
from typing import Dict, List, Optional, Any
from config import (
    get_provider_list, load_provider_config, add_custom_provider, 
    remove_custom_provider, update_api_key, add_model_to_provider,
    remove_model_from_provider, DEFAULT_PROVIDER_CONFIG, load_config, get_api_key,
    get_available_models, save_config
)
from models.api_clients import get_provider_from_model, get_client

def render_provider_manager():
    st.title("🔑 API密钥与提供商管理")
    
    st.markdown("""
    <div style="background-color: #f8f9fa; padding: 20px; border-radius: 10px; margin-bottom: 20px;">
    <h3 style="color: #4b778d;">在这里管理您的模型提供商和API密钥</h3>
    <p>设置API密钥、基础URL、支持的模型等信息，以便在测试和优化过程中使用这些提供商的模型。</p>
    </div>
    """, unsafe_allow_html=True)

    st.info("""
    🔒 API密钥将安全地存储在本地配置文件中，不会被发送到任何外部服务。
    """)
    
    # 获取提供商列表
    provider_list = get_provider_list()
    
    # 创建选项卡，使用emoji美化选项卡标题
    tab1, tab2, tab3 = st.tabs(["🔧 提供商管理", "➕ 添加新提供商", "🧪 评估模型测试"])
    
    with tab1:
        if not provider_list:
            st.info("暂无提供商，请先添加提供商")
        else:
            # 创建提供商选择器，添加样式
            st.markdown('<div style="margin-bottom: 12px; font-weight: 500;">选择提供商</div>', unsafe_allow_html=True)
            selected_provider = st.selectbox(
                "",
                provider_list,
                key="provider_selector",
                help="选择要管理的模型提供商"
            )
            
            if selected_provider:
                display_provider_details(selected_provider)
    
    with tab2:
        create_new_provider()
        
    with tab3:
        test_evaluator_model()

def display_provider_details(provider_name: str):
    """显示提供商详细信息"""
    # 加载提供商配置
    provider_config = load_provider_config(provider_name)
    config = load_config()
    
    # 显示提供商基本信息
    st.subheader(f"提供商: {provider_config.get('display_name', provider_name)}")
    
    # 提供商类型
    is_custom = provider_name in config.get("custom_providers", [])
    provider_type = "自定义提供商" if is_custom else "内置提供商"
    st.markdown(f"**类型**: {provider_type}")
    
    # 获取API密钥
    api_key = get_api_key(provider_name)
    new_api_key = st.text_input(
        "API密钥",
        value=api_key if api_key else "",
        type="password",
        help="输入您的API密钥"
    )
    
    col1, col2 = st.columns([1, 3])
    with col1:
        if st.button("保存API密钥", key=f"save_key_{provider_name}"):
            update_api_key(provider_name, new_api_key)
            st.success(f"{provider_name} API密钥已保存")
    
    with col2:
        if st.button("测试API密钥", key=f"test_key_{provider_name}"):
            if not new_api_key:
                st.error(f"{provider_name} API密钥未设置")
            else:
                # 保存API密钥后再测试
                update_api_key(provider_name, new_api_key)
                test_api_key(provider_name)
    
    # 价格信息
    if not is_custom:
        display_pricing_info(provider_name)
    
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
            
            # Azure 特殊处理
            if provider_name == "azure":
                st.subheader("Azure OpenAI配置")
                
                # 基础URL (Azure终端点)
                base_url = provider_config.get("base_url", "")
                new_base_url = st.text_input(
                    "Azure终端点",
                    value=base_url,
                    help="输入Azure OpenAI资源的终端点URL，例如: https://your-resource-name.openai.azure.com",
                    key="azure_base_url"
                )
                if base_url != new_base_url:
                    provider_config["base_url"] = new_base_url
                    add_custom_provider(provider_config)
                
                # API版本
                api_version = provider_config.get("api_version", "2023-05-15")
                new_api_version = st.text_input(
                    "API版本",
                    value=api_version,
                    help="Azure OpenAI API版本，例如: 2023-05-15",
                    key="azure_api_version"
                )
                if api_version != new_api_version:
                    provider_config["api_version"] = new_api_version
                    add_custom_provider(provider_config)
            
            # 价格信息
            st.subheader("价格信息")
            col1, col2 = st.columns(2)
            with col1:
                price_input = st.number_input(
                    "输入价格 (每1000 tokens)",
                    min_value=0.0,
                    value=provider_config.get("price_input", 0.001),
                    step=0.0001,
                    format="%.6f",
                    help="每1000个输入tokens的价格（美元）"
                )
                if price_input != provider_config.get("price_input", 0.0):
                    provider_config["price_input"] = price_input
                    add_custom_provider(provider_config)
            
            with col2:
                price_output = st.number_input(
                    "输出价格 (每1000 tokens)",
                    min_value=0.0,
                    value=provider_config.get("price_output", 0.002),
                    step=0.0001,
                    format="%.6f",
                    help="每1000个输出tokens的价格（美元）"
                )
                if price_output != provider_config.get("price_output", 0.0):
                    provider_config["price_output"] = price_output
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
                st.rerun()
    
    # 模型管理
    st.subheader("模型管理")
    
    # 显示现有模型
    models = []
    if is_custom:
        models = provider_config.get("models", [])
    else:
        config = load_config()
        models = config["models"].get(provider_name, [])
    
    if not models:
        st.info("暂无模型，请添加模型")
    else:
        st.write("当前支持的模型:")
        
        for i, model in enumerate(models):
            col1, col2, col3 = st.columns([3, 1, 1])
            
            with col1:
                st.write(f"- {model}")
            
            with col2:
                if st.button("测试", key=f"test_model_{i}", help=f"测试模型 {model} 是否可用"):
                    test_model(provider_name, model)
            
            with col3:
                if st.button("移除", key=f"remove_model_{i}", help=f"从提供商移除模型 {model}"):
                    remove_model_from_provider(provider_name, model)
                    st.success(f"已移除模型: {model}")
                    st.rerun()
    
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
            st.rerun()

def display_pricing_info(provider_name: str):
    """显示内置提供商的价格信息"""
    if provider_name == "openai":
        st.markdown("""
        ### 价格参考
        - GPT-3.5 Turbo: $0.0005 / 1K tokens (输入), $0.0015 / 1K tokens (输出)
        - GPT-4: $0.03 / 1K tokens (输入), $0.06 / 1K tokens (输出)
        - GPT-4o: $0.01 / 1K tokens (输入), $0.03 / 1K tokens (输出)
        
        ### 获取方式
        1. 访问 [OpenAI API Dashboard](https://platform.openai.com/api-keys)
        2. 登录您的账户
        3. 创建新的API密钥
        """)
    elif provider_name == "anthropic":
        st.markdown("""
        ### 价格参考
        - Claude 3 Haiku: $0.00025 / 1K tokens (输入), $0.00125 / 1K tokens (输出)
        - Claude 3 Sonnet: $0.003 / 1K tokens (输入), $0.015 / 1K tokens (输出)
        - Claude 3 Opus: $0.015 / 1K tokens (输入), $0.075 / 1K tokens (输出)
        
        ### 获取方式
        1. 访问 [Anthropic Console](https://console.anthropic.com/)
        2. 登录您的账户
        3. 创建新的API密钥
        """)
    elif provider_name == "google":
        st.markdown("""
        ### 价格参考
        - Gemini 1.0 Pro: $0.0025 / 1K tokens (输入+输出)
        - Gemini 1.5 Pro: $0.0025 / 1K tokens (输入+输出)
        
        ### 获取方式
        1. 访问 [Google AI Studio](https://makersuite.google.com/app/apikey)
        2. 登录您的账户
        3. 创建新的API密钥
        """)
    elif provider_name == "xai":
        st.markdown("""
        ### 价格参考
        - Grok-3: 价格暂未公布
        
        ### 获取方式
        1. 访问 [X.AI](https://x.ai/)
        2. 获取API访问权限
        """)
    elif provider_name == "azure":
        st.markdown("""
        ### 价格参考
        - GPT-4o: 价格取决于您的Azure订阅，通常与OpenAI价格相近
          - 标准价格: $0.01 / 1K tokens (输入), $0.03 / 1K tokens (输出)
        
        ### 配置方式
        1. 访问 [Azure Portal](https://portal.azure.com/)
        2. 创建或选择您的Azure OpenAI资源
        3. 获取以下信息:
           - API密钥 (在"密钥和终结点"下)
           - 终结点 URL (例如: https://your-resource-name.openai.azure.com)
           - 部署名称 (您为模型部署指定的名称)
        
        ### 注意事项
        - 对于Azure，需要在"提供商高级配置"中设置正确的API基础URL
        - 您也可以添加模型部署ID (例如: gpt-4o)
        """)

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
            st.rerun()

def test_api_key(provider_name: str):
    """测试API密钥是否有效"""
    try:
        # 获取提供商的一个模型进行测试
        config = load_config()
        models = []
        
        if provider_name in config["models"]:
            models = config["models"][provider_name]
        else:
            provider_config = load_provider_config(provider_name)
            models = provider_config.get("models", [])
        
        if not models:
            st.warning(f"提供商 {provider_name} 没有可用的模型，请先添加模型")
            return
        
        # 获取API客户端
        try:
            client = get_client(provider_name)
        except Exception as e:
            st.error(f"获取API客户端失败: {str(e)}")
            return
        
        # 使用第一个模型进行测试
        test_model = models[0]
        
        # 消息格式
        messages = [
            {"role": "user", "content": "测试消息，请回复 '你好，我正常工作'"}
        ]
        
        # 执行测试
        with st.spinner(f"正在测试 {provider_name} API密钥..."):
            result = client.generate_with_messages_sync(
                messages,
                test_model,
                {"max_tokens": 20, "temperature": 0.1}
            )
        
        if "error" in result:
            st.error(f"API密钥测试失败: {result['error']}")
        else:
            st.success(f"API密钥有效，成功连接到 {provider_name} 服务")
            st.write(f"测试模型: {test_model}")
            st.write(f"模型响应: {result['text']}")
    
    except Exception as e:
        st.error(f"测试过程中发生错误: {str(e)}")

def test_model(provider_name: str, model: str):
    """测试指定模型是否可用"""
    try:
        # 获取API客户端
        try:
            client = get_client(provider_name)
        except Exception as e:
            st.error(f"获取API客户端失败: {str(e)}")
            return
        
        # 消息格式
        messages = [
            {"role": "user", "content": "测试消息，请回复 '你好，我正常工作'"}
        ]
        
        # 执行测试
        with st.spinner(f"正在测试模型 {model}..."):
            result = client.generate_with_messages_sync(
                messages,
                model,
                {"max_tokens": 20, "temperature": 0.1}
            )
        
        if "error" in result:
            st.error(f"模型测试失败: {result['error']}")
        else:
            st.success(f"模型 {model} 测试成功")
            st.write(f"模型响应: {result['text']}")
    
    except Exception as e:
        st.error(f"测试过程中发生错误: {str(e)}")

def test_evaluator_model():
    """测试评估模型功能"""
    st.subheader("评估模型设置与测试")

    # 获取当前配置的评估模型
    config = load_config()
    available_models = get_available_models()
    current_evaluator = config.get("evaluator_model", "gpt-4")
    
    # 创建两列布局
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("评估模型选择")
        
        # 创建所有可用模型的列表
        eval_model_options = []
        for provider, models in available_models.items():
            for model in models:
                eval_model_options.append(f"{model} ({provider})")
        
        # 查找当前评估模型的索引
        current_index = 0
        for i, model_str in enumerate(eval_model_options):
            if model_str.startswith(current_evaluator + " "):
                current_index = i
                break
        
        selected_evaluator_str = st.selectbox(
            "选择评估模型",
            eval_model_options,
            index=current_index if current_index < len(eval_model_options) else 0,
            help="用于评估测试结果的模型"
        )
        
        # 从显示字符串中提取模型名称
        if selected_evaluator_str:
            selected_evaluator = selected_evaluator_str.split(" (")[0]
            new_provider = selected_evaluator_str.split(" (")[1].rstrip(")")
            
            # 添加本地评估的选项
            use_local = config.get("use_local_evaluation", False)
            new_use_local = st.checkbox(
                "使用本地评估（不调用API）", 
                value=use_local,
                help="选中此项将使用本地评估方法，而不调用评估模型API。本地评估使用基于文本相似度的简单算法。"
            )
            
            # 保存按钮
            if st.button("保存评估模型设置"):
                config["evaluator_model"] = selected_evaluator
                config["use_local_evaluation"] = new_use_local
                save_config(config)
                st.success(f"评估模型已更新为: {selected_evaluator}")
                if new_use_local != use_local:
                    st.success(f"本地评估设置已更新为: {'启用' if new_use_local else '禁用'}")
        
    with col2:
        st.subheader("当前评估模型信息")
        provider = get_provider_from_model(current_evaluator)
        api_key = get_api_key(provider)
        
        st.write(f"当前评估模型: **{current_evaluator}**")
        st.write(f"提供商: **{provider}**")
        st.write(f"API密钥状态: **{'已配置 ✅' if api_key else '未配置 ❌'}**")
        st.write(f"本地评估: **{'启用 ✅' if config.get("use_local_evaluation", False) else '禁用 ❌'}**")
    
    # 分割线
    st.divider()
    
    st.subheader("评估模型测试")
    st.write("测试当前评估模型是否能正确处理评估请求")
    
    col1, col2 = st.columns(2)
    
    with col1:
        # 测试参数设置
        test_response = st.text_area(
            "测试响应",
            value="这是一个测试响应，用于验证评估模型是否正常工作。",
            height=100,
            help="输入要评估的测试响应"
        )
    
    with col2:
        test_expected = st.text_area(
            "期望输出",
            value="这是期望的输出，用于验证评估模型是否正常工作。",
            height=100,
            help="输入期望的输出结果"
        )
    
    # 评估标准 - 可展开的高级选项
    with st.expander("高级选项 - 自定义评估标准"):
        criteria_col1, criteria_col2 = st.columns(2)
        
        with criteria_col1:
            accuracy_criteria = st.text_input(
                "准确性标准",
                value="评估响应与期望输出的匹配程度",
                help="输入评估准确性的标准"
            )
            
            completeness_criteria = st.text_input(
                "完整性标准",
                value="评估响应是否包含所有必要信息",
                help="输入评估完整性的标准"
            )
        
        with criteria_col2:
            relevance_criteria = st.text_input(
                "相关性标准",
                value="评估响应与提示词的相关性",
                help="输入评估相关性的标准"
            )
            
            clarity_criteria = st.text_input(
                "清晰度标准",
                value="评估响应的清晰度和可理解性",
                help="输入评估清晰度的标准"
            )

    if st.button("运行测试", type="primary"):
        provider = get_provider_from_model(current_evaluator)
        api_key = get_api_key(provider)
        
        if not api_key and not config.get("use_local_evaluation", False):
            st.error(f"评估模型 {current_evaluator} 的API密钥未设置，请先配置API密钥或启用本地评估")
        else:
            with st.spinner("正在测试评估模型..."):
                # 构建测试标准
                test_criteria = {
                    "accuracy": accuracy_criteria,
                    "completeness": completeness_criteria,
                    "relevance": relevance_criteria,
                    "clarity": clarity_criteria
                }
                
                # 创建评估器并执行测试
                from utils.evaluator import PromptEvaluator
                evaluator = PromptEvaluator()
                result = evaluator.evaluate_response_sync(
                    test_response,
                    test_expected,
                    test_criteria,
                    "测试提示词"
                )
                
                # 显示测试结果
                if "error" in result:
                    st.error(f"评估模型测试失败: {result['error']}")
                    if "raw_response" in result:
                        st.text_area("原始响应", value=result['raw_response'], height=200)
                else:
                    st.success("评估模型测试成功")
                    
                    # 以更美观的方式显示评估结果
                    st.write("### 评估结果")
                    
                    # 评分显示
                    if "scores" in result:
                        scores = result["scores"]
                        st.write("#### 评分")
                        score_cols = st.columns(4)
                        
                        with score_cols[0]:
                            st.metric("准确性", f"{scores.get('accuracy', 0)}分")
                        
                        with score_cols[1]:
                            st.metric("完整性", f"{scores.get('completeness', 0)}分")
                        
                        with score_cols[2]:
                            st.metric("相关性", f"{scores.get('relevance', 0)}分")
                        
                        with score_cols[3]:
                            st.metric("清晰度", f"{scores.get('clarity', 0)}分")
                        
                        # 总体评分
                        st.metric("总体评分", f"{result.get('overall_score', 0)}分")
                    
                    # 分析
                    if "analysis" in result:
                        st.write("#### 分析")
                        st.write(result["analysis"])
                    
                    # 详细信息
                    with st.expander("查看完整JSON结果"):
                        st.json(result)
                    
                    # 保存评估结果到会话状态，用于测试用例生成
                    st.session_state.last_evaluation_result = result
                    st.session_state.last_test_response = test_response
                    st.session_state.last_test_expected = test_expected
                    st.session_state.last_test_criteria = test_criteria

    # 分割线
    st.divider()
    
    # 新增：测试用例自动生成功能
    st.subheader("🔄 自动生成测试用例")
    st.write("使用评估模型自动生成新的测试用例，适用于测试其他模型")
    
    # 检查是否已经有评估结果可用
    has_evaluation = "last_evaluation_result" in st.session_state
    
    if not has_evaluation:
        st.info("请先运行上方的评估测试，然后再使用此功能")
    else:
        # 显示最近的测试响应和期望输出
        with st.expander("查看上次测试内容", expanded=False):
            st.write("**测试响应:**")
            st.write(st.session_state.last_test_response)
            st.write("**期望输出:**")
            st.write(st.session_state.last_test_expected)
            st.write("**评估结果:**")
            st.metric("总体评分", f"{st.session_state.last_evaluation_result.get('overall_score', 0)}分")
        
        col1, col2 = st.columns(2)
        
        with col1:
            test_model = st.text_input(
                "目标测试模型",
                value="gpt-4",
                help="输入要为其生成测试用例的模型名称"
            )
        
        with col2:
            test_purpose = st.text_input(
                "测试目的",
                value="测试模型在理解和回答用户问题方面的能力",
                help="测试的目的或关注点，例如：评估语法准确性、测试上下文理解、检验数学问题解决能力等"
            )
        
        # 选择测试集
        test_set_options = get_test_set_list()
        selected_test_set = st.selectbox(
            "选择目标测试集（将添加生成的测试用例）",
            options=test_set_options,
            help="选择要将生成的测试用例添加到哪个测试集中"
        )
        
        if st.button("生成测试用例", type="primary"):
            if not selected_test_set:
                st.error("请选择一个测试集")
                return
                
            provider = get_provider_from_model(current_evaluator)
            api_key = get_api_key(provider)
            
            if not api_key:
                st.error(f"评估模型 {current_evaluator} 的API密钥未设置，无法生成测试用例")
                return
                
            with st.spinner("AI正在生成测试用例..."):
                # 准备示例测试用例
                example_case = {
                    "id": f"test_{int(time.time())}",
                    "description": "示例测试用例",
                    "user_input": st.session_state.last_test_response,
                    "expected_output": st.session_state.last_test_expected,
                    "evaluation": st.session_state.last_evaluation_result
                }
                
                # 创建评估器并执行测试用例生成
                from utils.evaluator import PromptEvaluator
                evaluator = PromptEvaluator()
                result = evaluator.generate_test_cases(
                    test_model,
                    test_purpose,
                    example_case
                )
                
                if "error" in result:
                    st.error(f"测试用例生成失败: {result['error']}")
                    if "raw_response" in result:
                        st.text_area("原始响应", value=result['raw_response'], height=200)
                else:
                    # 加载选择的测试集
                    test_set = load_test_set(selected_test_set)
                    
                    # 添加生成的测试用例
                    test_cases = result.get("test_cases", [])
                    added_count = 0
                    
                    if test_cases:
                        for tc in test_cases:
                            # 生成唯一ID
                            if "id" not in tc or not tc["id"]:
                                tc["id"] = f"gen_{int(time.time())}_{added_count}"
                            
                            # 添加到测试集
                            test_set["cases"].append(tc)
                            added_count += 1
                        
                        # 保存更新的测试集
                        save_test_set(selected_test_set, test_set)
                        
                        st.success(f"成功生成并添加 {added_count} 个测试用例到测试集 '{selected_test_set}'")
                        
                        # 显示生成的测试用例
                        st.write("### 生成的测试用例")
                        for i, tc in enumerate(test_cases):
                            with st.expander(f"测试用例 {i+1}: {tc.get('description', '')}", expanded=i==0):
                                st.write(f"**ID:** {tc.get('id', '')}")
                                st.write(f"**描述:** {tc.get('description', '')}")
                                
                                st.write("**用户输入:**")
                                st.code(tc.get("user_input", ""))
                                
                                st.write("**期望输出:**")
                                st.code(tc.get("expected_output", ""))
                                
                                st.write("**评估标准:**")
                                criteria = tc.get("evaluation_criteria", {})
                                for criterion, description in criteria.items():
                                    st.write(f"- **{criterion}:** {description}")
                    else:
                        st.warning("没有生成任何测试用例，请检查评估模型的响应")
                        if "raw_response" in result:
                            st.text_area("原始响应", value=result['raw_response'], height=200)
                        else:
                            st.json(result)
