# prompt_optimization.py

import streamlit as st
import json
import pandas as pd
import asyncio
from datetime import datetime
import time
import plotly.express as px
import plotly.graph_objects as go

from config import get_template_list, load_template, get_test_set_list, load_test_set, save_template, get_available_models
from models.api_clients import get_client, get_provider_from_model
from models.token_counter import count_tokens, estimate_cost
from utils.evaluator import PromptEvaluator
from utils.optimizer import PromptOptimizer
from utils.common import (
    calculate_average_score, 
    get_dimension_scores, 
    create_dimension_radar_chart,
    run_test,
    display_template_info
)
from ui.components import (
    display_test_summary,
    display_response_tabs,
    display_evaluation_results,
    display_test_case_details
)

def render_prompt_optimization():
    st.title("🔍 提示词专项优化")
    
    st.markdown("""
    这个工具专注于单提示词单模型的深度优化。您可以选择一个提示词模板和一个模型，
    运行测试并获取AI生成的优化版本提示词。
    """)
    
    # 步骤1: 选择提示词和模型
    st.subheader("步骤1: 选择提示词和模型")
    
    col1, col2 = st.columns(2)
    
    with col1:
        template_list = get_template_list()
        if not template_list:
            st.warning("未找到提示词模板，请先创建模板")
            return
            
        selected_template = st.selectbox(
            "选择提示词模板",
            template_list
        )
        
        if selected_template:
            template = load_template(selected_template)
            st.info(f"**描述**: {template.get('description', '无描述')}")
            
            with st.expander("查看提示词内容"):
                st.code(template.get("template", ""))
    
    with col2:
        # 获取可用模型列表
        available_models = get_available_models()
        all_models = []
        
        # 创建统一的模型列表
        for provider, models in available_models.items():
            for model in models:
                all_models.append((provider, model))
        
        # 创建下拉选项
        model_options = [f"{model} ({provider})" for provider, model in all_models]
        model_map = {f"{model} ({provider})": (model, provider) for provider, model in all_models}
        
        # 选择模型
        selected_model_option = st.selectbox(
            "选择模型",
            model_options
        )
        
        if selected_model_option:
            selected_model, selected_provider = model_map[selected_model_option]
        else:
            selected_model = ""
            selected_provider = ""
        
        # 运行参数
        st.subheader("运行参数")
        temperature = st.slider("Temperature", 0.0, 2.0, 0.7, 0.1)
        max_tokens = st.slider("最大输出Token", 100, 4000, 1000, 100)
        repeat_count = st.slider("每个测试重复次数", 1, 3, 2, 1)
    
    # 步骤2: 选择测试集
    st.subheader("步骤2: 选择测试集")
    
    test_set_list = get_test_set_list()
    if not test_set_list:
        st.warning("未找到测试集，请先创建测试集")
        return
        
    selected_test_set = st.selectbox(
        "选择测试集",
        test_set_list
    )
    
    if selected_test_set:
        test_set = load_test_set(selected_test_set)
        st.info(f"**测试用例数**: {len(test_set.get('cases', []))}")
    
    # 检查是否已经有测试结果
    has_test_results = "specialized_test_results" in st.session_state
    
    # 步骤3: 运行测试
    st.subheader("步骤3: 运行测试")
    
    if not has_test_results:  # 仅在没有测试结果时显示测试按钮
        if st.button("▶️ 开始专项测试", type="primary"):
            if not selected_template or not selected_model or not selected_test_set:
                st.error("请先选择提示词模板、模型和测试集")
                return
                
            # 开始测试
            with st.spinner("测试运行中..."):
                # 加载测试集
                test_set = load_test_set(selected_test_set)
                
                test_results = run_test(
                    template=template,
                    model=selected_model,
                    test_set=test_set,
                    model_provider=selected_provider,
                    repeat_count=repeat_count,
                    temperature=temperature
                )
                
                if test_results:
                    # 保存结果到会话状态，以便在优化步骤中使用
                    st.session_state.specialized_test_results = test_results
                    st.session_state.specialized_template = template
                    st.session_state.specialized_model = selected_model
                    st.session_state.specialized_model_provider = selected_provider
                    st.session_state.specialized_test_set_name = selected_test_set
                    
                    # 刷新页面以显示结果和优化按钮
                    st.experimental_rerun()
    
    # 如果已有测试结果，显示结果和优化按钮
    if has_test_results:
        # 重新获取会话状态中的数据
        test_results = st.session_state.specialized_test_results
        template = st.session_state.specialized_template
        selected_model = st.session_state.specialized_model
        selected_provider = st.session_state.specialized_model_provider
        
        # 显示测试结果摘要
        display_test_summary(test_results, template, selected_model)
        
        # 显示详细测试结果
        st.subheader("详细测试结果")
        
        for i, case in enumerate(test_results.get("test_cases", [])):
            with st.expander(f"测试用例 {i+1}: {case.get('case_description', case.get('case_id', ''))}"):
                display_test_case_details(case)
        
        # 添加清除结果按钮
        if st.button("🗑️ 清除测试结果", key="clear_results"):
            # 清除会话状态中的测试结果
            if "specialized_test_results" in st.session_state:
                del st.session_state.specialized_test_results
            if "specialized_template" in st.session_state:
                del st.session_state.specialized_template
            if "specialized_model" in st.session_state:
                del st.session_state.specialized_model
            if "specialized_model_provider" in st.session_state:
                del st.session_state.specialized_model_provider
            if "specialized_test_set_name" in st.session_state:
                del st.session_state.specialized_test_set_name
            if "optimized_prompts" in st.session_state:
                del st.session_state.optimized_prompts
            
            # 刷新页面
            st.experimental_rerun()
        
        # 步骤4: 生成优化提示词
        st.subheader("步骤4: 生成优化提示词")
        
        # 添加自动批量评估选项
        auto_evaluate = st.checkbox(
            "生成优化提示词后自动进行批量评估", 
            value=False,
            help="选中此选项将在生成优化提示词后自动进行批量评估"
        )
        
        # 检查是否有优化结果
        has_optimization_results = "optimized_prompts" in st.session_state

        optimization_strategy = st.selectbox(
            "选择优化策略",
            ["balanced", "accuracy", "completeness", "conciseness"],
            format_func=lambda x: {
                "balanced": "平衡优化 (准确性、完整性和简洁性)",
                "accuracy": "优化准确性",
                "completeness": "优化完整性",
                "conciseness": "优化简洁性"
            }.get(x, x)
        )
        
        # 只有在没有优化结果时显示优化按钮
        if not has_optimization_results:
            if st.button("🔄 生成优化提示词", key="optimize_button", type="primary"):
                generate_optimized_prompts(
                    test_results, 
                    template, 
                    selected_model, 
                    optimization_strategy,
                    auto_evaluate=auto_evaluate,
                    model_provider=selected_provider
                )
        
        # 如果已有优化结果，显示结果
        if has_optimization_results:
            display_optimized_prompts(
                st.session_state.optimized_prompts, 
                template, 
                selected_model, 
                selected_provider
            )
            
            # 添加重新优化按钮
            if st.button("🔄 重新生成优化提示词", key="regenerate"):
                generate_optimized_prompts(
                    test_results, 
                    template, 
                    selected_model, 
                    optimization_strategy,
                    auto_evaluate=auto_evaluate,
                    model_provider=selected_provider
                )

