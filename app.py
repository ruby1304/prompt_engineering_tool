import streamlit as st
import os
import json
from pathlib import Path
import asyncio
import pandas as pd
import time

from config import load_config, update_api_key, get_api_key, initialize_system_templates
from models.token_counter import count_tokens, estimate_cost
from utils.evaluator import PromptEvaluator
from utils.optimizer import PromptOptimizer
from utils.visualizer import (
    create_score_comparison_chart, 
    create_token_comparison_chart,
    create_radar_chart,
    generate_report,
    display_report
)

# 初始化系统提示词模板
initialize_system_templates()

from ui.model_selector import render_model_selector
from ui.prompt_editor import render_prompt_editor
from ui.test_manager import render_test_manager
from ui.test_runner import render_test_runner
from ui.results_viewer import render_results_viewer
from ui.prompt_optimization import render_prompt_optimization
from ui.prompt_ab_test import render_prompt_ab_test
from ui.prompt_batch_ab_test import render_prompt_batch_ab_test
from ui.provider_manager import render_provider_manager
from ui.prompt_interactive_test import render_prompt_interactive_test
from ui.prompt_dialogue_test import render_prompt_dialogue_test
from ui.prompt_auto_optimization import render_prompt_auto_optimization


# 设置页面配置
st.set_page_config(
    page_title="提示词调优工程工具",
    page_icon="🧪",
    layout="wide",
    initial_sidebar_state="expanded"
)

# 初始化会话状态
if "page" not in st.session_state:
    st.session_state.page = "home"
if "current_prompt_template" not in st.session_state:
    st.session_state.current_prompt_template = None
if "current_test_set" not in st.session_state:
    st.session_state.current_test_set = None
if "test_results" not in st.session_state:
    st.session_state.test_results = {}
if "optimized_prompts" not in st.session_state:
    st.session_state.optimized_prompts = []

def navigate_to(page):
    st.session_state.page = page

# 侧边栏导航
with st.sidebar:
    st.title("🧪 提示词调优工具")
    
    st.subheader("导航")
    
    if st.button("🏠 首页", use_container_width=True):
        navigate_to("home")
    
    if st.button("🔑 API密钥与提供商管理", use_container_width=True):
        navigate_to("provider_manager")

    if st.button("📝 提示词编辑器", use_container_width=True):
        navigate_to("prompt_editor")
    
    if st.button("📊 测试集管理", use_container_width=True):
        navigate_to("test_manager")
    
    if st.button("🧪 测试运行", use_container_width=True):
        navigate_to("test_runner")
    
    if st.button("💬 交互式测试", use_container_width=True):
        navigate_to("prompt_interactive_test")
        
    if st.button("🗣️ 多轮对话测试", use_container_width=True):
        navigate_to("prompt_dialogue_test")
        
    if st.button("📈 结果查看", use_container_width=True):
        navigate_to("results_viewer")

    if st.button("🔍 提示词专项优化", use_container_width=True):
        navigate_to("prompt_optimization")
    
    if st.button("🤖 自动提示词优化", use_container_width=True):
        navigate_to("prompt_auto_optimization")
    
    if st.button("🔬 提示词A/B测试", use_container_width=True):
        navigate_to("prompt_ab_test")

    st.divider()
    st.caption("© 2025 提示词调优工程工具 v1.0")

# 主页内容
if st.session_state.page == "home":
    st.title("欢迎使用提示词调优工程工具")
    
    st.markdown("""
    这是一个专为提示词工程师设计的工具，帮助您系统化地测试和优化提示词效果。
    
    ### 使用流程
    
    1. **API密钥设置** - 在API密钥与提供商管理页面设置您的API密钥和模型提供商
    2. **创建提示词** - 在提示词编辑器中创建和编辑提示词模板
    3. **准备测试集** - 在测试集管理页面创建测试用例
    4. **运行测试** - 在测试运行页面执行提示词测试
    5. **分析结果** - 在结果查看页面分析测试结果
    
    ### 核心功能
    
    - 支持多种LLM模型的测试
    - 变量化的提示词模板
    - 可自定义评估标准
    - 提示词自动优化
    - 详细的结果分析和可视化
    
    开始使用吧！点击左侧的导航栏开始您的提示词调优之旅。
    """)
    
    # 显示快速启动卡片
    st.subheader("快速启动")
    
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.info("### 📝 创建提示词")
        st.markdown("创建和编辑提示词模板，支持变量和条件")
        if st.button("开始创建", key="start_prompt"):
            navigate_to("prompt_editor")
    
    with col2:
        st.info("### 📊 管理测试集")
        st.markdown("创建和编辑测试用例，定义评估标准")
        if st.button("管理测试集", key="manage_test"):
            navigate_to("test_manager")
    
    with col3:
        st.info("### 💬 交互式测试")
        st.markdown("选择模板和模型，输入内容并获取回复，手动评分")
        if st.button("交互式测试", key="start_interactive"):
            navigate_to("prompt_interactive_test")
            
    with col4:
        st.info("### 🤖 自动优化")
        st.markdown("使用AI自动生成测试、评估结果并持续迭代改进提示词")
        if st.button("自动优化", key="start_auto"):
            navigate_to("prompt_auto_optimization")

# 渲染其他页面
elif st.session_state.page == "prompt_editor":
    render_prompt_editor()

elif st.session_state.page == "test_manager":
    render_test_manager()

elif st.session_state.page == "test_runner":
    render_test_runner()

elif st.session_state.page == "results_viewer":
    render_results_viewer()

elif st.session_state.page == "prompt_interactive_test":
    render_prompt_interactive_test()

elif st.session_state.page == "prompt_dialogue_test":
    render_prompt_dialogue_test()

# 在页面路由部分添加
elif st.session_state.page == "prompt_optimization":
    render_prompt_optimization()

elif st.session_state.page == "prompt_auto_optimization":
    render_prompt_auto_optimization()

elif st.session_state.page == "prompt_ab_test":
    render_prompt_ab_test()

elif st.session_state.page == "prompt_batch_ab_test":
    render_prompt_batch_ab_test()

elif st.session_state.page == "provider_manager":
    render_provider_manager()