import streamlit as st
import json
import time
import pandas as pd
import uuid
from typing import Dict, Any, List, Tuple, Optional

from config import load_template, get_template_list, load_test_set, get_test_set_list, save_test_set
from utils.common import render_prompt_template, format_chat_history, generate_dialogue_improvement_report
from models.api_clients import get_provider_from_model
from ui.components import (
    select_single_model, 
    show_evaluation_detail,
    display_dialogue_analysis
)
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
        
    # 用于跟踪当前查看的评估详情（-1表示未查看任何评估）
    if "current_eval_view" not in st.session_state:
        st.session_state.current_eval_view = -1
    
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
                analyze_dialogue()
                
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
                                    # 如果当前正在查看这个评估，不显示查看按钮
                                    if st.session_state.current_eval_view == i+1:
                                        # 已经在查看详情中，显示详细评估内容
                                        continue_viewing = show_evaluation_detail(eval_result, i+1)
                                        if not continue_viewing:
                                            st.session_state.current_eval_view = -1
                                            st.experimental_rerun()
                                    else:
                                        # 否则显示查看按钮
                                        if st.button(f"查看详细评估 #{i+1}", key=f"detail_eval_{i}", use_container_width=True):
                                            st.session_state.current_eval_view = i+1
                                            st.experimental_rerun()
                                
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
        user_input = st.text_area("输入您的消息", key="user_msg_input", height=100, placeholder="按 Shift+Enter 换行", on_change=None)

        # 提交按钮和回车键兼容
        if st.button("发送", type="primary", use_container_width=True) or st.session_state.get("enter_pressed", False):
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
                    params = {"temperature": temperature, "max_tokens": 8000}

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
                            # 创建评估器
                            evaluator = PromptEvaluator()
                            evaluation = evaluator.evaluate_dialogue_turn(
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

        # 监听回车键事件
        st.session_state.enter_pressed = st.text_input("", key="hidden_input", on_change=lambda: st.session_state.update({"enter_pressed": True}))


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


def analyze_dialogue():
    """分析对话并显示结果"""
    if not st.session_state.dialogue_history or len(st.session_state.dialogue_history) < 2:
        st.warning("需要至少两轮对话才能进行分析")
        return
    
    # 使用组件显示对话分析
    prompt_suggestions, model_suggestions = display_dialogue_analysis(
        st.session_state.dialogue_history,
        st.session_state.evaluation_results,
        st.session_state.prompt_ratings
    )
    
    # 生成综合报告
    if st.button("生成改进报告", use_container_width=True):
        with st.spinner("正在生成改进报告..."):
            report = generate_dialogue_improvement_report(
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