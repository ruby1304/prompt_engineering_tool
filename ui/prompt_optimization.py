# prompt_optimization.py

import streamlit as st
import json
import pandas as pd
import asyncio
from datetime import datetime
import time
import plotly.express as px
import plotly.graph_objects as go

from config import get_template_list, load_template, get_test_set_list, load_test_set, save_template, get_available_models, get_all_template_names_sorted
from models.api_clients import get_client, get_provider_from_model
from models.token_counter import count_tokens, estimate_cost
from utils.evaluator import PromptEvaluator
from utils.optimizer import PromptOptimizer
from utils.common import (
    calculate_average_score, 
    get_dimension_scores, 
    create_dimension_radar_chart,
    run_test,
    save_optimized_template
)
from ui.components import (
    display_test_summary,
    display_response_tabs,
    display_evaluation_results,
    display_test_case_details
)

def render_prompt_optimization():
    tab1, tab2 = st.tabs(["专项优化（有样本）", "自动迭代优化"])
    with tab1:
        st.title("🔍 提示词专项优化")
        
        st.markdown("""
        这个工具专注于单提示词单模型的深度优化。您可以选择一个提示词模板和一个模型，
        运行测试并获取AI生成的优化版本提示词。
        """)
        
        # 步骤1: 选择提示词和模型
        st.subheader("步骤1: 选择提示词和模型")
        
        col1, col2 = st.columns(2)
        
        with col1:
            template_list = get_all_template_names_sorted()
            if not template_list:
                st.warning("未找到任何提示词模板（包括系统模板），请先创建模板")
                return
                
            selected_template = st.selectbox(
                "选择提示词模板（包含系统模板）",
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
                    
                # 加载测试集
                test_set = load_test_set(selected_test_set)
                if not test_set or not test_set.get("cases"):
                    st.error(f"无法加载测试集 '{selected_test_set}' 或测试集为空")
                    return

                # --- Progress Bar Setup ---
                total_cases = len(test_set.get("cases", []))
                total_attempts = total_cases * repeat_count
                completed_attempts = 0
                progress_bar = st.progress(0)
                status_text = st.empty()
                status_text.text(f"准备开始... 总共 {total_attempts} 次模型调用")

                def update_progress():
                    nonlocal completed_attempts
                    completed_attempts += 1
                    progress = completed_attempts / total_attempts if total_attempts > 0 else 0
                    progress = min(progress, 1.0)
                    progress_bar.progress(progress)
                    status_text.text(f"运行中... 已完成 {completed_attempts}/{total_attempts} 次模型调用")
                # --- End Progress Bar Setup ---

                # 开始测试
                test_results = run_test(
                    template=template,
                    model=selected_model,
                    test_set=test_set,
                    model_provider=selected_provider,
                    repeat_count=repeat_count,
                    temperature=temperature,
                    progress_callback=update_progress # Pass callback
                )
                
                # Final progress update and status
                progress_bar.progress(1.0)
                status_text.text(f"✅ 专项测试完成! 共执行 {completed_attempts}/{total_attempts} 次模型调用。")

                if test_results:
                    # 保存结果到会话状态，以便在优化步骤中使用
                    st.session_state.specialized_test_results = test_results
                    st.session_state.specialized_template = template
                    st.session_state.specialized_model = selected_model
                    st.session_state.specialized_model_provider = selected_provider
                    st.session_state.specialized_test_set_name = selected_test_set
                    
                    # 刷新页面以显示结果和优化按钮
                    st.rerun()
                else:
                    st.error("专项测试未能成功获取结果，请检查配置和API密钥。")
                    # Clear potentially empty state if needed
                    if "specialized_test_results" in st.session_state:
                        del st.session_state.specialized_test_results
        
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
                    display_test_case_details(case, inside_expander=True)
            
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
                st.rerun()
            
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

    with tab2:
        render_iterative_optimization()

def render_iterative_optimization():
    st.title("🔁 自动多轮提示词迭代优化")
    st.markdown("""
    本功能支持自动多轮提示词优化与评估，自动选出最优版本。
    """)
    # 选择模板、模型、测试集
    template_list = get_all_template_names_sorted()
    if not template_list:
        st.warning("未找到任何提示词模板（包括系统模板），请先创建模板")
        return
    selected_template = st.selectbox("选择提示词模板（包含系统模板）", template_list, key="iter_template")
    template = load_template(selected_template) if selected_template else None
    available_models = get_available_models()
    all_models = [(provider, model) for provider, models in available_models.items() for model in models]
    model_options = [f"{model} ({provider})" for provider, model in all_models]
    model_map = {f"{model} ({provider})": (model, provider) for provider, model in all_models}
    selected_model_option = st.selectbox("选择模型", model_options, key="iter_model")
    selected_model, selected_provider = model_map[selected_model_option] if selected_model_option else (None, None)

    # 步骤2: 选择测试集
    st.subheader("步骤2: 选择测试集")
    test_set_mode = st.radio(
        "测试集来源",
        ["选择已有测试集", "AI自动生成新测试集"],
        horizontal=True,
        key="iter_testset_mode"
    )
    test_set = []
    test_set_name = None
    
    if test_set_mode == "选择已有测试集":
        test_set_list = get_test_set_list()
        if not test_set_list:
            st.warning("未找到测试集，请先创建测试集")
            return
        selected_test_set = st.selectbox("选择测试集", test_set_list, key="iter_testset")
        if selected_test_set:
            loaded_test_set = load_test_set(selected_test_set)
            test_set = loaded_test_set  # 保持为dict，包含全局变量
            # 仅用于显示用例数时过滤
            valid_cases = [case for case in test_set.get("cases", []) if case.get("user_input") and case.get("expected_output") and case.get("evaluation_criteria")]
            test_set_name = selected_test_set
            st.info(f"**测试用例数**: {len(valid_cases)}")
    else:
        # AI自动生成新测试集
        test_set_name = st.text_input("新测试集名称", value=f"AI生成测试集_{datetime.now().strftime('%Y%m%d_%H%M%S')}")
        test_set_desc = st.text_input("新测试集描述", value="自动生成的测试集")
        gen_case_count = st.number_input("生成测试用例数量", min_value=3, max_value=1000, value=6, step=1)
        
        # 显示提示信息
        st.info("将根据当前提示词模板和模型，自动生成高质量测试用例")
        
        # 可以添加自定义测试方向的选项
        test_directions = st.text_area(
            "测试方向（可选）", 
            placeholder="输入特定测试方向，每行一个，例如：\n语义理解能力测试\n边界条件处理测试\n多语言处理能力测试",
            help="指定特定的测试方向，系统会针对这些方向生成测试用例"
        )

    # 迭代参数
    st.subheader("步骤3: 设置优化参数")
    max_iterations = st.slider("迭代次数", 1, 100, 5)
    optimization_strategy = st.selectbox(
        "优化策略",
        ["balanced", "accuracy", "completeness", "conciseness"],
        format_func=lambda x: {
            "balanced": "平衡优化 (准确性、完整性和简洁性)",
            "accuracy": "优化准确性",
            "completeness": "优化完整性",
            "conciseness": "优化简洁性"
        }.get(x, x),
        key="iter_strategy"
    )
    optimization_retries = st.number_input("优化失败重试次数", min_value=0, max_value=10, value=3, step=1, key="iter_optimization_retries")
    
    # 开始优化按钮
    if st.button("🚀 开始自动迭代优化", type="primary"):
        # 检查必要参数是否已选择
        if not template or not selected_model:
            st.error("请先选择提示词模板和模型")
            return
            
        # Progress Bar Setup for Test Set Generation and Iterations
        progress_container = st.container()
        with progress_container:
            generation_progress_bar = st.progress(0)
            generation_status_text = st.empty()
            # 修复这里的消息提示，根据测试集来源显示不同的准备信息
            if test_set_mode == "选择已有测试集":
                generation_status_text.text("准备使用已选择的测试集...")
            else:
                generation_status_text.text("准备生成测试集...")
        
        test_cases_for_optimization = None
        
        # 如果是AI自动生成测试集模式，先生成测试集
        if test_set_mode == "AI自动生成新测试集":
            with st.spinner("AI正在为您生成测试集..."):
                evaluator = PromptEvaluator()
                
                # 处理测试方向
                test_purposes = []
                if test_directions:
                    # 分割多行的测试方向
                    directions = [d.strip() for d in test_directions.strip().split("\n") if d.strip()]
                    if directions:
                        # 如果有指定测试方向，按方向生成测试用例
                        generation_status_text.text(f"正在生成多方向测试集，共{len(directions)}个方向...")
                        
                        # 每个方向生成对应数量的测试用例
                        cases_per_direction = max(1, gen_case_count // len(directions))
                        
                        # 创建基本的示例测试用例
                        example_case = {
                            "id": "example_case",
                            "description": f"{template.get('name', '提示词')}测试用例",
                            "user_input": "请给我讲解一下这个提示词的用途",
                            "expected_output": f"这个提示词用于{template.get('description', '特定任务处理')}，通过精确的指令引导模型输出高质量结果。",
                            "evaluation_criteria": {
                                "accuracy": "评估回答的准确性",
                                "completeness": "评估回答的完整性",
                                "relevance": "评估回答的相关性",
                                "clarity": "评估回答的清晰度"
                            }
                        }
                        
                        # 定义进度回调函数
                        def update_generation_progress(current, total):
                            progress = min(current / total, 1.0) if total > 0 else 0
                            generation_progress_bar.progress(progress)
                            generation_status_text.text(f"正在生成测试用例... 已完成: {current}/{total}")
                        
                        # 批量生成测试用例，传入进度回调函数
                        batch_result = evaluator.generate_test_cases_batch(
                            model=selected_model,
                            test_purposes=directions,
                            example_case=example_case,
                            target_count_per_purpose=cases_per_direction,
                            progress_callback=update_generation_progress
                        )
                        
                        if "error" in batch_result:
                            st.error(f"生成测试集失败: {batch_result['error']}")
                            return
                            
                        if "errors" in batch_result and batch_result["errors"]:
                            for error in batch_result["errors"]:
                                st.warning(error)
                                
                        # 修正：组装为dict结构，便于后续传递
                        test_cases_for_optimization = {
                            "cases": batch_result.get("test_cases", []),
                            "name": test_set_name,
                            "description": test_set_desc,
                        }
                else:
                    # 直接生成完整测试集
                    generation_status_text.text("正在生成通用测试集...")
                    
                    # 定义进度回调函数
                    def update_generation_progress(current, total):
                        progress = min(current / total, 1.0) if total > 0 else 0
                        generation_progress_bar.progress(progress)
                        generation_status_text.text(f"正在生成测试用例... 已完成: {current}/{total}")
                    
                    result = evaluator.generate_complete_test_set(
                        name=test_set_name,
                        description=test_set_desc,
                        model=selected_model,
                        count=gen_case_count
                    )
                    
                    if "error" in result:
                        st.error(f"生成测试集失败: {result['error']}")
                        return
                        
                    generated_test_set = result.get("test_set", {})
                    test_cases_for_optimization = generated_test_set  # 保持为dict结构
                    
                    # 保存生成的测试集
                    from config import save_test_set
                    save_test_set(test_set_name, generated_test_set)
                    
                # 检查生成的测试用例数量
                if not test_cases_for_optimization or not test_cases_for_optimization.get("cases"):
                    st.error("未能生成测试用例，请尝试其他参数或使用已有测试集")
                    return
                    
                # 更新生成进度
                generation_progress_bar.progress(1.0)
                generation_status_text.success(f"✅ 成功生成 {len(test_cases_for_optimization['cases'])} 个测试用例")
                
                # 展示生成的测试用例
                with st.expander("查看生成的测试用例"):
                    for i, case in enumerate(test_cases_for_optimization["cases"]):
                        st.write(f"**测试用例 {i+1}**: {case.get('description', '')}")
                        st.write(f"- **用户输入**: {case.get('user_input', '')}")
                        st.write(f"- **期望输出**: {case.get('expected_output', '')}")
                        st.write("---")
        else:
            # 使用已有测试集，直接赋值为dict结构
            # 并过滤无效用例
            filtered_cases = [case for case in test_set.get("cases", []) if case.get("user_input") and case.get("expected_output") and case.get("evaluation_criteria")]
            test_cases_for_optimization = dict(test_set)
            test_cases_for_optimization["cases"] = filtered_cases

        # 检查是否有测试用例用于优化
        if not test_cases_for_optimization or not test_cases_for_optimization.get("cases"):
            st.error("未能获取或生成有效的测试用例，无法开始优化。请确保测试集中的每个用例都包含 user_input、expected_output 和 evaluation_criteria。")
            return

        # 设置双进度条
        iteration_progress_bar = st.progress(0)
        iteration_status_text = st.empty()
        inner_progress_bar = st.progress(0)
        inner_status_text = st.empty()

        # 进度回调，支持两层进度
        def iteration_progress_callback(iteration, total_iterations, inner_idx, inner_total, global_idx, global_total, stage=None, data=None):
            # 从data中获取更详细的进度和分数信息
            avg_score = data.get('avg_score') if data else None 
            child_current = data.get('child_current') if data else inner_idx
            child_total = data.get('child_total') if data else inner_total
            
            # --- BEGIN MODIFICATION for effective_stage_name ---
            effective_stage_name = None
            child_data_from_parent = data.get('child_data', {}) if data else {}

            # Priority 1: 'stage_name' from child's 'complete(data_to_add=...)'
            effective_stage_name = child_data_from_parent.get('stage_name')
            
            # Update avg_score if it's more specifically available in child_data_from_parent
            if child_data_from_parent.get('avg_score') is not None:
                avg_score = child_data_from_parent.get('avg_score')

            if not effective_stage_name and data:
                # Priority 2: 'description' from ProgressTracker (passed as 'stage' in callback)
                effective_stage_name = data.get('description') # 'description' from ProgressTracker
            
            if not effective_stage_name:
                # Priority 3: 'stage' directly from callback args (less common now with ProgressTracker)
                effective_stage_name = stage

            # --- END MODIFICATION for effective_stage_name ---

            # 更新总进度条
            iter_progress = min(global_idx / global_total, 1.0) if global_total > 0 else 0
            iteration_progress_bar.progress(iter_progress)
            
            iteration_status = f"迭代优化进行中... 第 {iteration}/{total_iterations} 轮 (总进度: {iter_progress:.2%})"
            if avg_score is not None and effective_stage_name and ('eval_done' in effective_stage_name or 'opt_eval_done' in effective_stage_name):
                iteration_status += f"，阶段 '{effective_stage_name}' 平均分: {avg_score:.2f}"
            elif avg_score is not None: 
                 iteration_status += f"，当前平均分: {avg_score:.2f}"
            iteration_status_text.text(iteration_status)
            
            # 内层进度（具体阶段的进度）
            current_stage_progress = min(child_current / child_total, 1.0) if child_total > 0 else 0
            inner_progress_bar.progress(current_stage_progress)

            stage_text_map = {
                "gen": f"生成响应: {child_current}/{child_total}",
                "eval": f"评估响应: {child_current}/{child_total}",
                "opt_gen": f"生成优化版本响应: {child_current}/{child_total}",
                "opt_eval": f"评估优化版本: {child_current}/{child_total}",
                "eval_done": f"评估完成! 平均分: {avg_score:.2f}" if avg_score is not None else "评估完成!",
                "opt_eval_done": f"优化版本评估完成! 平均分: {avg_score:.2f}" if avg_score is not None else "优化版本评估完成!"
            }
            
            display_stage_key = effective_stage_name 
            if effective_stage_name: 
                if effective_stage_name.startswith("gen_") and len(effective_stage_name.split('_')) > 1 : display_stage_key = "gen"
                elif effective_stage_name.startswith("eval_") and not "done" in effective_stage_name and len(effective_stage_name.split('_')) > 1: display_stage_key = "eval"
                elif effective_stage_name.startswith("opt_gen_") and len(effective_stage_name.split('_')) > 2 : display_stage_key = "opt_gen"
                elif effective_stage_name.startswith("opt_eval_") and not "done" in effective_stage_name and len(effective_stage_name.split('_')) > 2: display_stage_key = "opt_eval"
                elif "eval_done" in effective_stage_name: display_stage_key = "eval_done"
                elif "opt_eval_done" in effective_stage_name: display_stage_key = "opt_eval_done"

            status_message = stage_text_map.get(display_stage_key, f"处理中: {effective_stage_name} ({child_current}/{child_total})")
            
            if display_stage_key and "done" in display_stage_key:
                inner_status_text.success(status_message)
            else:
                inner_status_text.text(status_message)

        try:
            st.info(f"即将开始迭代优化，计划进行 {max_iterations} 轮迭代...")
            
            # 添加时间戳记录开始时间
            start_time = time.time()
            
            # 执行迭代优化
            optimizer = PromptOptimizer(optimization_retries=optimization_retries)
            result = optimizer.iterative_prompt_optimization_sync(
                initial_prompt=template,
                test_set_dict=test_cases_for_optimization, 
                evaluator=PromptEvaluator(),
                optimization_strategy=optimization_strategy,
                model=selected_model,
                provider=selected_provider,
                max_iterations=max_iterations,
                progress_callback=iteration_progress_callback
            )
            
            # 记录完成时间和总耗时
            end_time = time.time()
            total_time = end_time - start_time
            st.success(f"迭代优化完成！总耗时: {total_time:.1f} 秒")
            
            # 检查结果
            if "error" in result:
                st.error(f"迭代优化过程出错: {result.get('error')}")
                if result.get("history"):
                    st.info("尽管出现错误，仍能展示部分结果")
                else:
                    return
                
            # 获取历史记录
            history = result.get("history", [])
            if not history:
                st.warning("未能获取迭代优化历史记录")
                return
                
            # 记录每轮的数据量
            history_stats = {}
            for item in history:
                iteration = item.get('iteration', 0)
                stage = item.get('stage', 'unknown')
                if iteration not in history_stats:
                    history_stats[iteration] = {'initial': 0, 'optimized': 0}
                if stage == 'initial':
                    history_stats[iteration]['initial'] += 1
                elif stage == 'optimized':
                    history_stats[iteration]['optimized'] += 1
            # 修正：确保最后一轮也统计（即使优化版本为0）
            for i in range(1, max_iterations + 1):
                if i not in history_stats:
                    history_stats[i] = {'initial': 0, 'optimized': 0}
            st.write("迭代历史数据统计:")
            for iter_num in range(1, max_iterations + 1):
                stats = history_stats.get(iter_num, {'initial': 0, 'optimized': 0})
                st.write(f"- 第 {iter_num} 轮: 初始提示词 {stats['initial']} 个, 优化版本 {stats['optimized']} 个")
            
            # 更新最终进度
            iteration_progress_bar.progress(1.0)
            iteration_status_text.success("✅ 自动迭代优化完成！")
            inner_progress_bar.progress(1.0)
            inner_status_text.success("全部评估任务已完成！")
            
            # 按迭代轮次重组结果，便于展示
            iteration_results = {}
            for item in history:
                iteration = item.get('iteration', 0)
                if iteration not in iteration_results:
                    iteration_results[iteration] = {
                        'initial': None,
                        'optimized': []
                    }
                
                stage = item.get('stage', '')
                if stage == 'initial':
                    iteration_results[iteration]['initial'] = item
                elif stage == 'optimized':
                    iteration_results[iteration]['optimized'].append(item)
                    
            # 输出一些调试信息
            st.write(f"共完成 {len(iteration_results)} 轮迭代")
            
            # 展示每轮结果
            for iter_num in sorted(iteration_results.keys()):
                iter_data = iteration_results[iter_num]
                
                with st.expander(f"第 {iter_num} 轮迭代", expanded=True):
                    # 显示本轮初始提示词
                    if iter_data['initial']:
                        st.subheader(f"当前提示词 (平均分: {iter_data['initial'].get('avg_score', 0):.2f})")
                        prompt_str = iter_data['initial'].get('prompt_str')
                        prompt_obj = iter_data['initial'].get('prompt_obj')
                        prompt = iter_data['initial'].get('prompt')
                        if prompt_str:
                            st.code(prompt_str, language="markdown")
                        elif prompt:
                            st.code(prompt, language="markdown")
                        elif prompt_obj:
                            st.code(json.dumps(prompt_obj, ensure_ascii=False, indent=2), language="json")
                        else:
                            st.warning("未找到本轮初始提示词内容")
                    else:
                        st.info(f"未找到第 {iter_num} 轮的初始提示词信息")
                    
                    # 如果是最后一轮迭代，不会有优化版本
                    if not iter_data['optimized'] and iter_num == max_iterations:
                        st.info("最后一轮迭代，无需生成优化版本")
                        continue
                    
                    # 显示本轮生成的优化版本
                    if iter_data['optimized']:
                        st.subheader(f"本轮生成的优化版本 ({len(iter_data['optimized'])} 个)")
                        
                        # 只标记一个最佳版本
                        best_version = None
                        for version in iter_data['optimized']:
                            if version.get('is_best', False):
                                best_version = version
                                break
                        
                        if not best_version and iter_data['optimized']:
                            best_version = max(iter_data['optimized'], key=lambda x: x.get('avg_score', 0))
                        
                        best_version_id = id(best_version) if best_version else None
                        
                        # 展示每个优化版本 - 不再使用嵌套expander，而是使用容器和分隔线
                        for idx, version in enumerate(iter_data['optimized']):
                            # 只标记一个最佳
                            is_best = (id(version) == best_version_id)
                            version_label = f"版本 {version.get('version', '?')}"
                            
                            if is_best:
                                version_label += " ✅ (选为下一轮的提示词)"
                            
                            version_score = version.get('avg_score', 0)
                            version_strategy = version.get('strategy', '未知策略')
                            
                            # 使用容器替代嵌套的expander
                            version_container = st.container()
                            with version_container:
                                st.markdown(f"### {version_label} - {version_strategy} (平均分: {version_score:.2f})")
                                st.markdown(f"**优化策略**: {version_strategy}")
                                v_prompt_str = version.get('prompt_str')
                                v_prompt = version.get('prompt')
                                v_prompt_obj = version.get('prompt_obj')
                                if v_prompt_str:
                                    st.code(v_prompt_str, language="markdown")
                                elif v_prompt:
                                    st.code(v_prompt, language="markdown")
                                elif v_prompt_obj:
                                    st.code(json.dumps(v_prompt_obj, ensure_ascii=False, indent=2), language="json")
                                else:
                                    st.warning("未找到此版本的提示词内容")
                                st.markdown("---")
                    else:
                        st.info(f"第 {iter_num} 轮未生成优化版本")
            
            # 展示最优结果
            st.markdown("---")
            st.header("最终最优提示词")
            best_prompt_obj = result.get("best_prompt_obj", None)
            best_score = result.get("best_score", 0)
            
            if best_prompt_obj and isinstance(best_prompt_obj, dict):
                best_prompt_str = best_prompt_obj.get("template", "")
                st.code(best_prompt_str, language="markdown")
                st.markdown(f"**最优平均分**: {best_score:.2f}")
                st.markdown("**最优提示词完整对象（含变量）**:")
                st.code(json.dumps(best_prompt_obj, ensure_ascii=False, indent=2), language="json")
                # 自动保存最优提示词为新模板（完整对象，包含变量）
                from utils.common import save_optimized_template
                new_name = save_optimized_template(template, best_prompt_obj, 0)
                st.session_state.iter_best_prompt = best_prompt_str
                st.session_state.iter_best_score = best_score
                st.session_state.iter_best_template_name = new_name
                st.success(f"最优提示词已自动保存为新模板: {new_name}")
                # 提供再次保存的选项
                if st.button("💾 再次保存最优提示词为新模板"):
                    new_name2 = save_optimized_template(template, best_prompt_obj, int(time.time())%10000)
                    st.success(f"已保存为新模板: {new_name2}")
            else:
                st.warning("未能获取最优提示词结果")
        except Exception as e:
            st.error(f"迭代优化过程出错: {str(e)}")
            import traceback
            st.code(traceback.format_exc(), language="python")

def generate_optimized_prompts(results, template, model, optimization_strategy, auto_evaluate=False, model_provider=None):
    """
    根据测试结果生成优化提示词
    """
    with st.spinner("AI正在分析测试结果并生成优化提示词..."):
        # 收集评估结果
        evaluations = []
        # 遍历所有测试用例
        for case in results.get("test_cases", []):
            responses = case.get("responses", [])
            if responses:
                for response in responses:
                    if response.get("evaluation") and not response.get("error"):
                        evaluations.append(response["evaluation"])
            elif case.get("evaluation"):
                evaluations.append(case["evaluation"])
        if not evaluations:
            st.error("没有找到有效的评估结果，无法生成优化提示词")
            return
        optimizer = PromptOptimizer()
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
            st.session_state.optimized_prompts = optimized_prompts
            st.success(f"成功生成 {len(optimized_prompts)} 个优化提示词版本")
            display_optimized_prompts(optimized_prompts, template, model, model_provider)
            if auto_evaluate:
                optimized_templates = []
                for i, opt_prompt in enumerate(optimized_prompts):
                    optimized_template = dict(template)
                    optimized_template["name"] = f"{template.get('name', '')}的优化版本_{i+1}"
                    optimized_template["description"] = f"优化策略: {opt_prompt.get('strategy', '')}"
                    optimized_template["template"] = opt_prompt.get("prompt", "")
                    optimized_templates.append(optimized_template)
                st.session_state.batch_ab_test_original = template
                st.session_state.batch_ab_test_optimized = optimized_templates
                st.session_state.batch_ab_test_model = model
                st.session_state.batch_ab_test_model_provider = model_provider
                st.session_state.batch_ab_test_test_set = st.session_state.specialized_test_set_name
                st.session_state.page = "prompt_batch_ab_test"
                st.rerun()

def display_optimized_prompts(optimized_prompts, template, model, model_provider):
    """显示优化提示词结果"""
    if not optimized_prompts:
        st.warning("没有优化提示词可显示")
        return
    
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
        st.rerun()
    
    # 显示各个优化提示词版本
    for i, opt_prompt in enumerate(optimized_prompts):
        with st.expander(f"优化版本 {i+1}: {opt_prompt.get('strategy', '未知策略')}"):
            # 使用更清晰的视觉分隔
            st.divider()
            
            # 优化策略部分
            st.markdown("#### 优化策略")
            st.write(opt_prompt.get("strategy", ""))
            
            # 显示针对解决的问题（如果有）
            if "problem_addressed" in opt_prompt:
                st.markdown("#### 针对解决的问题")
                st.info(opt_prompt.get("problem_addressed", ""))
            
            # 预期改进
            st.markdown("#### 预期改进")
            st.write(opt_prompt.get("expected_improvements", ""))
            
            # 优化理由（如果有）
            if "reasoning" in opt_prompt:
                st.markdown("#### 优化理由")
                st.info(opt_prompt.get("reasoning", ""))
            
            st.divider()
            
            # 显示优化后的提示词
            st.markdown("#### 优化后的提示词")
            st.code(opt_prompt.get("prompt", ""), language="markdown")
            
            st.divider()
            
            # 创建按钮，将优化后的提示词保存为新模板或运行A/B测试
            col1, col2 = st.columns(2)
            
            with col1:
                if st.button(f"💾 保存为新模板", key=f"save_opt_{i}"):
                    new_name = save_optimized_template(template, opt_prompt, i)
                    st.success(f"已保存为新模板: {new_name}")
            
            with col2:
                if st.button(f"🔍 A/B测试", key=f"test_opt_{i}"):
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
                    st.rerun()
