import streamlit as st
import json
import pandas as pd
import asyncio
from datetime import datetime
import time
import plotly.express as px
import plotly.graph_objects as go

from config import load_test_set, save_template
from utils.common import (
    calculate_average_score, 
    get_dimension_scores, 
    create_dimension_radar_chart,
    run_test,
    display_template_info,
    save_optimized_template,
    compare_dimension_performance
)
from ui.components import (
    display_test_summary,
    display_response_tabs,
    display_evaluation_results,
    display_test_case_details
)

def render_prompt_ab_test():
    st.title("🔬 提示词A/B测试")
    
    # 检查是否有A/B测试数据
    if (not hasattr(st.session_state, 'ab_test_original') or 
        not hasattr(st.session_state, 'ab_test_optimized')):
        st.warning("请先从提示词专项优化页面启动A/B测试")
        
        if st.button("返回提示词专项优化"):
            st.session_state.page = "prompt_optimization"
            st.rerun()
        return
    
    # 获取A/B测试数据
    original_template = st.session_state.ab_test_original
    optimized_template = st.session_state.ab_test_optimized
    model = st.session_state.ab_test_model
    model_provider = st.session_state.get("ab_test_model_provider")
    test_set_name = st.session_state.ab_test_test_set
    
    st.markdown(f"""
    ### A/B测试: 原始提示词 vs 优化提示词
    
    - **模型**: {model} ({model_provider if model_provider else "未指定提供商"})
    - **测试集**: {test_set_name}
    """)
    
    # 显示提示词对比
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("原始提示词")
        display_template_info(original_template)
    
    with col2:
        st.subheader("优化提示词")
        display_template_info(optimized_template)
    
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
    
    # 运行A/B测试
    if "ab_test_results" not in st.session_state:
        if st.button("▶️ 运行A/B测试", type="primary"):
            # 加载测试集
            test_set = load_test_set(test_set_name)
            
            if not test_set or not test_set.get("cases"):
                st.error(f"无法加载测试集 '{test_set_name}' 或测试集为空")
                return
            
            with st.spinner("A/B测试运行中..."):
                # 运行原始提示词测试
                st.text("测试原始提示词...")
                original_results = run_test(
                    original_template, 
                    model, 
                    test_set, 
                    model_provider=model_provider,
                    repeat_count=repeat_count,
                    temperature=temperature
                )
                
                # 运行优化提示词测试
                st.text("测试优化提示词...")
                optimized_results = run_test(
                    optimized_template, 
                    model, 
                    test_set,
                    model_provider=model_provider,
                    repeat_count=repeat_count,
                    temperature=temperature
                )
                
                # 保存结果
                st.session_state.ab_test_results = {
                    "original": original_results,
                    "optimized": optimized_results,
                    "params": {
                        "repeat_count": repeat_count,
                        "temperature": temperature
                    }
                }
                
                # 刷新页面以显示结果
                st.rerun()
    
    # 如果已有测试结果，显示结果
    if "ab_test_results" in st.session_state:
        display_ab_test_results(st.session_state.ab_test_results)
        
        # 添加清除结果按钮
        if st.button("🗑️ 清除测试结果", key="clear_ab_results"):
            if "ab_test_results" in st.session_state:
                del st.session_state.ab_test_results
            st.rerun()

def display_ab_test_results(ab_results):
    """显示A/B测试结果对比"""
    st.subheader("A/B测试结果")
    
    original_results = ab_results["original"]
    optimized_results = ab_results["optimized"]
    params = ab_results.get("params", {})
    
    # 获取模型信息
    model = original_results.get("model", "未知模型")
    model_provider = original_results.get("model_provider", "未知提供商")
    
    # 显示测试参数
    st.info(f"""
    **测试信息**:
    - 测试模型: **{model}** (提供商: **{model_provider}**)
    - 每个测试重复次数: **{params.get('repeat_count', 1)}**
    - 温度设置: **{params.get('temperature', 0.7)}**
    """)
    
    # 计算平均分数
    original_avg = calculate_average_score(original_results)
    optimized_avg = calculate_average_score(optimized_results)
    
    # 显示总体对比
    st.subheader("总体性能对比")
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.metric("原始提示词平均分", f"{original_avg:.1f}")
    
    with col2:
        st.metric("优化提示词平均分", f"{optimized_avg:.1f}")
    
    with col3:
        improvement = ((optimized_avg - original_avg) / original_avg * 100) if original_avg > 0 else 0
        st.metric("改进", f"{improvement:.1f}%", delta=f"{improvement:.1f}%")
    
    # 获取维度评分
    original_dims = get_dimension_scores(original_results)
    optimized_dims = get_dimension_scores(optimized_results)
    
    # 维度对比与改进表格
    compare_dimension_performance([original_results, optimized_results], ["原始提示词", "优化提示词"])
    
    # 显示用例级比较
    st.subheader("用例级比较")
    
    for case_index in range(min(len(original_results.get("test_cases", [])), len(optimized_results.get("test_cases", [])))):
        original_case = original_results["test_cases"][case_index]
        optimized_case = optimized_results["test_cases"][case_index]
        
        # 计算用例得分
        original_case_score = calculate_case_score(original_case)
        optimized_case_score = calculate_case_score(optimized_case)
        
        # 计算改进
        case_improvement = ((optimized_case_score - original_case_score) / original_case_score * 100) if original_case_score > 0 else 0
        
        # 确定哪个更好
        better_version = "优化版本" if optimized_case_score > original_case_score else "原始版本" if original_case_score > optimized_case_score else "相同"
        
        with st.expander(f"用例 {case_index+1}: {original_case.get('case_description', original_case.get('case_id', ''))} ({better_version}更好)"):
            # 显示用例信息
            display_test_case_details(original_case, show_system_prompt=False)
            
            # 显示用例比较
            col1, col2 = st.columns(2)
            
            with col1:
                st.subheader("原始提示词响应")
                st.code(original_case.get("prompt", ""))
                display_response_tabs(original_case.get("responses", []))
            
            with col2:
                st.subheader("优化提示词响应")
                st.code(optimized_case.get("prompt", ""))
                display_response_tabs(optimized_case.get("responses", []))
    
    # 结论
    st.subheader("结论")
    
    if optimized_avg > original_avg:
        st.success(f"✅ 优化提示词整体表现更好，提升了 {improvement:.1f}%")
        
        # 找出最大改进的维度
        if improvements:
            best_dim = max(improvements.items(), key=lambda x: x[1])
            st.write(f"最大改进在 **{best_dim[0]}** 维度，提升了 **{best_dim[1]:.1f}%**")
        
        # 保存优化提示词
        if st.button("保存优化提示词为模板", type="primary"):
            optimized_template = st.session_state.ab_test_optimized
            new_template = dict(optimized_template)
            new_name = save_optimized_template(new_template, {"prompt": new_template.get("template", ""), "strategy": new_template.get("description", "")})
            st.success(f"已将优化提示词保存为新模板: {new_name}")
    
    elif optimized_avg < original_avg:
        st.error(f"❌ 优化提示词整体表现不如原始提示词，下降了 {abs(improvement):.1f}%")
        st.write("建议重新优化提示词或保留原始提示词")
    else:
        st.info("🔄 优化提示词和原始提示词表现相当")

def calculate_case_score(case):
    """计算单个测试用例的平均得分"""
    total_score = 0
    count = 0
    
    responses = case.get("responses", [])
    for resp in responses:
        eval_result = resp.get("evaluation")
        if eval_result and "overall_score" in eval_result:
            total_score += eval_result["overall_score"]
            count += 1
    
    return total_score / count if count > 0 else 0
