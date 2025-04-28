import streamlit as st
from config import get_available_models
from models.api_clients import get_provider_from_model
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
import matplotlib.pyplot as plt

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

def show_evaluation_detail(evaluation: dict, turn_number: int):
    """显示对话轮次的详细评估结果"""
    st.subheader(f"第 {turn_number} 轮对话评估结果")
    
    # 添加一个关闭按钮
    if st.button("收起评估详情", key=f"close_eval_{turn_number}", use_container_width=True):
        return False
        
    # 如果有错误信息，显示错误
    if "error" in evaluation:
        st.warning(f"评估过程遇到问题: {evaluation.get('error')}")
        return True
    
    # 创建选项卡布局
    tab1, tab2, tab3 = st.tabs(["评分详情", "问题诊断", "分析报告"])
    
    # 显示分数
    with tab1:
        scores = evaluation["scores"]
        overall = evaluation["overall_score"]
        
        # 以彩色方块和百分比形式显示分数
        st.write("#### 各维度评分")
        
        # 为每个分数创建一个进度条样式的显示
        for dimension, score in scores.items():
            if dimension != "prompt_efficiency":  # 排除提示词效率，因为这不是对话质量的直接衡量
                # 确定颜色
                color = "green" if score >= 80 else "orange" if score >= 60 else "red"
                
                # 创建可视化的分数条
                st.markdown(
                    f"**{dimension.capitalize()}**: "
                    f"<div style='background-color:#f0f2f6;border-radius:10px;height:25px;width:100%;margin-bottom:10px;'>"
                    f"<div style='background-color:{color};border-radius:10px;height:25px;width:{score}%;padding-left:10px;'>"
                    f"<span style='color:white;line-height:25px;'>{score}%</span>"
                    f"</div></div>",
                    unsafe_allow_html=True
                )
        
        # 总体评分
        st.write("#### 总体评分")
        overall_color = "green" if overall >= 80 else "orange" if overall >= 60 else "red"
        st.markdown(
            f"<div style='background-color:#f0f2f6;border-radius:10px;height:30px;width:100%;'>"
            f"<div style='background-color:{overall_color};border-radius:10px;height:30px;width:{overall}%;padding-left:10px;'>"
            f"<span style='color:white;line-height:30px;font-weight:bold;'>{overall}%</span>"
            f"</div></div>",
            unsafe_allow_html=True
        )
    
    # 问题诊断
    with tab2:
        issues = evaluation.get("issues", [])
        
        if not issues:
            st.success("未检测到明显问题，此轮对话表现良好！")
        else:
            st.write("#### 检测到的问题")
            
            # 按类型分组显示问题
            model_issues = [issue for issue in issues if issue["type"] == "model"]
            prompt_issues = [issue for issue in issues if issue["type"] == "prompt"]
            
            if model_issues:
                st.write("##### 模型问题")
                for issue in model_issues:
                    severity_color = "red" if issue["severity"] == "high" else "orange"
                    st.markdown(f"<div style='border-left:4px solid {severity_color};padding-left:10px;margin-bottom:10px;'>"
                               f"<p><strong>严重程度:</strong> {issue['severity']}</p>"
                               f"<p><strong>问题:</strong> {issue['description']}</p>"
                               f"<p><strong>建议:</strong> {issue['suggestion']}</p>"
                               f"</div>", unsafe_allow_html=True)
            
            if prompt_issues:
                st.write("##### 提示词问题")
                for issue in prompt_issues:
                    severity_color = "red" if issue["severity"] == "high" else "orange"
                    st.markdown(f"<div style='border-left:4px solid {severity_color};padding-left:10px;margin-bottom:10px;'>"
                               f"<p><strong>严重程度:</strong> {issue['severity']}</p>"
                               f"<p><strong>问题:</strong> {issue['description']}</p>"
                               f"<p><strong>建议:</strong> {issue['suggestion']}</p>"
                               f"</div>", unsafe_allow_html=True)
    
    # 分析报告
    with tab3:
        if "summary" in evaluation:
            st.write("#### 评估总结")
            st.info(evaluation["summary"])
        
        if "analysis" in evaluation:
            st.write("#### 详细分析")
            st.markdown(evaluation["analysis"])
            
        # Token使用情况
        if "prompt_info" in evaluation:
            st.write("#### 提示词信息")
            st.write(f"提示词token数量: {evaluation['prompt_info'].get('token_count', 'N/A')}")
            
    return True

