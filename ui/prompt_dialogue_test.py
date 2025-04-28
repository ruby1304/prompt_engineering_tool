import streamlit as st
import json
import time
import pandas as pd
import matplotlib.pyplot as plt
from typing import Dict, Any, List, Tuple, Optional
import asyncio
import uuid

from config import load_template, get_template_list, load_test_set, get_test_set_list, save_test_set
from utils.common import render_prompt_template
from models.api_clients import get_provider_from_model, get_client
from ui.components import select_single_model
from utils.parallel_executor import execute_model_sync
from utils.evaluator import PromptEvaluator
from utils.test_set_manager import generate_unique_id, add_test_case


def render_prompt_dialogue_test():
    """渲染提示词多轮对话测试页面"""
    st.title("🗣️ 提示词多轮对话测试")
    
    st.markdown("""
    <div style="background-color: #f8f9fa; padding: 20px; border-radius: 10px; margin-bottom: 20px;">
    <h3 style="color: #4b778d;">多轮对话交互测试</h3>
    <p>测试某个对话提示词在多轮对话中的效果，评估每轮对话质量，并分析模型和提示词可能存在的问题。</p>
    </div>
    """, unsafe_allow_html=True)
    
    # 初始化对话历史
    if "dialogue_history" not in st.session_state:
        st.session_state.dialogue_history = []
    
    if "chat_turn" not in st.session_state:
        st.session_state.chat_turn = 0
        
    if "evaluation_results" not in st.session_state:
        st.session_state.evaluation_results = []
    
    if "prompt_ratings" not in st.session_state:
        st.session_state.prompt_ratings = []
        
    # 创建两列布局：左侧设置，右侧对话
    col_config, col_chat = st.columns([3, 4])
    
    with col_config:
        st.subheader("对话设置")
        
        # 选择提示词模板
        st.write("#### 选择提示词模板")
        template_list = get_template_list()
        if not template_list:
            st.warning("未找到提示词模板，请先创建模板")
            return
            
        selected_template_name = st.selectbox(
            "选择模板",
            options=template_list,
            help="选择要测试的提示词模板"
        )
        
        # 加载模板
        if selected_template_name:
            template = load_template(selected_template_name)
            if template:
                st.success(f"已加载模板: {selected_template_name}")
                
                # 展示模板内容预览
                with st.expander("查看模板内容", expanded=False):
                    st.code(template.get("template", ""))
                    st.write(f"**描述:** {template.get('description', '无描述')}")
            else:
                st.error(f"无法加载模板 {selected_template_name}")
                return
        
        # 选择模型
        st.write("#### 选择语言模型")
        model, provider = select_single_model(key_prefix="dialogue_test", help_text="选择用于测试的模型")
        
        if not model:
            st.warning("请选择一个模型")
        
        # 模型参数设置
        st.write("#### 模型参数")
        temperature = st.slider("Temperature", 0.0, 2.0, 0.7, 0.1, 
                              help="控制生成文本的随机性。较高的值会产生更多样化但可能不一致的输出")
        
        # 会话控制按钮
        st.write("#### 会话控制")
        control_cols = st.columns(2)
        
        with control_cols[0]:
            if st.button("🔄 重置对话", use_container_width=True):
                # 重置对话历史
                st.session_state.dialogue_history = []
                st.session_state.chat_turn = 0
                st.session_state.evaluation_results = []
                st.session_state.prompt_ratings = []
                st.experimental_rerun()
                
        with control_cols[1]:
            if st.button("📊 分析对话", use_container_width=True, disabled=len(st.session_state.dialogue_history) < 2):
                show_dialogue_analysis()
                
        # 评估设置
        st.write("#### 评估设置")
        auto_evaluate = st.checkbox("自动评估每轮对话", value=True, help="每轮对话后自动进行评估")
        
        # 目标测试集选择 - 用于保存对话轮次
        st.write("#### 目标测试集")
        test_set_list = get_test_set_list()
        if not test_set_list:
            st.warning("未找到测试集，请先创建测试集")
            selected_test_set = None
        else:
            selected_test_set = st.selectbox(
                "选择测试集",
                options=test_set_list,
                help="选择要将对话轮次保存到的测试集"
            )
            
            if selected_test_set:
                test_set = load_test_set(selected_test_set)
                if test_set:
                    st.success(f"已加载测试集: {selected_test_set}")
                    with st.expander("测试集信息", expanded=False):
                        st.write(f"**描述:** {test_set.get('description', '无描述')}")
                        st.write(f"**案例数量:** {len(test_set.get('cases', []))}")
                else:
                    st.error(f"无法加载测试集 {selected_test_set}")
        
        # 添加提示词自定义区域，可选填
        st.write("#### 提示词自定义变量")
        prompt_vars = {}
        with st.expander("自定义变量", expanded=False):
            var_keys = st.text_area(
                "变量名列表（每行一个）", 
                help="输入要自定义的变量名，每行一个"
            ).strip().split("\n")
            
            for key in var_keys:
                if key and key.strip():
                    prompt_vars[key.strip()] = st.text_input(f"变量 '{key.strip()}'", key=f"var_{key.strip()}")
        
    with col_chat:
        st.subheader("对话测试")
        
        # 对话容器
        chat_container = st.container(height=500, border=True)
        
        # 渲染对话历史
        with chat_container:
            if not st.session_state.dialogue_history:
                st.info("对话尚未开始。请在下方输入您的第一条消息。")
            else:
                for i, exchange in enumerate(st.session_state.dialogue_history):
                    st.markdown(f"**用户:** {exchange['user']}")
                    
                    with st.chat_message("assistant", avatar="🤖"):
                        st.markdown(exchange['assistant'])
                        
                        # 如果有评估结果，显示简要评分
                        if i < len(st.session_state.evaluation_results) and st.session_state.evaluation_results[i]:
                            eval_result = st.session_state.evaluation_results[i]
                            if "overall_score" in eval_result:
                                score = eval_result["overall_score"]
                                score_color = "green" if score >= 80 else "orange" if score >= 60 else "red"
                                st.markdown(f"<span style='color:{score_color};font-size:0.8em;'>回复质量评分: {score}/100</span>", unsafe_allow_html=True)
                                
                                # 显示评估详情按钮和保存轮次按钮
                                cols = st.columns(2)
                                with cols[0]:
                                    if st.button(f"查看详细评估 #{i+1}", key=f"detail_eval_{i}", use_container_width=True):
                                        show_evaluation_detail(eval_result, i+1)
                                
                                with cols[1]:
                                    if st.button(f"保存轮次 #{i+1}", key=f"save_turn_{i}", use_container_width=True):
                                        if selected_test_set:
                                            save_dialogue_turn_to_test_set(
                                                selected_test_set,
                                                i,
                                                st.session_state.dialogue_history,
                                                eval_result
                                            )
                                        else:
                                            st.error("请先选择目标测试集")
        
        # 用户输入区
        user_input = st.text_area("输入您的消息", key="user_msg_input", height=100)
        
        # 提交按钮
        if st.button("发送", type="primary", use_container_width=True):
            if not user_input:
                st.warning("请输入消息")
            elif not model:
                st.warning("请先选择一个模型")
            elif not selected_template_name:
                st.warning("请先选择一个提示词模板")
            else:
                with st.spinner("模型思考中..."):
                    # 准备对话历史以添加到提示词中
                    chat_records = format_chat_history(st.session_state.dialogue_history)
                    
                    # 准备模板变量
                    template_vars = {
                        "chat_records": chat_records,
                        **prompt_vars  # 添加用户自定义的变量
                    }
                    
                    # 渲染提示词模板
                    prompt_template = render_prompt_template(template, {"variables": template_vars}, {"variables": {}})
                    
                    # 创建消息列表
                    messages = []
                    
                    # 添加系统提示词
                    messages.append({"role": "system", "content": prompt_template})
                    
                    # 调用模型
                    client = get_client(provider)
                    params = {"temperature": temperature, "max_tokens": 2000}
                    
                    # 添加新的用户消息
                    messages.append({"role": "user", "content": user_input})
                    
                    try:
                        # 使用同步调用
                        response = execute_model_sync(
                            model=model,
                            provider=provider,
                            messages=messages,
                            params=params
                        )
                        
                        if "error" in response and response["error"]:
                            st.error(f"模型调用失败: {response['error']}")
                            return
                        
                        # 获取模型回复
                        assistant_response = response.get("text", "")
                        
                        # 更新对话历史
                        st.session_state.dialogue_history.append({
                            "user": user_input,
                            "assistant": assistant_response,
                            "model": model,
                            "turn": st.session_state.chat_turn + 1,
                            "timestamp": int(time.time()),
                            "prompt_template": prompt_template,
                            "usage": response.get("usage", {}),
                            "complete_messages": messages,
                            "chat_records": chat_records  # 保存当前轮次的对话历史
                        })
                        
                        # 增加对话回合数
                        st.session_state.chat_turn += 1
                        
                        # 如果启用了自动评估，评估此轮对话
                        if auto_evaluate:
                            evaluation = evaluate_dialogue_turn(
                                user_input, 
                                assistant_response, 
                                prompt_template,
                                st.session_state.chat_turn
                            )
                            st.session_state.evaluation_results.append(evaluation)
                            
                            # 保存提示词评分记录
                            if "scores" in evaluation:
                                st.session_state.prompt_ratings.append({
                                    "turn": st.session_state.chat_turn,
                                    "scores": evaluation["scores"],
                                    "overall": evaluation["overall_score"]
                                })
                        else:
                            # 如果未启用自动评估，添加一个空的占位符
                            st.session_state.evaluation_results.append(None)
                        
                        # 清空输入框 (通过重新渲染页面实现)
                        st.experimental_rerun()
                    
                    except Exception as e:
                        st.error(f"发生错误: {str(e)}")


