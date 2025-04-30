# prompt_auto_optimization.py

import streamlit as st
import json
import pandas as pd
import asyncio
import time
from datetime import datetime
import plotly.express as px
import plotly.graph_objects as go
import threading
import queue

from config import get_template_list, load_template, get_test_set_list, load_test_set, save_template, get_available_models
from models.api_clients import get_client, get_provider_from_model
from models.token_counter import count_tokens, estimate_cost
from utils.evaluator import PromptEvaluator
from utils.optimizer import PromptOptimizer
from utils.auto_optimizer import AutomaticPromptOptimizer
from utils.common import (
    calculate_average_score, 
    get_dimension_scores, 
    create_dimension_radar_chart,
    run_test,
    save_optimized_template,
    render_prompt_template
)
from ui.components import (
    display_test_summary,
    display_response_tabs,
    display_evaluation_results,
    display_test_case_details
)

# 确保这个函数是在模块级定义的，而不是嵌套在其他函数中
def render_prompt_auto_optimization():
    st.title("🤖 自动提示词优化")
    
    st.markdown("""
    自动提示词优化使用AI持续评估和迭代改进提示词模板。系统会自动生成测试用例、评估结果、优化提示词，并持续进行迭代改进。
    
    ### 自动优化流程
    
    1. **选择初始提示词模板** - 作为优化的起点
    2. **选择对话模型** - 用于生成响应
    3. **选择评估模型** - 用于评估响应质量
    4. **选择迭代模型** - 用于优化提示词
    5. **开始自动优化** - 系统将持续优化提示词，直到达到设定轮次或手动停止
    """)
    
    # 检查是否有自动优化任务正在运行
    is_optimization_running = "auto_optimization_running" in st.session_state and st.session_state.auto_optimization_running
    
    # 步骤1: 选择提示词模板和模型
    if not is_optimization_running:
        st.subheader("步骤1: 选择提示词和模型")
        
        col1, col2 = st.columns(2)
        
        with col1:
            template_list = get_template_list()
            if not template_list:
                st.warning("未找到提示词模板，请先创建模板")
                return
                
            selected_template = st.selectbox(
                "选择提示词模板",
                template_list,
                key="auto_opt_template"
            )
            
            template = load_template(selected_template) if selected_template else None
            
            if template:
                with st.expander("查看提示词模板", expanded=False):
                    st.markdown(f"**名称**: {template.get('name', '')}")
                    st.markdown(f"**描述**: {template.get('description', '')}")
                    st.code(template.get('template', ''), language="markdown")
        
        with col2:
            # 获取可用模型列表
            available_models = get_available_models()
            
            # 将所有模型整合为(provider, model)元组的列表
            all_models = [(provider, model) for provider, models in available_models.items() for model in models]
            
            # 创建选项和映射
            model_options = [f"{model} ({provider})" for provider, model in all_models]
            model_map = {f"{model} ({provider})": (model, provider) for provider, model in all_models}
            
            # 选择对话模型
            selected_model_option = st.selectbox(
                "选择对话模型（用于生成响应）", 
                model_options,
                key="auto_opt_model"
            )
            
            if selected_model_option:
                selected_model, selected_provider = model_map[selected_model_option]
            else:
                selected_model = ""
                selected_provider = ""
            
            # 选择评估模型
            eval_model_option = st.selectbox(
                "选择评估模型（用于评估响应质量）", 
                model_options,
                key="auto_opt_eval_model",
                index=model_options.index(selected_model_option) if selected_model_option in model_options else 0
            )
            
            if eval_model_option:
                eval_model, eval_provider = model_map[eval_model_option]
            else:
                eval_model = selected_model
                eval_provider = selected_provider
            
            # 选择迭代模型
            iter_model_option = st.selectbox(
                "选择迭代模型（用于优化提示词）", 
                model_options,
                key="auto_opt_iter_model",
                index=model_options.index(selected_model_option) if selected_model_option in model_options else 0
            )
            
            if iter_model_option:
                iter_model, iter_provider = model_map[iter_model_option]
            else:
                iter_model = selected_model
                iter_provider = selected_provider
    
        # 步骤2: 配置自动优化参数
        st.subheader("步骤2: 配置自动优化参数")
        
        col1, col2 = st.columns(2)
        
        with col1:
            max_iterations = st.number_input("最大迭代轮次", min_value=1, max_value=1000, value=10, step=1)
            test_cases_per_iter = st.number_input("每轮测试用例数", min_value=1, max_value=50, value=3, step=1)
            optimization_strategy = st.selectbox(
                "优化策略",
                ["balanced", "accuracy", "completeness", "conciseness"],
                format_func=lambda x: {
                    "balanced": "平衡优化 (准确性、完整性和简洁性)",
                    "accuracy": "优化准确性",
                    "completeness": "优化完整性",
                    "conciseness": "优化简洁性"
                }.get(x, x)
            )
        
        with col2:
            temperature = st.slider("温度 (Temperature)", 0.0, 2.0, 0.7, 0.1)
            auto_save_best = st.checkbox("自动保存每轮最佳提示词", value=True)
            log_detail_level = st.selectbox(
                "日志详细程度",
                ["简洁", "标准", "详细"],
                index=1
            )
        
        # 步骤3: 开始自动优化
        st.subheader("步骤3: 开始自动优化")
        
        # 初始化或重置会话状态变量，用于存储优化结果
        if "auto_optimization_results" not in st.session_state:
            st.session_state.auto_optimization_results = {"iterations": [], "current_best": None, "logs": []}
        
        if "auto_optimization_paused" not in st.session_state:
            st.session_state.auto_optimization_paused = False
            
        col1, col2 = st.columns([3, 1])
        
        with col1:
            if st.button("🚀 启动自动优化", type="primary"):
                # 检查必要的参数是否已设置
                if not selected_template or not selected_model:
                    st.error("请先选择提示词模板和模型")
                    return
                
                # 重置优化结果以开始新的优化过程
                st.session_state.auto_optimization_results = {"iterations": [], "current_best": None, "logs": []}
                st.session_state.auto_optimization_running = True
                st.session_state.auto_optimization_paused = False
                st.session_state.auto_optimization_logs = []
                
                # 存储优化配置以便在会话刷新后恢复
                st.session_state.auto_optimization_config = {
                    "template": template,
                    "model": selected_model,
                    "provider": selected_provider,
                    "eval_model": eval_model,
                    "eval_provider": eval_provider,
                    "iter_model": iter_model,
                    "iter_provider": iter_provider,
                    "max_iterations": max_iterations,
                    "test_cases_per_iter": test_cases_per_iter,
                    "optimization_strategy": optimization_strategy,
                    "temperature": temperature,
                    "auto_save_best": auto_save_best,
                    "log_detail_level": log_detail_level,
                    "start_time": time.time()
                }
                
                # 重新加载页面以显示优化过程界面
                st.rerun()
        
        with col2:
            if st.button("清除历史记录"):
                if "auto_optimization_results" in st.session_state:
                    del st.session_state.auto_optimization_results
                if "auto_optimization_config" in st.session_state:
                    del st.session_state.auto_optimization_config
                if "auto_optimization_logs" in st.session_state:
                    del st.session_state.auto_optimization_logs
                st.success("已清除历史记录")
                time.sleep(1)
                st.rerun()
    else:
        # 显示正在运行的自动优化过程
        display_running_optimization()