def display_dialogue_analysis(dialogue_history, evaluation_results, prompt_ratings):
    """显示整个对话的分析结果
    
    Args:
        dialogue_history: 对话历史记录列表
        evaluation_results: 评估结果列表
        prompt_ratings: 提示词评分记录列表
    """
    st.subheader("🔍 对话分析")
    
    # 创建选项卡布局
    tab1, tab2, tab3 = st.tabs(["对话质量趋势", "提示词效果分析", "改进建议"])
    
    with tab1:
        st.write("#### 对话质量随时间变化趋势")
        
        # 提取评分数据
        if prompt_ratings:
            # 转换为pandas DataFrame以便分析
            df = pd.DataFrame([
                {
                    "turn": rating["turn"],
                    "overall": rating["overall"],
                    **rating["scores"]
                }
                for rating in prompt_ratings
            ])
            
            # 绘制总体评分趋势图
            fig, ax = plt.subplots(figsize=(10, 4))
            ax.plot(df["turn"], df["overall"], marker='o', linewidth=2, label='总体评分')
            ax.set_xlabel('对话回合')
            ax.set_ylabel('评分')
            ax.set_title('对话质量趋势')
            ax.grid(True, linestyle='--', alpha=0.7)
            ax.set_ylim(0, 100)
            st.pyplot(fig)
            
            # 绘制各维度评分趋势
            dimensions = [col for col in df.columns if col not in ["turn", "overall", "prompt_efficiency"]]
            if dimensions:
                fig, ax = plt.subplots(figsize=(10, 6))
                for dim in dimensions:
                    ax.plot(df["turn"], df[dim], marker='o', linewidth=2, label=dim)
                ax.set_xlabel('对话回合')
                ax.set_ylabel('评分')
                ax.set_title('各维度评分趋势')
                ax.grid(True, linestyle='--', alpha=0.7)
                ax.set_ylim(0, 100)
                ax.legend()
                st.pyplot(fig)
                
                # 计算评分的统计数据
                st.write("#### 评分统计数据")
                stats_df = df[dimensions + ["overall"]].describe().T[["mean", "std", "min", "max"]]
                stats_df = stats_df.round(2)
                
                # 为数据添加颜色标记
                def color_mean(val):
                    color = 'green' if val >= 80 else 'orange' if val >= 60 else 'red'
                    return f'color: {color}; font-weight: bold'
                
                # 应用样式并显示
                st.dataframe(stats_df.style.applymap(color_mean, subset=['mean']))
        else:
            st.info("尚无评估数据，请确保已启用自动评估或手动评估对话")
    
    with tab2:
        st.write("#### 提示词效果分析")
        
        # 分析各轮对话中提示词遵循度
        if prompt_ratings:
            # 计算提示词遵循度统计
            prompt_following_scores = [rating["scores"].get("prompt_following", 0) for rating in prompt_ratings]
            avg_following = sum(prompt_following_scores) / len(prompt_following_scores) if prompt_following_scores else 0
            
            # 显示提示词遵循度评分 - 避免使用嵌套列布局，改用行布局
            st.metric("平均提示词遵循度", f"{avg_following:.1f}/100")
            
            min_following = min(prompt_following_scores) if prompt_following_scores else 0
            st.metric("最低提示词遵循度", f"{min_following}/100")
            
            # 提示词问题汇总
            prompt_issues = []
            for i, eval_result in enumerate(evaluation_results):
                if eval_result and "issues" in eval_result:
                    for issue in eval_result["issues"]:
                        if issue["type"] == "prompt":
                            prompt_issues.append({
                                "turn": i+1,
                                "severity": issue["severity"],
                                "description": issue["description"],
                                "suggestion": issue["suggestion"]
                            })
            
            if prompt_issues:
                st.write("#### 提示词问题汇总")
                issue_df = pd.DataFrame(prompt_issues)
                st.dataframe(issue_df, use_container_width=True)
                
                # 按严重程度计数
                severity_counts = issue_df["severity"].value_counts()
                
                # 绘制饼图
                fig, ax = plt.subplots()
                ax.pie(severity_counts, labels=severity_counts.index, autopct='%1.1f%%',
                      colors=['red' if x == 'high' else 'orange' for x in severity_counts.index])
                ax.set_title('提示词问题严重程度分布')
                st.pyplot(fig)
            else:
                st.success("未检测到明显的提示词问题")
        else:
            st.info("尚无评估数据，请确保已启用自动评估或手动评估对话")
    
    with tab3:
        st.write("#### 改进建议")
        
        # 汇总所有建议
        all_suggestions = []
        model_suggestions = []
        prompt_suggestions = []
        
        for eval_result in evaluation_results:
            if eval_result and "issues" in eval_result:
                for issue in eval_result["issues"]:
                    if issue["type"] == "prompt" and issue["suggestion"] not in prompt_suggestions:
                        prompt_suggestions.append(issue["suggestion"])
                    elif issue["type"] == "model" and issue["suggestion"] not in model_suggestions:
                        model_suggestions.append(issue["suggestion"])
        
        # 提示词改进建议
        st.write("##### 提示词改进建议")
        if prompt_suggestions:
            for i, suggestion in enumerate(prompt_suggestions):
                st.markdown(f"{i+1}. {suggestion}")
        else:
            st.success("提示词表现良好，没有特别需要改进的地方")
        
        # 模型选择建议
        st.write("##### 模型使用建议")
        if model_suggestions:
            for i, suggestion in enumerate(model_suggestions):
                st.markdown(f"{i+1}. {suggestion}")
        else:
            st.success("模型表现良好，没有特别需要调整的地方")
        
        return prompt_suggestions, model_suggestions