def format_chat_history(history: List[Dict]) -> str:
    """将对话历史格式化为模板可用的格式，只保留最近5轮对话"""
    # 只保留最近的5轮对话
    recent_history = history[-5:] if len(history) > 5 else history
    
    formatted = ""
    
    for exchange in recent_history:
        formatted += f"用户: {exchange['user']}\n"
        formatted += f"助手: {exchange['assistant']}\n\n"
    
    return formatted.strip()


def save_dialogue_turn_to_test_set(test_set_name: str, turn_index: int, dialogue_history: List[Dict], evaluation: Dict = None) -> None:
    """将指定的对话轮次保存到测试集中
    
    Args:
        test_set_name: 测试集名称
        turn_index: 对话轮次索引
        dialogue_history: 完整对话历史
        evaluation: 评估结果（可选）
    """
    if turn_index < 0 or turn_index >= len(dialogue_history):
        st.error(f"无效的对话轮次索引: {turn_index}")
        return
    
    # 加载目标测试集
    test_set = load_test_set(test_set_name)
    if not test_set:
        st.error(f"无法加载测试集 {test_set_name}")
        return
    
    # 获取当前轮次对话
    turn_data = dialogue_history[turn_index]
    
    # 获取当前轮次的对话历史上下文
    chat_records = turn_data.get("chat_records", format_chat_history(dialogue_history[:turn_index]))
    
    # 创建新的测试用例
    new_case = {
        "id": generate_unique_id(),
        "description": f"对话轮次 #{turn_index+1} - {time.strftime('%Y-%m-%d %H:%M:%S')}",
        "user_input": turn_data.get("user", ""),
        "expected_output": "",  # 默认不设置期望输出
        "model_response": turn_data.get("assistant", ""),  # 保存模型实际响应
        "evaluation_criteria": {
            "relevance": "模型响应与用户提问的相关性",
            "helpfulness": "模型响应对解决用户问题的帮助程度",
            "accuracy": "模型响应中信息的准确性",
            "prompt_following": "模型遵循提示词指令的程度",
            "consistency": "模型回复与之前对话的一致性",
            "coherence": "模型回复的连贯性和逻辑性",
        },
        "variables": {
            "chat_records": chat_records,  # 保存对话历史上下文
            "model": turn_data.get("model", ""),
            "timestamp": turn_data.get("timestamp", int(time.time())),
        },
        "timestamp": int(time.time())
    }
    
    # 如果有评估结果，也保存下来
    if evaluation:
        new_case["evaluation"] = evaluation
    
    # 添加到测试集
    test_set = add_test_case(test_set, new_case)
    
    # 保存更新的测试集
    save_test_set(test_set_name, test_set)
    
    # 显示成功消息
    st.success(f"已将对话轮次 #{turn_index+1} 保存到测试集 '{test_set_name}'")