# 辅助函数定义
def display_running_optimization():
    """显示正在运行的自动优化过程"""
    config = st.session_state.auto_optimization_config
    
    # 显示当前配置摘要
    st.subheader("自动优化进行中")
    
    col1, col2, col3 = st.columns(3)
    with col1:
        st.info(f"**提示词模板**: {config['template'].get('name', '')}")
        st.info(f"**对话模型**: {config['model']} ({config['provider']})")
    with col2:
        st.info(f"**评估模型**: {config['eval_model']} ({config['eval_provider']})")
        st.info(f"**迭代模型**: {config['iter_model']} ({config['iter_provider']})")
    with col3:
        st.info(f"**优化策略**: {config['optimization_strategy']}")
        st.info(f"**最大轮次**: {config['max_iterations']}")
    
    # 创建一个对象来处理自动优化逻辑
    if "auto_optimizer" not in st.session_state:
        st.session_state.auto_optimizer = AutomaticPromptOptimizer(
            initial_prompt=config['template'].get('template', ''),
            model=config['model'],
            provider=config['provider'],
            eval_model=config['eval_model'],
            eval_provider=config['eval_provider'],
            iter_model=config['iter_model'],
            iter_provider=config['iter_provider'],
            max_iterations=config['max_iterations'],
            test_cases_per_iter=config['test_cases_per_iter'],
            optimization_strategy=config['optimization_strategy'],
            temperature=config['temperature']
        )
    
    # 进度条和控制按钮
    overall_progress = st.progress(0.0)
    status_text = st.empty()
    
    # 控制按钮行
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        if st.session_state.auto_optimization_paused:
            if st.button("▶️ 继续优化", type="primary"):
                st.session_state.auto_optimization_paused = False
                st.rerun()
        else:
            if st.button("⏸️ 暂停优化"):
                st.session_state.auto_optimization_paused = True
                st.rerun()
    
    with col2:
        if st.button("🛑 终止优化"):
            st.session_state.auto_optimization_running = False
            if "auto_optimizer" in st.session_state:
                del st.session_state.auto_optimizer
            st.success("优化已终止")
            time.sleep(1)
            st.rerun()
    
    with col3:
        if st.button("💾 保存当前最佳提示词"):
            if "auto_optimization_results" in st.session_state and st.session_state.auto_optimization_results.get("current_best"):
                best_prompt = st.session_state.auto_optimization_results["current_best"]["prompt"]
                best_score = st.session_state.auto_optimization_results["current_best"].get("score", 0)
                
                from utils.common import save_optimized_template
                new_name = save_optimized_template(config['template'], {"prompt": best_prompt}, int(time.time()) % 10000)
                st.success(f"已保存最佳提示词 (得分: {best_score:.2f}) 为新模板: {new_name}")
    
    with col4:
        if st.button("🧪 手动测试当前最佳提示词"):
            if "auto_optimization_results" in st.session_state and st.session_state.auto_optimization_results.get("current_best"):
                # 将当前最佳提示词设置为会话状态，以便在交互式测试页面使用
                best_prompt = st.session_state.auto_optimization_results["current_best"]["prompt"]
                
                # 创建一个临时模板
                temp_template = dict(config['template'])
                temp_template["name"] = f"{config['template'].get('name', '')}的优化版本"
                temp_template["description"] = f"自动优化生成的提示词版本，优化时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
                temp_template["template"] = best_prompt
                
                # 设置会话状态以在交互测试页面使用
                st.session_state.temp_test_template = temp_template
                st.session_state.temp_test_model = config['model']
                st.session_state.temp_test_provider = config['provider']
                
                # 跳转到交互式测试页面
                st.session_state.page = "prompt_interactive_test"
                st.session_state.from_auto_optimization = True
                st.rerun()
    
    # 显示日志输出
    st.subheader("优化日志")
    log_container = st.container()
    
    # 显示迭代结果
    st.subheader("优化迭代进展")
    iterations_container = st.container()
    
    # 如果未暂停，运行自动优化的下一步
    if not st.session_state.auto_optimization_paused:
        run_optimization_step(overall_progress, status_text, log_container, iterations_container)

