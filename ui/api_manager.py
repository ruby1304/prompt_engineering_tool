# ui/api_manager.py
import streamlit as st
from config import get_api_key, update_api_key, load_config
from models.api_clients import get_provider_from_model
from ui.components.layout import page_header, tabs_section
from ui.components.cards import info_card
from ui.components.forms import api_key_form

def render_api_manager():
    """API密钥管理页面"""
    # 使用布局组件显示页面标题
    page_header(
        "API密钥管理", 
        "管理您的AI模型提供商API密钥，安全地存储在本地配置文件中", 
        "🔑"
    )
    
    # 显示安全提示
    info_card(
        "安全提示", 
        """
        您的API密钥将安全地存储在本地配置文件中。这些密钥不会被发送到任何外部服务。
        请确保不要将包含API密钥的配置文件分享给他人。
        """
    )
    
    # 定义各提供商标签页的渲染函数
    def render_openai_tab():
        openai_key = get_api_key("openai")
        
        # 使用API密钥表单组件
        def on_save_openai(api_key):
            update_api_key("openai", api_key)
            st.success("OpenAI API密钥已保存")
        
        api_key_form(
            "OpenAI API密钥", 
            openai_key, 
            on_save_openai, 
            "openai",
            help_text="输入您的OpenAI API密钥，用于访问GPT-3.5, GPT-4等模型"
        )
        
        st.markdown("""
        ### 获取方式
        1. 访问 [OpenAI API Dashboard](https://platform.openai.com/api-keys)
        2. 登录您的账户
        3. 创建新的API密钥
        
        ### 价格参考
        - GPT-3.5 Turbo: $0.0005 / 1K tokens (输入), $0.0015 / 1K tokens (输出)
        - GPT-4: $0.03 / 1K tokens (输入), $0.06 / 1K tokens (输出)
        - GPT-4 Turbo: $0.01 / 1K tokens (输入), $0.03 / 1K tokens (输出)
        """)
    
    def render_anthropic_tab():
        anthropic_key = get_api_key("anthropic")
        
        def on_save_anthropic(api_key):
            update_api_key("anthropic", api_key)
            st.success("Anthropic API密钥已保存")
        
        api_key_form(
            "Anthropic API密钥", 
            anthropic_key, 
            on_save_anthropic, 
            "anthropic",
            help_text="输入您的Anthropic API密钥，用于访问Claude系列模型"
        )
        
        st.markdown("""
        ### 获取方式
        1. 访问 [Anthropic Console](https://console.anthropic.com/)
        2. 登录您的账户
        3. 在API Keys部分创建新的API密钥
        
        ### 价格参考
        - Claude 3 Haiku: $0.25 / 1M tokens (输入), $1.25 / 1M tokens (输出)
        - Claude 3 Sonnet: $3 / 1M tokens (输入), $15 / 1M tokens (输出)
        - Claude 3 Opus: $15 / 1M tokens (输入), $75 / 1M tokens (输出)
        """)
    
    def render_google_tab():
        google_key = get_api_key("google")
        
        def on_save_google(api_key):
            update_api_key("google", api_key)
            st.success("Google API密钥已保存")
        
        api_key_form(
            "Google AI API密钥", 
            google_key, 
            on_save_google, 
            "google",
            help_text="输入您的Google AI API密钥，用于访问Gemini系列模型"
        )
        
        st.markdown("""
        ### 获取方式
        1. 访问 [Google AI Studio](https://makersuite.google.com/app/apikey)
        2. 登录您的Google账户
        3. 创建新的API密钥
        
        ### 价格参考
        - Gemini Pro: $0.0005 / 1K tokens (输入), $0.0015 / 1K tokens (输出)
        - Gemini Flash: $0.00035 / 1K tokens (输入), $0.00105 / 1K tokens (输出)
        """)
    
    def render_xai_tab():
        xai_key = get_api_key("xai")
        
        def on_save_xai(api_key):
            update_api_key("xai", api_key)
            st.success("xAI API密钥已保存")
        
        api_key_form(
            "xAI API密钥", 
            xai_key, 
            on_save_xai, 
            "xai",
            help_text="输入您的xAI API密钥，用于访问Grok系列模型"
        )
        
        st.markdown("""
        ### 获取方式
        1. 访问 [xAI开发者平台](https://x.ai/)
        2. 登录您的账户
        3. 创建新的API密钥
        
        ### 价格参考
        - Grok-1: $0.0005 / 1K tokens (输入), $0.0015 / 1K tokens (输出)
        """)
    
    # 使用选项卡组件显示不同提供商的API管理
    tabs_config = [
        {"title": "OpenAI", "content": render_openai_tab},
        {"title": "Anthropic", "content": render_anthropic_tab},
        {"title": "Google", "content": render_google_tab},
        {"title": "xAI", "content": render_xai_tab}
    ]
    
    tabs_section(tabs_config)