def evaluate_dialogue_turn(user_input: str, model_response: str, prompt_template: str, turn_number: int) -> Dict:
    """评估单轮对话质量"""
    evaluator = PromptEvaluator()
    
    # 设计针对对话的评估标准
    evaluation_criteria = {
        "relevance": "模型响应与用户提问的相关性(0-100分)",
        "helpfulness": "模型响应对解决用户问题的帮助程度(0-100分)",
        "accuracy": "模型响应中信息的准确性(0-100分)",
        "prompt_following": "模型遵循提示词指令的程度(0-100分)",
        "consistency": "模型回复与之前对话的一致性(0-100分)",
        "coherence": "模型回复的连贯性和逻辑性(0-100分)",
    }
    
    # 构建评估提示
    combined_prompt = f"用户问题:\n{user_input}\n\n提示词模板:\n{prompt_template}"
    
    # 因为是对话，没有标准答案，我们使用一个通用的期望
    expected_output = f"回合 {turn_number}：根据提示词和用户问题给出有帮助、相关且准确的回答"
    
    # 调用评估器
    evaluation = evaluator.evaluate_response_sync(
        model_response,
        expected_output,
        evaluation_criteria,
        combined_prompt
    )
    
    # 计算针对提示词和模型的问题诊断
    if "scores" in evaluation:
        scores = evaluation["scores"]
        
        # 分析可能的问题
        issues = []
        
        # 模型问题判断标准
        if scores.get("accuracy", 0) < 70 or scores.get("coherence", 0) < 70:
            issues.append({
                "type": "model",
                "severity": "high" if scores.get("accuracy", 0) < 50 else "medium",
                "description": "模型生成的内容可能不准确或不连贯",
                "suggestion": "考虑使用更高级的模型或调低temperature参数"
            })
            
        # 提示词问题判断标准
        if scores.get("prompt_following", 0) < 70:
            issues.append({
                "type": "prompt",
                "severity": "high" if scores.get("prompt_following", 0) < 50 else "medium",
                "description": "模型未能良好地遵循提示词指令",
                "suggestion": "明确提示词中的指令，增加详细的格式要求和约束"
            })
            
        if scores.get("consistency", 0) < 70:
            issues.append({
                "type": "prompt",
                "severity": "medium",
                "description": "模型回复与之前对话缺乏一致性",
                "suggestion": "在提示词中强调保持上下文一致性，或增加对话历史总结指令"
            })
            
        # 将问题分析添加到评估结果中
        evaluation["issues"] = issues
    
    return evaluation


