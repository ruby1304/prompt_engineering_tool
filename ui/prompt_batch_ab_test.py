# prompt_batch_ab_test.py

import streamlit as st
import json
import pandas as pd
import asyncio
from datetime import datetime
import time
import plotly.express as px
import numpy as np

from config import load_test_set, save_template
from utils.common import (
    calculate_average_score, 
    get_dimension_scores, 
    analyze_response_stability,
    create_dimension_radar_chart,
    create_score_bar_chart,
    run_test
)
from ui.components import (
    display_test_summary,
    display_response_tabs,
    display_evaluation_results,
    display_test_case_details
)

def render_prompt_batch_ab_test():
    st.title("🧪 提示词批量评估")
    
    # 检查是否有批量A/B测试数据
    if (not hasattr(st.session_state, 'batch_ab_test_original') or 
        not hasattr(st.session_state, 'batch_ab_test_optimized')):
        st.warning("请先从提示词专项优化页面启动批量评估")
        
        if st.button("返回提示词专项优化"):
            st.session_state.page = "prompt_optimization"
            st.experimental_rerun()
        return
    
    # 获取批量A/B测试数据
    original_template = st.session_state.batch_ab_test_original
    optimized_templates = st.session_state.batch_ab_test_optimized
    model = st.session_state.batch_ab_test_model
    model_provider = st.session_state.get("batch_ab_test_model_provider")
    test_set_name = st.session_state.batch_ab_test_test_set
    
    st.markdown(f"""
    ### 批量评估: 原始提示词 vs {len(optimized_templates)}个优化版本
    
    - **模型**: {model} ({model_provider if model_provider else "未指定提供商"})
    - **测试集**: {test_set_name}
    - **优化版本数**: {len(optimized_templates)}
    """)
    
    # 显示提示词概览
    with st.expander("查看所有提示词"):
        st.subheader("原始提示词")
        from utils.common import display_template_info
        display_template_info(original_template)
        
        for i, opt_template in enumerate(optimized_templates):
            st.subheader(f"优化版本 {i+1}")
            display_template_info(opt_template)
    
    # 测试参数设置
    st.subheader("测试参数")
    
    col1, col2 = st.columns(2)
    
    with col1:
        repeat_count = st.slider(
            "每个测试重复次数", 
            min_value=1, 
            max_value=5, 
            value=2, 
            help="增加重复次数可提高结果稳定性，特别是在高温度设置下"
        )
    
    with col2:
        temperature = st.slider(
            "Temperature", 
            min_value=0.0, 
            max_value=2.0, 
            value=0.7, 
            step=0.1,
            help="控制模型输出的随机性。较高的值会产生更多样化但可能不一致的输出"
        )
    
    # 运行批量测试
    if "batch_test_results" not in st.session_state:
        if st.button("▶️ 运行批量评估", type="primary"):
            # 加载测试集
            test_set = load_test_set(test_set_name)
            
            if not test_set or not test_set.get("cases"):
                st.error(f"无法加载测试集 '{test_set_name}' 或测试集为空")
                return
            
            with st.spinner("批量评估运行中..."):
                # 创建进度条
                progress_bar = st.progress(0)
                status_text = st.empty()
                
                # 计算总任务数
                total_templates = 1 + len(optimized_templates)
                total_tasks = total_templates
                completed_tasks = 0
                
                # 准备结果存储
                batch_results = {
                    "original": {"template": original_template, "results": None},
                    "optimized": []
                }
                
                # 测试原始提示词
                status_text.text("测试原始提示词...")
                original_results = run_test(
                    original_template, 
                    model, 
                    test_set, 
                    model_provider=model_provider,
                    repeat_count=repeat_count,
                    temperature=temperature
                )
                batch_results["original"]["results"] = original_results
                completed_tasks += 1
                progress_bar.progress(completed_tasks / total_tasks)
                
                # 测试所有优化版本
                for i, opt_template in enumerate(optimized_templates):
                    status_text.text(f"测试优化版本 {i+1}...")
                    opt_results = run_test(
                        opt_template, 
                        model, 
                        test_set,
                        model_provider=model_provider,
                        repeat_count=repeat_count,
                        temperature=temperature
                    )
                    batch_results["optimized"].append({
                        "template": opt_template,
                        "results": opt_results
                    })
                    completed_tasks += 1
                    progress_bar.progress(completed_tasks / total_tasks)
                
                # 完成进度条
                progress_bar.progress(1.0)
                status_text.text("✅ 批量评估完成!")
                
                # 保存结果
                st.session_state.batch_test_results = batch_results
                
                # 刷新页面以显示结果
                st.experimental_rerun()
    
    # 如果已有测试结果，显示结果
    if "batch_test_results" in st.session_state:
        batch_results = st.session_state.batch_test_results
        display_batch_test_results(batch_results)
        
        # 添加清除结果按钮
        if st.button("🗑️ 清除测试结果", key="clear_batch_results"):
            if "batch_test_results" in st.session_state:
                del st.session_state.batch_test_results
            st.experimental_rerun()