def run_optimization_step(progress_bar, status_text, log_container, iterations_container):
    """运行自动优化的一个步骤"""
    
    # 获取配置
    config = st.session_state.auto_optimization_config
    auto_optimizer = st.session_state.auto_optimizer
    
    # 更新进度条和状态文本
    current_iter = auto_optimizer.current_iteration
    progress = min(current_iter / config['max_iterations'], 1.0)
    progress_bar.progress(progress)
    
    # 如果还未完成最大迭代轮次，执行下一步优化
    if current_iter < config['max_iterations'] and not auto_optimizer.is_completed():
        # 计算运行时间
        elapsed_time = time.time() - config['start_time']
        status_text.info(f"正在执行第 {current_iter + 1}/{config['max_iterations']} 轮优化... 已用时间: {elapsed_time:.1f}秒")
        
        # 执行一步优化，收集结果
        result = auto_optimizer.run_single_iteration()
        
        # 记录日志
        if "auto_optimization_logs" not in st.session_state:
            st.session_state.auto_optimization_logs = []
        
        st.session_state.auto_optimization_logs.extend(auto_optimizer.get_latest_logs())
        
        # 更新优化结果
        if "auto_optimization_results" not in st.session_state:
            st.session_state.auto_optimization_results = {"iterations": [], "current_best": None, "logs": []}
        
        if result:
            # 添加到迭代结果中
            st.session_state.auto_optimization_results["iterations"].append(result)
            
            # 检查是否是新的最佳结果
            if (not st.session_state.auto_optimization_results["current_best"] or 
                result.get("score", 0) > st.session_state.auto_optimization_results["current_best"].get("score", 0)):
                st.session_state.auto_optimization_results["current_best"] = result
                
                # 如果配置了自动保存最佳提示词
                if config.get("auto_save_best", True):
                    from utils.common import save_optimized_template
                    new_name = save_optimized_template(
                        config['template'], 
                        {"prompt": result["prompt"]}, 
                        current_iter
                    )
                    # 记录自动保存事件
                    st.session_state.auto_optimization_logs.append({
                        "time": time.time(),
                        "level": "INFO",
                        "message": f"自动保存最佳提示词 (得分: {result['score']:.2f}) 为新模板: {new_name}"
                    })
        
        # 显示最新的日志
        display_optimization_logs(log_container)
        
        # 显示迭代结果
        display_optimization_iterations(iterations_container)
        
        # 如果还未完成，等待1秒后重新加载页面以继续优化
        if current_iter + 1 < config['max_iterations'] and not auto_optimizer.is_completed():
            time.sleep(1)  # 用于模拟优化过程并防止页面刷新太快
            st.rerun()
        else:
            # 已完成所有迭代，更新状态
            status_text.success(f"✅ 自动优化完成! 共执行 {current_iter + 1} 轮优化，用时 {elapsed_time:.1f}秒")
            st.balloons()
            
            # 标记优化已完成但保持运行状态，以便查看结果
            auto_optimizer.mark_completed()
    else:
        # 优化已经完成，显示最终状态
        elapsed_time = time.time() - config['start_time']
        status_text.success(f"✅ 自动优化完成! 共执行 {current_iter} 轮优化，用时 {elapsed_time:.1f}秒")
        
        # 显示日志和迭代结果
        display_optimization_logs(log_container)
        display_optimization_iterations(iterations_container)