def show_evaluation_detail(evaluation: Dict, turn_number: int):
    """显示详细的评估结果"""
    st.subheader(f"第 {turn_number} 轮对话评估结果")
    
    # 如果有错误信息，显示错误
    if "error" in evaluation:
        st.warning(f"评估过程遇到问题: {evaluation.get('error')}")
        return
    
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


def show_dialogue_analysis():
    """显示整个对话的分析结果"""
    if not st.session_state.dialogue_history or len(st.session_state.dialogue_history) < 2:
        st.warning("需要至少两轮对话才能进行分析")
        return
    
    st.subheader("🔍 对话分析")
    
    # 创建选项卡布局
    tab1, tab2, tab3 = st.tabs(["对话质量趋势", "提示词效果分析", "改进建议"])
    
    with tab1:
        st.write("#### 对话质量随时间变化趋势")
        
        # 提取评分数据
        if st.session_state.prompt_ratings:
            # 转换为pandas DataFrame以便分析
            df = pd.DataFrame([
                {
                    "turn": rating["turn"],
                    "overall": rating["overall"],
                    **rating["scores"]
                }
                for rating in st.session_state.prompt_ratings
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
        if st.session_state.prompt_ratings:
            # 计算提示词遵循度统计
            prompt_following_scores = [rating["scores"].get("prompt_following", 0) for rating in st.session_state.prompt_ratings]
            avg_following = sum(prompt_following_scores) / len(prompt_following_scores) if prompt_following_scores else 0
            
            # 显示提示词遵循度评分
            col1, col2 = st.columns(2)
            with col1:
                st.metric("平均提示词遵循度", f"{avg_following:.1f}/100")
                
            with col2:
                min_following = min(prompt_following_scores) if prompt_following_scores else 0
                st.metric("最低提示词遵循度", f"{min_following}/100")
            
            # 提示词问题汇总
            prompt_issues = []
            for i, eval_result in enumerate(st.session_state.evaluation_results):
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
        
        for eval_result in st.session_state.evaluation_results:
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
        
        # 生成综合报告
        if st.button("生成改进报告", use_container_width=True):
            with st.spinner("正在生成改进报告..."):
                report = generate_improvement_report(
                    st.session_state.dialogue_history,
                    st.session_state.evaluation_results
                )
                st.code(report, language="markdown")
                
                # 提供下载链接
                st.download_button(
                    label="下载报告",
                    data=report,
                    file_name=f"dialogue_analysis_{int(time.time())}.md",
                    mime="text/markdown"
                )


def generate_improvement_report(dialogue_history: List[Dict], evaluation_results: List[Dict]) -> str:
    """生成对话改进报告"""
    # 提取基本信息
    num_turns = len(dialogue_history)
    model_name = dialogue_history[0]["model"] if dialogue_history else "未知模型"
    
    # 计算平均分数
    avg_scores = {}
    overall_scores = []
    
    for eval_result in evaluation_results:
        if eval_result and "scores" in eval_result:
            for key, score in eval_result["scores"].items():
                if key != "prompt_efficiency":
                    avg_scores[key] = avg_scores.get(key, 0) + score
            
            if "overall_score" in eval_result:
                overall_scores.append(eval_result["overall_score"])
    
    # 计算平均值
    for key in avg_scores:
        avg_scores[key] /= len(evaluation_results) if evaluation_results else 1
    
    avg_overall = sum(overall_scores) / len(overall_scores) if overall_scores else 0
    
    # 收集问题和建议
    prompt_issues = []
    model_issues = []
    
    for eval_result in evaluation_results:
        if eval_result and "issues" in eval_result:
            for issue in eval_result["issues"]:
                if issue["type"] == "prompt" and issue not in prompt_issues:
                    prompt_issues.append(issue)
                elif issue["type"] == "model" and issue not in model_issues:
                    model_issues.append(issue)
    
    # 生成报告
    report = f"""# 多轮对话测试分析报告

## 基本信息
- **测试时间**: {time.strftime("%Y-%m-%d %H:%M:%S")}
- **对话轮数**: {num_turns}
- **使用模型**: {model_name}

## 评分摘要
- **总体评分**: {avg_overall:.1f}/100
"""
    
    # 添加各维度平均分
    report += "\n### 各维度平均分\n"
    for key, score in avg_scores.items():
        report += f"- **{key}**: {score:.1f}/100\n"
    
    # 添加问题分析
    report += "\n## 问题分析\n"
    
    if prompt_issues:
        report += "\n### 提示词问题\n"
        for issue in prompt_issues:
            report += f"- **严重程度**: {issue['severity']}\n"
            report += f"  - **描述**: {issue['description']}\n"
            report += f"  - **建议**: {issue['suggestion']}\n"
    else:
        report += "\n### 提示词问题\n- 未检测到明显问题\n"
    
    if model_issues:
        report += "\n### 模型问题\n"
        for issue in model_issues:
            report += f"- **严重程度**: {issue['severity']}\n"
            report += f"  - **描述**: {issue['description']}\n"
            report += f"  - **建议**: {issue['suggestion']}\n"
    else:
        report += "\n### 模型问题\n- 未检测到明显问题\n"
    
    # 添加改进建议综述
    report += "\n## 改进建议总结\n"
    
    # 提示词改进建议
    prompt_suggestions = list(set([issue["suggestion"] for issue in prompt_issues]))
    if prompt_suggestions:
        report += "\n### 提示词改进建议\n"
        for i, suggestion in enumerate(prompt_suggestions):
            report += f"{i+1}. {suggestion}\n"
    else:
        report += "\n### 提示词改进建议\n- 提示词表现良好，没有特别需要改进的地方\n"
    
    # 模型改进建议
    model_suggestions = list(set([issue["suggestion"] for issue in model_issues]))
    if model_suggestions:
        report += "\n### 模型使用建议\n"
        for i, suggestion in enumerate(model_suggestions):
            report += f"{i+1}. {suggestion}\n"
    else:
        report += "\n### 模型使用建议\n- 模型表现良好，没有特别需要调整的地方\n"
    
    return report