def generate_optimized_prompts(results, template, model, optimization_strategy, auto_evaluate=False, model_provider=None):
    """根据测试结果生成优化提示词"""
    
    with st.spinner("AI正在分析测试结果并生成优化提示词..."):
        # 收集评估结果
        evaluations = []
        
        # 遍历所有测试用例
        for case in results.get("test_cases", []):
            # 检查是否使用新的响应格式
            responses = case.get("responses", [])
            
            if responses:
                # 处理每个响应的评估
                for response in responses:
                    if response.get("evaluation") and not response.get("error"):
                        evaluations.append(response["evaluation"])
            elif case.get("evaluation"):
                # 兼容旧格式
                evaluations.append(case["evaluation"])
        
        # 如果没有有效的评估结果，无法优化
        if not evaluations:
            st.error("没有找到有效的评估结果，无法生成优化提示词")
            return
        
        # 创建优化器
        optimizer = PromptOptimizer()
        
        # 生成优化提示词
        optimization_result = optimizer.optimize_prompt_sync(
            template.get("template", ""),
            evaluations,
            optimization_strategy
        )
        
        if "error" in optimization_result:
            st.error(f"优化失败: {optimization_result['error']}")
        else:
            optimized_prompts = optimization_result.get("optimized_prompts", [])
            
            if not optimized_prompts:
                st.warning("未能生成优化提示词")
                return
            
            # 将优化结果保存到会话状态
            st.session_state.optimized_prompts = optimized_prompts
            st.success(f"成功生成 {len(optimized_prompts)} 个优化提示词版本")
            
            # 显示优化提示词
            display_optimized_prompts(optimized_prompts, template, model, model_provider)
            
            # 自动进行批量评估
            if auto_evaluate:
                # 创建优化后的模板列表
                optimized_templates = []
                for i, opt_prompt in enumerate(optimized_prompts):
                    optimized_template = dict(template)
                    optimized_template["name"] = f"{template.get('name', '')}的优化版本_{i+1}"
                    optimized_template["description"] = f"优化策略: {opt_prompt.get('strategy', '')}"
                    optimized_template["template"] = opt_prompt.get("prompt", "")
                    optimized_templates.append(optimized_template)
                
                # 保存批量A/B测试所需数据到会话状态
                st.session_state.batch_ab_test_original = template
                st.session_state.batch_ab_test_optimized = optimized_templates
                st.session_state.batch_ab_test_model = model
                st.session_state.batch_ab_test_model_provider = model_provider
                st.session_state.batch_ab_test_test_set = st.session_state.specialized_test_set_name
                
                # 跳转到批量A/B测试页面
                st.session_state.page = "prompt_batch_ab_test"
                st.experimental_rerun()

