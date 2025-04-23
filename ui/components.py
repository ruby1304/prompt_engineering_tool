import streamlit as st
from config import get_available_models
from models.api_clients import get_provider_from_model
import pandas as pd
import plotly.graph_objects as go

from utils.common import (
    calculate_average_score, 
    get_dimension_scores, 
    create_dimension_radar_chart
)

def select_single_model(key_prefix="model", help_text=None):
    """单模型选择器组件
    
    返回: (model, provider)
    """
    # 动态获取所有可用模型
    available_models = get_available_models()
    all_models = []
    
    # 创建统一的模型列表，包含提供商信息
    for provider, models in available_models.items():
        for model in models:
            all_models.append((provider, model))
    
    # 创建格式化的选项列表，显示提供商信息
    model_options = [f"{model} ({provider})" for provider, model in all_models]
    model_map = {f"{model} ({provider})": (model, provider) for provider, model in all_models}
    
    selected_model_option = st.selectbox(
        "选择模型",
        model_options,
        key=f"{key_prefix}_selector",
        help=help_text
    )
    
    if selected_model_option:
        return model_map[selected_model_option]
    else:
        return None, None

def select_multiple_models(key_prefix="models", label="选择模型"):
    """多模型选择器组件
    
    返回: List[(model, provider)]
    """
    # 动态获取所有可用模型
    available_models = get_available_models()
    selected_models = []
    
    # 显示标签
    st.markdown(f"**{label}:**")
    
    # 按提供商分组显示模型
    for provider, provider_models in available_models.items():
        # 显示提供商名称
        st.markdown(f"**{provider.capitalize()}:**")
        
        # 创建列来显示模型选择框
        cols = st.columns(2)
        col_idx = 0
        
        for model in provider_models:
            with cols[col_idx]:
                if st.checkbox(model, key=f"{key_prefix}_{provider}_{model}"):
                    selected_models.append((model, provider))
            
            # 切换列
            col_idx = (col_idx + 1) % 2
        
        # 添加分隔线
        st.divider()
    
    return selected_models


def display_test_summary(results, template, model):
    """显示测试结果摘要"""
    st.subheader("测试结果摘要")
    
    # 计算平均分数
    avg_score = calculate_average_score(results)
    
    # 获取维度评分
    dimension_scores = get_dimension_scores(results)
    
    # 显示测试结果摘要
    col1, col2 = st.columns(2)
    
    with col1:
        if avg_score > 0:
            st.metric("平均分数", f"{avg_score:.1f}")
            st.write("维度评分:")
            for dim, score in dimension_scores.items():
                st.metric(dim, f"{score:.1f}", label_visibility="visible")
        else:
            st.warning("未能找到有效的评估分数")
    
    with col2:
        if dimension_scores:
            # 创建雷达图
            fig = create_dimension_radar_chart(
                [dimension_scores], 
                [template.get("name", "当前提示词")],
                "提示词表现雷达图"
            )
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("没有足够的维度评分来生成雷达图")
    
    return avg_score, dimension_scores

def display_response_tabs(responses):
    """使用选项卡显示多个响应"""
    if not responses:
        st.info("没有响应数据")
        return
        
    for i, resp in enumerate(responses):
        st.markdown(f"**响应 #{i+1}:**")
        if resp.get("error"):
            st.error(resp.get("error"))
        else:
            st.code(resp.get("response", "无响应"))
            
        # 显示评估结果
        eval_result = resp.get("evaluation")
        if eval_result:
            display_evaluation_results(eval_result)

