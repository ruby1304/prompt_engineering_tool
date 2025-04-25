import streamlit as st
import json
import pandas as pd
import asyncio
from datetime import datetime
import time
# 修改导入方式
from config import get_template_list, load_template, get_test_set_list, load_test_set, save_result, get_available_models, load_config
from models.api_clients import get_client, get_provider_from_model
from models.token_counter import count_tokens, estimate_cost
from utils.evaluator import PromptEvaluator
from utils.common import render_prompt_template, run_test

def render_test_runner():
    st.title("🧪 测试运行")
    
    # 选择要测试的提示词模板和测试集
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("选择提示词模板")
        
        template_list = get_template_list()
        
        if not template_list:
            st.warning("未找到提示词模板，请先创建模板")
            return
        
        selected_templates = []
        
        if "test_mode" not in st.session_state:
            st.session_state.test_mode = "single_prompt_multi_model"
        
        test_mode = st.radio(
            "测试模式",
            ["single_prompt_multi_model", "multi_prompt_single_model"],
            format_func=lambda x: "单提示词多模型" if x == "single_prompt_multi_model" else "多提示词单模型"
        )
        st.session_state.test_mode = test_mode
        
        if test_mode == "single_prompt_multi_model":
            selected_template = st.selectbox(
                "选择提示词模板",
                template_list
            )
            if selected_template:
                selected_templates = [selected_template]
        else:
            # 多选提示词模板
            for template_name in template_list:
                if st.checkbox(template_name, key=f"temp_{template_name}"):
                    selected_templates.append(template_name)
    
    with col2:
        st.subheader("选择测试集")
        
        test_set_list = get_test_set_list()
        
        if not test_set_list:
            st.warning("未找到测试集，请先创建测试集")
            return
        
        selected_test_set = st.selectbox(
            "选择测试集",
            test_set_list
        )
    
    if not selected_templates or not selected_test_set:
        st.warning("请选择提示词模板和测试集")
        return
    
    # 加载选择的模板和测试集
    templates = [load_template(name) for name in selected_templates]
    test_set = load_test_set(selected_test_set)
    
    # 模型选择和参数设置
    st.subheader("模型和参数设置")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("选择模型")
        
        # 使用组件选择模型
        if test_mode == "single_prompt_multi_model":
            # 多模型选择
            from ui.components import select_multiple_models
            selected_model_pairs = select_multiple_models(key_prefix="test_run", label="选择要测试的模型")
            
            # 提取模型名称和提供商信息
            selected_models = [model for model, _ in selected_model_pairs]
            model_provider_map = {model: provider for model, provider in selected_model_pairs}
            
            # 保存到会话状态
            st.session_state.model_provider_map = model_provider_map
        else:
            # 单模型选择
            from ui.components import select_single_model
            model, provider = select_single_model(key_prefix="test_run_single", help_text="选择用于测试的模型")
            
            selected_models = [model] if model else []
            if model:
                st.session_state.model_provider_map = {model: provider}
        
        if not selected_models:
            st.warning("请至少选择一个模型")
            return
    
    with col2:
        st.subheader("运行参数")
        
        temperature = st.slider("Temperature", 0.0, 2.0, 0.7, 0.1)
        max_tokens = st.slider("最大输出Token", 100, 4000, 1000, 100)
        repeat_count = st.slider("每个测试重复次数", 1, 5, 2, 1)
    
    # 显示当前的评估器设置（而不是允许更改）
    config = load_config()
    current_evaluator = config.get("evaluator_model", "gpt-4")
    use_local_eval = config.get("use_local_evaluation", False)
    provider = get_provider_from_model(current_evaluator)
    
    with st.expander("当前评估器设置", expanded=False):
        st.info(f"""
        - 评估模型: **{current_evaluator}** ({provider})
        - 本地评估: **{"启用" if use_local_eval else "禁用"}**
        
        *要更改评估模型设置，请前往 [API密钥与提供商管理 > 评估模型测试] 页面*
        """)
    
    # 预览测试配置
    st.subheader("测试预览")
    
    # 获取模型显示信息
    model_display_info = []
    for model in selected_models:
        provider = st.session_state.model_provider_map.get(model, "未知提供商")
        model_display_info.append(f"{model} ({provider})")
    
    preview_data = {
        "提示词模板": [t["name"] for t in templates],
        "测试集": test_set["name"],
        "测试用例数": len(test_set["cases"]),
        "选择的模型": model_display_info,
        "重复次数": repeat_count,
        "评估器模型": current_evaluator
    }
    
    st.json(preview_data)
    
    # 估算测试成本和时间
    total_calls = len(templates) * len(test_set["cases"]) * len(selected_models) * repeat_count
    avg_token_count = 1000  # 假设平均每次调用1000个token
    total_tokens = total_calls * avg_token_count
    
    # 估算成本（非常粗略）
    estimated_cost = sum([estimate_cost(avg_token_count, model) * len(test_set["cases"]) * repeat_count for model in selected_models])
    
    # 估算时间（假设每次调用平均2秒）
    estimated_time = total_calls * 2
    
    st.info(f"""
    ### 测试估算
    - 总API调用次数: {total_calls}
    - 预估Token数量: {total_tokens}
    - 预估成本: ${estimated_cost:.2f}
    - 预估完成时间: {estimated_time} 秒 (约 {estimated_time//60}分{estimated_time%60}秒)
    """)
    
    # 运行测试
    if st.button("▶️ 运行测试", type="primary"):
        run_tests(
            templates=templates,
            test_set=test_set,
            selected_models=selected_models,
            temperature=temperature,
            max_tokens=max_tokens,
            repeat_count=repeat_count,
            test_mode=test_mode
        )