def display_optimized_prompts(optimized_prompts, template, model, model_provider):
    """显示优化提示词结果"""
    if not optimized_prompts:
        st.warning("没有优化提示词可显示")
        return
        
    st.success(f"生成了 {len(optimized_prompts)} 个优化提示词版本")
    
    # 只有在未选择自动评估时才显示批量评估按钮
    if st.button("🔬 批量评估所有优化版本", type="primary"):
        # 创建优化后的模板列表
        optimized_templates = []
        for i, opt_prompt in enumerate(optimized_prompts):
            optimized_template = dict(template)
            optimized_template["name"] = f"{template.get('name', '')}的优化版本_{i+1}"
            optimized_template["description"] = f"优化策略: {opt_prompt.get('strategy', '')}"
            optimized_template["template"] = opt_prompt.get("prompt", "")
            optimized_templates.append(optimized_template)
        
        # 保存批量A/B测试所需数据到会话状态
        st.session_state.batch_ab_test_original = template
        st.session_state.batch_ab_test_optimized = optimized_templates
        st.session_state.batch_ab_test_model = model
        st.session_state.batch_ab_test_model_provider = model_provider
        st.session_state.batch_ab_test_test_set = st.session_state.specialized_test_set_name
        
        # 跳转到批量A/B测试页面
        st.session_state.page = "prompt_batch_ab_test"
        st.experimental_rerun()
    
    # 显示各个优化提示词版本
    for i, opt_prompt in enumerate(optimized_prompts):
        with st.expander(f"优化版本 {i+1}: {opt_prompt.get('strategy', '未知策略')}"):
            # 优化策略部分
            st.markdown("**优化策略:**")
            st.write(opt_prompt.get("strategy", ""))
            
            # 显示针对解决的问题（如果有）
            if "problem_addressed" in opt_prompt:
                st.markdown("**针对解决的问题:**")
                st.info(opt_prompt.get("problem_addressed", ""))
            
            # 预期改进
            st.markdown("**预期改进:**")
            st.write(opt_prompt.get("expected_improvements", ""))
            
            # 优化理由（如果有）
            if "reasoning" in opt_prompt:
                st.markdown("**优化理由:**")
                st.info(opt_prompt.get("reasoning", ""))
            
            # 显示优化后的提示词
            st.markdown("**优化后的提示词:**")
            st.code(opt_prompt.get("prompt", ""))
            
            # 创建按钮，将优化后的提示词保存为新模板或运行A/B测试
            col1, col2 = st.columns(2)
            
            with col1:
                if st.button(f"保存为新模板", key=f"save_opt_{i}"):
                    # 复制原始模板，替换提示词内容
                    new_template = dict(template)
                    current_time = datetime.now().strftime("%Y%m%d_%H%M%S")
                    new_template["name"] = f"{template.get('name', 'template')}_{current_time}_v{i+1}"
                    new_template["description"] = f"从 '{template.get('name', 'unknown')}' 优化: {opt_prompt.get('strategy', '')}"
                    new_template["template"] = opt_prompt.get("prompt", "")
                    
                    save_template(new_template["name"], new_template)
                    st.success(f"已保存为新模板: {new_template['name']}")
            
            with col2:
                if st.button(f"A/B测试", key=f"test_opt_{i}"):
                    # 创建优化后的模板
                    optimized_template = dict(template)
                    optimized_template["name"] = f"{template.get('name', '')}的优化版本_{i+1}"
                    optimized_template["description"] = f"优化策略: {opt_prompt.get('strategy', '')}"
                    optimized_template["template"] = opt_prompt.get("prompt", "")
                    
                    # 保存A/B测试所需数据到会话状态
                    st.session_state.ab_test_original = template
                    st.session_state.ab_test_optimized = optimized_template
                    st.session_state.ab_test_model = model
                    st.session_state.ab_test_model_provider = model_provider
                    st.session_state.ab_test_test_set = st.session_state.specialized_test_set_name
                    
                    # 跳转到A/B测试页面
                    st.session_state.page = "prompt_ab_test"
                    st.experimental_rerun()