def display_evaluation_results(eval_result):
    """显示评估结果"""
    if not eval_result:
        return
        
    st.markdown("**评估结果:**")
    
    if "error" in eval_result:
        st.error(f"评估错误: {eval_result['error']}")
        return
        
    # 显示本地评估标记
    if eval_result.get("is_local_evaluation", False):
        st.warning("⚠️ 本地评估结果，非AI评估模型生成")
    
    # 显示分数
    if "scores" in eval_result:
        score_cols = st.columns(len(eval_result["scores"]))
        for i, (dim, score) in enumerate(eval_result["scores"].items()):
            with score_cols[i]:
                st.metric(dim, f"{score:.1f}")
    
    # 显示总分
    if "overall_score" in eval_result:
        st.metric("总分", f"{eval_result['overall_score']:.1f}")
    
    # 显示分析
    if "analysis" in eval_result:
        st.markdown("**分析:**")
        st.write(eval_result["analysis"])
    
    # 显示Token信息
    if "prompt_info" in eval_result:
        st.info(f"提示词Token数: {eval_result['prompt_info'].get('token_count', '未知')}")

def display_test_case_details(case, show_system_prompt=True, inside_expander=False):
    """显示测试用例详情"""
    if not case:
        st.info("没有测试用例数据")
        return
        
    # 显示用户输入和期望输出
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("**用户输入:**")
        st.code(case.get("user_input", ""))
    
    with col2:
        st.markdown("**期望输出:**")
        st.code(case.get("expected_output", ""))
    
    # 显示系统提示（可选）
    if show_system_prompt:
        if inside_expander:
            # 如果已经在expander内部，就不使用嵌套expander
            st.markdown("**系统提示:**")
            st.code(case.get("prompt", ""))
        else:
            # 正常使用expander
            with st.expander("查看系统提示"):
                st.code(case.get("prompt", ""))
    
    # 显示响应和评估结果
    if "responses" in case and case["responses"]:
        st.markdown("**模型响应:**")
        for resp in case["responses"]:
            # 如果在expander内部，则不使用嵌套expander
            if inside_expander:
                st.markdown(f"**响应 (模型: {resp.get('model', '未知')}, 尝试: #{resp.get('attempt', 0)}):**")
                if resp.get("error"):
                    st.error(resp.get("error"))
                else:
                    st.code(resp.get("response", ""))
                    if resp.get("usage"):
                        st.info(f"Token使用: {resp.get('usage', {}).get('total_tokens', '未知')}")
                
                # 显示评估结果
                if resp.get("evaluation"):
                    display_evaluation_results(resp.get("evaluation"))
            else:
                with st.expander(f"响应 (模型: {resp.get('model', '未知')}, 尝试: #{resp.get('attempt', 0)})"):
                    if resp.get("error"):
                        st.error(resp.get("error"))
                    else:
                        st.code(resp.get("response", ""))
                        if resp.get("usage"):
                            st.info(f"Token使用: {resp.get('usage', {}).get('total_tokens', '未知')}")
                    
                    # 显示评估结果
                    if resp.get("evaluation"):
                        display_evaluation_results(resp.get("evaluation"))
    
    # 兼容旧格式 - 如果使用model_responses
    elif "model_responses" in case:
        st.markdown("**模型响应:**")
        for resp in case["model_responses"]:
            # 如果在expander内部，则不使用嵌套expander
            if inside_expander:
                st.markdown(f"**响应 (模型: {resp.get('model', '未知')}, 尝试: #{resp.get('attempt', 0)}):**")
                if resp.get("error"):
                    st.error(resp.get("error"))
                else:
                    st.code(resp.get("response", ""))
                    if resp.get("usage"):
                        st.info(f"Token使用: {resp.get('usage', {}).get('total_tokens', '未知')}")
            else:
                with st.expander(f"响应 (模型: {resp.get('model', '未知')}, 尝试: #{resp.get('attempt', 0)})"):
                    if resp.get("error"):
                        st.error(resp.get("error"))
                    else:
                        st.code(resp.get("response", ""))
                        if resp.get("usage"):
                            st.info(f"Token使用: {resp.get('usage', {}).get('total_tokens', '未知')}")
    
    # 显示评估结果（如果使用旧格式）
    if "evaluation" in case:
        display_evaluation_results(case["evaluation"])