def run_tests(templates, test_set, selected_models, temperature, max_tokens, repeat_count, test_mode):
    """运行测试并显示进度（并发重构版）"""
    st.subheader("测试运行中...")
    progress_bar = st.progress(0)
    status_text = st.empty()
    result_area = st.empty() # Keep this for potential future detailed status
    
    # Calculate total attempts based on cases and repeats
    total_cases = len(test_set.get("cases", []))
    total_attempts = len(templates) * len(selected_models) * total_cases * repeat_count
    completed_attempts = 0
    
    # Define the progress callback function
    def update_progress():
        nonlocal completed_attempts
        completed_attempts += 1
        progress = completed_attempts / total_attempts if total_attempts > 0 else 0
        # Ensure progress doesn't exceed 1.0 due to potential floating point issues
        progress = min(progress, 1.0)
        progress_bar.progress(progress)
        status_text.text(f"运行中... 已完成 {completed_attempts}/{total_attempts} 次模型调用")

    results = {}
    all_test_results = [] # Store results from run_test calls

    # --- Main Test Loop --- 
    # Iterate through templates and models to call run_test
    for template in templates:
        template_name = template["name"]
        template_results_for_models = []
        for model in selected_models:
            provider = st.session_state.model_provider_map.get(model) if hasattr(st.session_state, 'model_provider_map') else None
            
            status_text.text(f"正在运行: 模板 '{template_name}' - 模型 '{model}'...")
            
            # Call run_test with the progress callback
            test_result = run_test(
                template=template,
                model=model,
                test_set=test_set,
                model_provider=provider,
                repeat_count=repeat_count,
                temperature=temperature,
                progress_callback=update_progress # Pass the callback here
            )
            
            if test_result:
                template_results_for_models.append(test_result)
            else:
                st.warning(f"模板 '{template_name}' - 模型 '{model}' 测试运行失败或未返回结果。")
        
        # Store results grouped by template after processing all models for it
        if template_results_for_models:
             # Aggregate results for the current template from different models
            aggregated_cases = []
            for res in template_results_for_models:
                for case in res.get("test_cases", []):
                    # Add model info to each case if not already present (should be added by run_test)
                    if "model" not in case:
                         case["model"] = res.get("model")
                    aggregated_cases.append(case)
            
            results[template_name] = {
                "template": template,
                "test_set": test_set["name"],
                "models": selected_models, # List all models tested with this template
                "params": {
                    "temperature": temperature,
                    "max_tokens": max_tokens # Assuming max_tokens was intended here, though not passed to run_test
                },
                "test_cases": aggregated_cases # Combined cases from all models for this template
            }

    # --- Post-Test Processing --- 
    # Ensure progress bar reaches 100% and update status
    progress_bar.progress(1.0)
    status_text.text(f"✅ 测试完成! 共执行 {completed_attempts}/{total_attempts} 次模型调用。")
    result_area.empty() # Clear the intermediate status area

    # Save results
    result_name = f"test_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    save_result(result_name, results)
    st.success(f"测试结果已保存: {result_name}")

    # Display results preview
    from ui.components import display_test_case_details
    st.subheader("测试结果预览")
    # Check if results dictionary is empty
    if not results:
        st.warning("没有生成任何测试结果。请检查模型选择和测试配置。")
        return
        
    for template_name, template_result in results.items():
        st.markdown(f"#### 提示词模板: {template_name}")
        if not template_result.get("test_cases"):
            st.warning(f"模板 '{template_name}' 没有有效的测试用例结果。")
            continue
            
        # Display results grouped by case ID first, then show different model responses/evals
        cases_grouped = {}
        for case in template_result["test_cases"]:
            case_id = case.get("case_id", "unknown_case")
            if case_id not in cases_grouped:
                cases_grouped[case_id] = {
                    "description": case.get("case_description", case_id),
                    "details": []
                }
            cases_grouped[case_id]["details"].append(case)
            
        case_counter = 1
        for case_id, group_data in cases_grouped.items():
            st.markdown(f"**测试用例 {case_counter}: {group_data['description']}**")
            # Display details for each model run for this case
            for case_detail in group_data["details"]:
                 st.markdown(f"*模型: {case_detail.get('model', '未知')}*", help=f"Prompt used:\n```\n{case_detail.get('prompt', 'N/A')}\n```")
                 display_test_case_details(case_detail, show_system_prompt=False, inside_expander=True) # Use expander for cleaner look
            case_counter += 1
            st.divider()

    # Navigate to results viewer
    st.session_state.last_result = result_name
    st.session_state.page = "results_viewer"
    st.rerun()