def display_optimization_logs(container):
    """在容器中显示优化日志"""
    if "auto_optimization_logs" in st.session_state:
        logs = st.session_state.auto_optimization_logs
        
        # 确定日志详细程度
        if "auto_optimization_config" in st.session_state:
            detail_level = st.session_state.auto_optimization_config.get("log_detail_level", "标准")
        else:
            detail_level = "标准"
        
        # 根据详细程度过滤日志
        if detail_level == "简洁":
            # 只显示INFO级别以上的重要日志
            filtered_logs = [log for log in logs if log.get("level") in ["INFO", "WARNING", "ERROR"]]
        elif detail_level == "详细":
            # 显示所有日志
            filtered_logs = logs
        else:
            # 标准级别，显示DEBUG以上级别
            filtered_logs = [log for log in logs if log.get("level") in ["DEBUG", "INFO", "WARNING", "ERROR"]]
        
        # 限制显示最近的50条日志
        display_logs = filtered_logs[-50:] if len(filtered_logs) > 50 else filtered_logs
        
        with container:
            for log in display_logs:
                timestamp = datetime.fromtimestamp(log.get("time", time.time())).strftime('%H:%M:%S')
                level = log.get("level", "INFO")
                message = log.get("message", "")
                
                if level == "ERROR":
                    st.error(f"{timestamp} - {message}")
                elif level == "WARNING":
                    st.warning(f"{timestamp} - {message}")
                elif level == "INFO":
                    st.info(f"{timestamp} - {message}")
                else:
                    st.text(f"{timestamp} - [{level}] {message}")