def display_batch_test_results(batch_results):
    """显示批量测试结果对比"""
    st.subheader("批量评估结果")
    
    # 获取模型信息
    original_results = batch_results["original"]["results"]
    model = original_results.get("model", "未知模型")
    model_provider = original_results.get("model_provider", "未知提供商")
    
    # 获取测试参数
    test_params = original_results.get("test_params", {})
    repeat_count = test_params.get("repeat_count", 1)
    temperature = test_params.get("temperature", 0.7)
    
    st.info(f"""
    **测试信息**:
    - 测试模型: **{model}** (提供商: **{model_provider}**)
    - 每个测试重复次数: **{repeat_count}**
    - 温度设置: **{temperature}**
    """)
    
    # 计算原始提示词和所有优化版本的平均分数
    original_avg = calculate_average_score(original_results)
    optimized_results_list = [item["results"] for item in batch_results["optimized"]]
    optimized_avgs = [calculate_average_score(res) for res in optimized_results_list]
    
    # 找出最佳版本
    all_scores = [original_avg] + optimized_avgs
    if all_scores and max(all_scores) > 0:
        best_index = all_scores.index(max(all_scores))
        
        if best_index == 0:
            best_template = batch_results["original"]["template"]
            best_score = original_avg
            best_label = "原始提示词"
        else:
            best_template = batch_results["optimized"][best_index-1]["template"]
            best_score = optimized_avgs[best_index-1]
            best_label = f"优化版本 {best_index}"
        
        # 显示最佳版本
        st.success(f"### 最佳提示词: {best_label} (得分: {best_score:.1f})")
    else:
        st.warning("未能找到有效的评估分数")
        best_template = None
        best_score = 0
        best_label = "未确定"
        best_index = -1
    
    # 创建总体对比图表
    st.subheader("总体性能对比")
    
    # 准备数据
    labels = ["原始提示词"] + [f"优化版本 {i+1}" for i in range(len(optimized_avgs))]
    scores = [original_avg] + optimized_avgs
    
    # 创建条形图
    fig = create_score_bar_chart(scores, labels, "提示词版本平均得分对比")
    st.plotly_chart(fig, use_container_width=True)
    
    # 显示响应稳定性分析
    st.subheader("响应稳定性分析")
    
    stability_data = []
    
    # 分析原始提示词的稳定性
    original_stability = analyze_response_stability(original_results)
    stability_data.append({"版本": "原始提示词", **original_stability})
    
    # 分析优化提示词的稳定性
    for i, result in enumerate(optimized_results_list):
        opt_stability = analyze_response_stability(result)
        stability_data.append({"版本": f"优化版本 {i+1}", **opt_stability})
    
    # 创建稳定性对比表格
    stability_df = pd.DataFrame(stability_data)
    st.dataframe(stability_df, use_container_width=True)
    
    # 创建维度雷达图对比
    st.subheader("维度表现对比")
    
    # 获取原始提示词的维度分数
    original_dimensions = get_dimension_scores(original_results)
    
    # 获取所有优化版本的维度分数
    optimized_dimensions = []
    for result in optimized_results_list:
        opt_dims = get_dimension_scores(result)
        optimized_dimensions.append(opt_dims)
    
    # 准备数据
    dimension_scores_list = [original_dimensions] + optimized_dimensions
    labels = ["原始提示词"] + [f"优化版本 {i+1}" for i in range(len(optimized_dimensions))]
    
    # 创建雷达图
    fig = create_dimension_radar_chart(dimension_scores_list, labels, "提示词版本维度表现对比")
    st.plotly_chart(fig, use_container_width=True)
    
    # 显示各维度提升情况
    st.subheader("各维度改进情况")
    
    # 创建表格数据
    improvement_data = []
    dimensions = list(original_dimensions.keys())
    
    for i, opt_dims in enumerate(optimized_dimensions):
        improvements = {}
        
        for dim in dimensions:
            if original_dimensions[dim] > 0:
                improvement = (opt_dims[dim] - original_dimensions[dim]) / original_dimensions[dim] * 100
            else:
                improvement = 0
                
            improvements[dim] = improvement
        
        # 计算总体改进
        avg_improvement = sum(improvements.values()) / len(improvements) if improvements else 0
        
        row = {
            "版本": f"优化版本 {i+1}",
            "总体改进": f"{avg_improvement:.1f}%"
        }
        
        for dim in dimensions:
            row[dim] = f"{improvements[dim]:.1f}%"
        
        improvement_data.append(row)
    
    # 显示表格
    if improvement_data:
        st.dataframe(pd.DataFrame(improvement_data), use_container_width=True)
    else:
        st.info("没有足够的数据来计算改进情况")
    
    # 添加详细比较功能
    st.subheader("详细对比分析")
    
    # 选择要比较的版本
    compare_versions = st.multiselect(
        "选择要详细比较的版本",
        options=labels,
        default=[labels[0], labels[best_index]] if best_index > 0 else [labels[0]]
    )
    
    if len(compare_versions) >= 2:
        # 获取要比较的结果
        compare_results = []
        for version in compare_versions:
            if version == "原始提示词":
                compare_results.append(original_results)
            else:
                # 提取版本号
                version_index = int(version.split()[-1]) - 1
                if version_index < len(optimized_results_list):
                    compare_results.append(optimized_results_list[version_index])
        
        # 显示用例级比较
        display_case_comparisons(compare_results, compare_versions)
    
    # 显示推荐使用的提示词
    display_recommendation(best_template, best_score, best_label, original_avg)

