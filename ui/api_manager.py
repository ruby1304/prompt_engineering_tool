import streamlit as st
# 修改导入方式
from config import get_api_key, update_api_key, load_config
from models.api_clients import get_provider_from_model

def render_api_manager():
    st.title("🔑 API密钥管理")
    
    st.info("""
    在这里管理您的LLM API密钥。这些密钥将安全地存储在本地配置文件中。
    您的API密钥不会被发送到任何外部服务。
    """)
    
    tab1, tab2, tab3, tab4 = st.tabs(["OpenAI", "Anthropic", "Google", "XAi"])
    
    with tab1:
        openai_key = get_api_key("openai")
        new_openai_key = st.text_input(
            "OpenAI API密钥",
            value=openai_key,
            type="password",
            help="输入您的OpenAI API密钥，用于访问GPT-3.5, GPT-4等模型"
        )
        
        if st.button("保存OpenAI密钥", key="save_openai"):
            update_api_key("openai", new_openai_key)
            st.success("OpenAI API密钥已保存")
        
        st.markdown("""
        ### 获取方式
        1. 访问 [OpenAI API Dashboard](https://platform.openai.com/api-keys)
        2. 登录您的账户
        3. 创建新的API密钥
        
        ### 价格参考
        - GPT-3.5 Turbo: $0.0005 / 1K tokens (输入), $0.0015 / 1K tokens (输出)
        - GPT-4: $0.03 / 1K tokens (输入), $0.06 / 1K tokens (输出)
        - GPT-4o: $0.01 / 1K tokens (输入), $0.03 / 1K tokens (输出)
        """)
    
    with tab2:
        anthropic_key = get_api_key("anthropic")
        new_anthropic_key = st.text_input(
            "Anthropic API密钥",
            value=anthropic_key,
            type="password",
            help="输入您的Anthropic API密钥，用于访问Claude系列模型"
        )
        
        if st.button("保存Anthropic密钥", key="save_anthropic"):
            update_api_key("anthropic", new_anthropic_key)
            st.success("Anthropic API密钥已保存")
        
        st.markdown("""
        ### 获取方式
        1. 访问 [Anthropic Console](https://console.anthropic.com/)
        2. 登录您的账户
        3. 创建新的API密钥
        
        ### 价格参考
        - Claude 3 Haiku: $0.00025 / 1K tokens (输入), $0.00125 / 1K tokens (输出)
        - Claude 3 Sonnet: $0.003 / 1K tokens (输入), $0.015 / 1K tokens (输出)
        - Claude 3 Opus: $0.015 / 1K tokens (输入), $0.075 / 1K tokens (输出)
        """)
    
    with tab3:
        google_key = get_api_key("google")
        new_google_key = st.text_input(
            "Google AI Studio API密钥",
            value=google_key,
            type="password",
            help="输入您的Google AI Studio API密钥，用于访问Gemini系列模型"
        )
        
        if st.button("保存Google密钥", key="save_google"):
            update_api_key("google", new_google_key)
            st.success("Google API密钥已保存")
        
        st.markdown("""
        ### 获取方式
        1. 访问 [Google AI Studio](https://makersuite.google.com/app/apikey)
        2. 登录您的账户
        3. 创建新的API密钥
        
        ### 价格参考
        - Gemini 1.0 Pro: $0.0025 / 1K tokens (输入+输出)
        - Gemini 1.5 Pro: $0.0025 / 1K tokens (输入+输出)
        """)

    with tab4:
        xai_key = get_api_key("xai")
        new_xai_key = st.text_input(
            "XAi API密钥",
            value=xai_key,
            type="password",
            help="输入您的XAi API密钥，用于访问Grok-3模型"
        )
        
        if st.button("保存XAi密钥", key="save_xai"):
            update_api_key("xai", new_xai_key)
            st.success("XAi API密钥已保存")
        
        st.markdown("""
        ### 获取方式
        """)    
    st.divider()
    
    st.subheader("验证API密钥")
    
    if st.button("测试所有API密钥"):
        # 在实际应用中，这里会有一个简单的API调用来验证密钥是否有效
        st.info("正在测试API密钥...")
        # 这里为简化示例，仅检查密钥是否存在
        results = []
        
        openai_key = get_api_key("openai")
        if openai_key:
            results.append("✅ OpenAI API密钥已设置")
        else:
            results.append("❌ OpenAI API密钥未设置")
        
        anthropic_key = get_api_key("anthropic")
        if anthropic_key:
            results.append("✅ Anthropic API密钥已设置")
        else:
            results.append("❌ Anthropic API密钥未设置")
        
        google_key = get_api_key("google")
        if google_key:
            results.append("✅ Google API密钥已设置")
        else:
            results.append("❌ Google API密钥未设置")
        
        xai_key = get_api_key("xai")
        if xai_key:
            results.append("✅ XAi API密钥已设置")
        else:
            results.append("❌ XAi API密钥未设置")
        for result in results:
            st.write(result)

    st.divider()
    st.subheader("测试评估模型")

    # 获取当前配置的评估模型
    config = load_config()
    current_evaluator = config.get("evaluator_model", "gpt-4")
    provider = get_provider_from_model(current_evaluator)
    api_key = get_api_key(provider)

    st.write(f"当前评估模型: **{current_evaluator}**")
    st.write(f"提供商: **{provider}**")
    st.write(f"API密钥状态: **{'已配置' if api_key else '未配置'}**")

    if st.button("测试评估模型"):
        if not api_key:
            st.error(f"评估模型 {current_evaluator} 的API密钥未设置，请先配置API密钥")
        else:
            with st.spinner("正在测试评估模型..."):
                # 简单的测试用例
                test_response = "这是一个测试响应，用于验证评估模型是否正常工作。"
                test_expected = "这是期望的输出，用于验证评估模型是否正常工作。"
                test_criteria = {
                    "accuracy": "评估响应与期望输出的匹配程度",
                    "completeness": "评估响应是否包含所有必要信息"
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
                    st.json(result)