def display_optimization_iterations(container):
    """在容器中显示优化迭代结果"""
    if "auto_optimization_results" in st.session_state:
        results = st.session_state.auto_optimization_results
        iterations = results.get("iterations", [])
        current_best = results.get("current_best")
        
        with container:
            if current_best:
                st.subheader(f"当前最佳提示词 (得分: {current_best.get('score', 0):.2f})")
                st.code(current_best.get("prompt", ""), language="markdown")
                st.divider()
            
            # 使用tabs来展示每一轮的结果
            if iterations:
                tabs = st.tabs([f"第{i+1}轮" for i in range(len(iterations))])
                
                for i, (tab, iteration) in enumerate(zip(tabs, iterations)):
                    with tab:
                        col1, col2 = st.columns([1, 1])
                        
                        with col1:
                            st.markdown(f"**得分**: {iteration.get('score', 0):.2f}")
                            st.markdown(f"**测试用例数**: {len(iteration.get('test_cases', []))}")
                            st.markdown(f"**优化策略**: {iteration.get('strategy', '未指定')}")
                            
                            # 如果有测试结果，显示详细信息
                            test_results = iteration.get("test_results", [])
                            if test_results:
                                with st.expander("查看测试结果详情"):
                                    for j, result in enumerate(test_results):
                                        st.markdown(f"**测试 {j+1}**")
                                        st.markdown(f"- 用户输入: {result.get('user_input', '')}")
                                        st.markdown(f"- 模型响应: {result.get('model_response', '')[:100]}...")
                                        st.markdown(f"- 得分: {result.get('score', 0):.2f}")
                                        st.markdown("---")
                        
                        with col2:
                            st.subheader("提示词")
                            st.code(iteration.get("prompt", ""), language="markdown")
                            
                            # 添加一个按钮来手动测试这个提示词
                            if st.button(f"🧪 测试此提示词", key=f"test_iter_{i}"):
                                # 创建一个临时模板
                                config = st.session_state.auto_optimization_config
                                temp_template = dict(config['template'])
                                temp_template["name"] = f"{config['template'].get('name', '')}的第{i+1}轮优化版本"
                                temp_template["description"] = f"自动优化第{i+1}轮生成的提示词版本"
                                temp_template["template"] = iteration.get("prompt", "")
                                
                                # 设置会话状态以在交互测试页面使用
                                st.session_state.temp_test_template = temp_template
                                st.session_state.temp_test_model = config['model']
                                st.session_state.temp_test_provider = config['provider']
                                
                                # 跳转到交互式测试页面
                                st.session_state.page = "prompt_interactive_test"
                                st.session_state.from_auto_optimization = True
                                st.rerun()
            else:
                st.info("尚无优化迭代结果，请等待...")

# 确保模块导出了render_prompt_auto_optimization函数
__all__ = ['render_prompt_auto_optimization']