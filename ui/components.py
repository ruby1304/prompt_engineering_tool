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
        st.metric("平均分数", f"{avg_score:.1f}")
        st.write("维度评分:")
        for dim, score in dimension_scores.items():
            st.write(f"- {dim}: {score:.1f}")
    
    with col2:
        # 创建雷达图
        fig = create_dimension_radar_chart(
            [dimension_scores], 
            [template.get("name", "当前提示词")],
            "提示词表现雷达图"
        )
        st.plotly_chart(fig, use_container_width=True)
    
    return avg_score, dimension_scores

def display_response_tabs(responses):
    """使用选项卡显示多个响应"""
    if not responses:
        st.info("无响应数据")
        return
    
    # 创建响应选项卡，每个响应一个选项卡
    resp_tabs = st.tabs([f"响应 #{resp.get('attempt', i+1)}" for i, resp in enumerate(responses)])
    
    # 在每个选项卡中显示对应响应
    for i, tab in enumerate(resp_tabs):
        resp = responses[i]
        with tab:
            if resp.get("error"):
                st.error(resp.get("error"))
            else:
                st.code(resp.get("response", ""))
                
                # 显示token使用情况
                if resp.get("usage"):
                    st.info(f"Token使用: {resp['usage'].get('total_tokens', '未知')}")
            
            # 显示评估结果
            display_evaluation_results(resp.get("evaluation"))

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

def display_test_case_details(case, show_system_prompt=True):
    """显示测试用例详细信息"""
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("**用户输入:**")
        st.code(case.get("user_input", ""))
    
    with col2:
        st.markdown("**期望输出:**")
        st.code(case.get("expected_output", ""))
    
    if show_system_prompt:
        with st.expander("查看系统提示"):
            st.code(case.get("prompt", ""))
    
    # 显示响应
    st.markdown("**模型响应:**")
    display_response_tabs(case.get("responses", []))