def display_case_comparisons(compare_results, compare_versions):
    """显示用例级别的详细比较"""
    for case_index in range(len(compare_results[0].get("test_cases", []))):
        case_exists = True
        for result in compare_results:
            if case_index >= len(result.get("test_cases", [])):
                case_exists = False
                break
        
        if not case_exists:
            continue
            
        # 获取所有版本的该用例结果
        case_data = []
        
        for i, result in enumerate(compare_results):
            case = result["test_cases"][case_index]
            version_name = compare_versions[i]
            
            # 获取所有响应的评估结果
            responses = case.get("responses", [])
            
            # 计算平均评分
            avg_score = 0
            score_count = 0
            
            for resp_data in responses:
                # 使用保存的评估结果
                eval_result = resp_data.get("evaluation")
                if eval_result and "overall_score" in eval_result:
                    avg_score += eval_result["overall_score"]
                    score_count += 1
            
            if score_count > 0:
                avg_score /= score_count
            
            case_data.append({
                "version": version_name,
                "responses": responses,
                "avg_score": avg_score,
                "case": case
            })
        
        # 找出最佳响应
        best_case_index = 0
        best_case_score = 0
        for i, data in enumerate(case_data):
            if data["avg_score"] > best_case_score:
                best_case_score = data["avg_score"]
                best_case_index = i
        
        # 显示用例详情
        with st.expander(f"用例 {case_index+1}: {case_data[0]['case'].get('case_description', case_data[0]['case'].get('case_id', ''))}"):
            # 显示用户输入和期望输出
            col1, col2 = st.columns(2)
            
            with col1:
                st.markdown("**用户输入:**")
                st.code(case_data[0]['case'].get("user_input", ""))
            
            with col2:
                st.markdown("**期望输出:**")
                st.code(case_data[0]['case'].get("expected_output", ""))
            
            # 为每个比较版本创建选项卡
            tabs = st.tabs([data["version"] for data in case_data])
            
            # 在每个选项卡中显示详细信息
            for i, tab in enumerate(tabs):
                with tab:
                    data = case_data[i]
                    
                    # 显示平均分数
                    st.metric("平均评分", f"{data['avg_score']:.1f}")
                    
                    if i == best_case_index and data["avg_score"] > 0:
                        st.success("✓ 此版本在当前用例中表现最佳")
                    
                    # 显示系统提示
                    with st.expander("查看系统提示"):
                        st.code(data["case"].get("prompt", ""))
                    
                    # 显示所有响应
                    st.subheader("响应")
                    display_response_tabs(data["responses"])

def display_recommendation(best_template, best_score, best_label, original_avg):
    """显示推荐使用的提示词"""
    st.subheader("推荐使用的提示词")
    
    if best_template and best_score > 0:
        improvement = ((best_score - original_avg) / original_avg * 100) if original_avg > 0 else 0
        improvement_text = f"提升了 **{improvement:.1f}%**" if best_score > original_avg else f"下降了 **{abs(improvement):.1f}%**"
        
        st.info(f"""
        根据评估结果，推荐使用 **{best_label}**。
        
        - 平均得分: **{best_score:.1f}**
        - 相比原始提示词: {improvement_text}
        """)
        
        # 保存推荐提示词
        if st.button("保存推荐提示词为模板", type="primary"):
            if best_template:
                new_template = dict(best_template)
                current_time = datetime.now().strftime("%Y%m%d_%H%M%S")
                
                if best_label == "原始提示词":
                    new_template["name"] = f"{best_template.get('name', 'template')}_{current_time}_recommended"
                    new_template["description"] = f"推荐使用的原始提示词 (得分: {best_score:.1f})"
                else:
                    new_template["name"] = f"{best_template.get('name', 'template')}_{current_time}_recommended"
                    new_template["description"] = f"推荐使用的优化提示词 (得分: {best_score:.1f})"
                
                save_template(new_template["name"], new_template)
                st.success(f"已将推荐提示词保存为新模板: {new_template['name']}")
    else:
        st.warning("无法确定推荐提示词，请检查评估结果")
