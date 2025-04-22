# ui/test_runner.py
import streamlit as st
import pandas as pd
import asyncio
from datetime import datetime
import time
import json
from config import get_template_list, load_template, get_test_set_list, load_test_set, save_result, get_available_models
from models.api_clients import get_client, get_provider_from_model
from models.token_counter import count_tokens, estimate_cost
from utils.evaluator import PromptEvaluator
from utils.common import run_test
from ui.components.layout import page_header, tabs_section
from ui.components.selectors import select_single_model, select_multiple_models, select_template, select_test_set
from ui.components.cards import info_card, result_card, display_test_summary, display_response_tabs, display_evaluation_results
from ui.components.tables import results_table
from ui.components.forms import test_config_form

def render_test_runner():
    """测试运行页面"""
    # 使用布局组件显示页面标题
    page_header("测试运行", "运行提示词测试并评估结果", "🧪")
    
    # 初始化会话状态
    if "test_mode" not in st.session_state:
        st.session_state.test_mode = "single_prompt_multi_model"
    
    if "test_results" not in st.session_state:
        st.session_state.test_results = None
    
    if "test_is_running" not in st.session_state:
        st.session_state.test_is_running = False
    
    # 定义各标签页渲染函数
    def render_test_config():
        """渲染测试配置标签页"""
        st.markdown("## 测试配置")
        
        # 测试模式选择
        test_mode = st.radio(
            "测试模式", 
            ["single_prompt_multi_model", "multi_prompt_single_model"],
            format_func=lambda x: "单模板多模型" if x == "single_prompt_multi_model" else "多模板单模型",
            key="test_mode_selector",
            horizontal=True
        )
        
        st.session_state.test_mode = test_mode
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.subheader("选择提示词模板")
            template_list = get_template_list()
            
            if not template_list:
                st.warning("未找到提示词模板，请先创建模板")
                return
            
            # 根据测试模式选择单个或多个模板
            if test_mode == "single_prompt_multi_model":
                selected_template = select_template(
                    template_list, 
                    "选择模板", 
                    "test_template", 
                    "选择要测试的提示词模板"
                )
                if selected_template:
                    st.session_state.selected_templates = [selected_template]
                
                # 显示选中模板的信息
                if "selected_templates" in st.session_state and st.session_state.selected_templates:
                    try:
                        template = load_template(st.session_state.selected_templates[0])
                        if template:
                            st.success(f"已选择模板: {template.get('name', '')}")
                            with st.expander("查看模板详情", expanded=False):
                                st.markdown(f"**描述**: {template.get('description', '无描述')}")
                                st.markdown("**模板内容**:")
                                st.code(template.get("template", ""), language="markdown")
                                
                                # 显示变量
                                if template.get("variables"):
                                    st.markdown("**变量**:")
                                    for var_name, var_config in template.get("variables", {}).items():
                                        st.markdown(f"- **{var_name}**: {var_config.get('description', '')} (默认: `{var_config.get('default', '')}`)")
                    except Exception as e:
                        st.error(f"加载模板时出错: {str(e)}")
            else:
                selected_templates = select_template(
                    template_list, 
                    "选择多个模板", 
                    "test_templates", 
                    "选择要测试的多个提示词模板",
                    allow_multiple=True
                )
                st.session_state.selected_templates = selected_templates
                
                # 显示选中模板数量
                if "selected_templates" in st.session_state and st.session_state.selected_templates:
                    st.success(f"已选择 {len(st.session_state.selected_templates)} 个模板")
                    with st.expander("查看选中的模板", expanded=False):
                        for template_name in st.session_state.selected_templates:
                            st.markdown(f"- {template_name}")
        
        with col2:
            st.subheader("选择测试集")
            test_set_list = get_test_set_list()
            
            if not test_set_list:
                st.warning("未找到测试集，请先创建测试集")
                return
            
            selected_test_set = select_test_set(
                test_set_list, 
                "选择测试集", 
                "test_set", 
                "选择要使用的测试集"
            )
            st.session_state.selected_test_set = selected_test_set
            
            # 显示选中测试集的信息
            if "selected_test_set" in st.session_state and st.session_state.selected_test_set:
                try:
                    test_set = load_test_set(st.session_state.selected_test_set)
                    if test_set:
                        st.success(f"已选择测试集: {test_set.get('name', '')}")
                        with st.expander("查看测试集详情", expanded=False):
                            st.markdown(f"**描述**: {test_set.get('description', '无描述')}")
                            st.markdown(f"**测试用例数**: {len(test_set.get('cases', []))}")
                            
                            # 显示测试用例摘要
                            if test_set.get("cases"):
                                test_cases = []
                                for case in test_set.get("cases", []):
                                    test_cases.append({
                                        "ID": case.get("id", ""),
                                        "描述": case.get("description", ""),
                                        "评估标准数": len(case.get("evaluation_criteria", {}))
                                    })
                                
                                if test_cases:
                                    st.dataframe(pd.DataFrame(test_cases), use_container_width=True)
                except Exception as e:
                    st.error(f"加载测试集时出错: {str(e)}")
    
    def render_model_selection():
        """渲染模型选择标签页"""
        st.markdown("## 模型选择")
        
        # 获取测试模式
        test_mode = st.session_state.get("test_mode", "single_prompt_multi_model")
        
        if test_mode == "single_prompt_multi_model":
            st.markdown("### 选择多个模型")
            st.markdown("在此模式下，将使用单个提示词模板测试多个模型")
            
            selected_models = select_multiple_models(
                "test_models", 
                "选择要测试的模型（可多选）"
            )
            
            st.session_state.selected_models = selected_models
            
            # 显示选中的模型
            if selected_models:
                st.success(f"已选择 {len(selected_models)} 个模型")
                with st.expander("查看选中的模型", expanded=False):
                    for model_info in selected_models:
                        st.markdown(f"- {model_info['model']} ({model_info['provider']})")
            else:
                st.warning("请选择至少一个模型")
        else:
            st.markdown("### 选择单个模型")
            st.markdown("在此模式下，将使用多个提示词模板测试单个模型")
            
            model, provider = select_single_model(
                "test_model", 
                "选择要测试的模型"
            )
            
            if model and provider:
                st.session_state.selected_models = [{"model": model, "provider": provider}]
                st.success(f"已选择模型: {model} ({provider})")
            else:
                st.warning("请选择一个模型")
    
    def render_test_execution():
        """渲染测试执行标签页"""
        st.markdown("## 测试执行")
        
        # 检查是否已选择所需元素
        has_templates = "selected_templates" in st.session_state and st.session_state.selected_templates
        has_test_set = "selected_test_set" in st.session_state and st.session_state.selected_test_set
        has_models = "selected_models" in st.session_state and st.session_state.selected_models
        
        if not (has_templates and has_test_set and has_models):
            missing = []
            if not has_templates:
                missing.append("提示词模板")
            if not has_test_set:
                missing.append("测试集")
            if not has_models:
                missing.append("模型")
            
            st.warning(f"请先在前面的标签页中选择{', '.join(missing)}")
            return
        
        # 显示测试配置摘要
        with st.expander("测试配置摘要", expanded=True):
            col1, col2, col3 = st.columns(3)
            
            with col1:
                st.markdown("**提示词模板**")
                for template_name in st.session_state.selected_templates:
                    st.markdown(f"- {template_name}")
            
            with col2:
                st.markdown("**测试集**")
                st.markdown(f"- {st.session_state.selected_test_set}")
                
                # 加载测试集信息
                try:
                    test_set = load_test_set(st.session_state.selected_test_set)
                    if test_set:
                        st.markdown(f"- 测试用例数: {len(test_set.get('cases', []))}")
                except Exception:
                    pass
            
            with col3:
                st.markdown("**模型**")
                for model_info in st.session_state.selected_models:
                    st.markdown(f"- {model_info['model']} ({model_info['provider']})")
        
        # 测试选项设置
        with st.expander("测试选项", expanded=True):
            col1, col2 = st.columns(2)
            
            with col1:
                # 模型参数
                st.markdown("**模型参数**")
                temperature = st.slider(
                    "Temperature", 
                    min_value=0.0, 
                    max_value=1.0, 
                    value=0.7, 
                    step=0.1,
                    help="控制输出的随机性，较高的值将使输出更随机，较低的值使输出更确定"
                )
                
                max_tokens = st.number_input(
                    "最大输出Token数", 
                    min_value=1, 
                    max_value=4096, 
                    value=1024,
                    help="限制模型响应的最大长度"
                )
                
                # 添加测试运行次数配置
                num_runs = st.number_input(
                    "每个配置运行次数", 
                    min_value=1, 
                    max_value=10, 
                    value=1,
                    help="每个模型-模板-测试用例组合运行的次数"
                )
            
            with col2:
                # 评估选项
                st.markdown("**评估选项**")
                run_evaluation = st.checkbox(
                    "自动评估响应", 
                    value=True,
                    help="使用评估模型对生成的响应进行评分"
                )
                
                if run_evaluation:
                    # 使用统一的评估模型选择器
                    from ui.components.selectors import select_evaluator_model
                    evaluator_model, evaluator_provider = select_evaluator_model(
                        "test_evaluator", 
                        "选择用于评估响应质量的模型"
                    )
                else:
                    evaluator_model = None
                    evaluator_provider = None
        
        # 运行测试按钮
        run_col1, run_col2 = st.columns([2, 1])
        
        with run_col1:
            if st.button("▶️ 开始测试", key="start_test_btn", use_container_width=True, type="primary"):
                # 设置状态为正在运行
                st.session_state.test_is_running = True
                st.session_state.test_results = None
                
                # 收集测试配置
                test_config = {
                    "templates": st.session_state.selected_templates,
                    "test_set": st.session_state.selected_test_set,
                    "models": st.session_state.selected_models,
                    "params": {
                        "temperature": temperature,
                        "max_tokens": max_tokens,
                        "num_runs": num_runs  # 添加运行次数
                    },
                    "evaluation": {
                        "run": run_evaluation,
                        "model": evaluator_model,
                        "provider": evaluator_provider
                    },
                    "timestamp": datetime.now().strftime("%Y%m%d_%H%M%S")
                }
                
                # 存储测试配置
                st.session_state.test_config = test_config
                st.experimental_rerun()
        
        with run_col2:
            if st.button("🔄 重置", key="reset_test_btn", use_container_width=True):
                # 重置测试状态
                st.session_state.test_is_running = False
                st.session_state.test_results = None
                st.session_state.test_config = None
                st.experimental_rerun()
        
        # 执行测试
        if st.session_state.get("test_is_running", False):
            with st.spinner("正在运行测试..."):
                # 使用asyncio运行异步测试函数
                test_results = run_test_with_progress(st.session_state.test_config)
                st.session_state.test_results = test_results
                st.session_state.test_is_running = False
                
                if test_results:
                    # 保存测试结果
                    result_name = f"test_results_{st.session_state.test_config['timestamp']}.json"
                    save_result(result_name, test_results)
                    st.session_state.last_result = result_name
                    
                    # 显示成功消息
                    st.success("测试完成！")
                    
                    # 设置当前标签页索引为结果标签页（索引为3）
                    st.session_state.active_tab = 3
                else:
                    st.error("测试执行失败，请检查日志")
                
                st.experimental_rerun()
    
    def render_test_results():
        """渲染测试结果标签页"""
        st.markdown("## 测试结果")
        
        # 检查是否有测试结果
        if not st.session_state.get("test_results"):
            st.info('尚未运行测试或没有测试结果。请在"测试执行"标签页运行测试。')
            return
        
        # 获取测试结果
        results = st.session_state.test_results
        
        # 显示测试结果摘要
        st.markdown("### 测试结果摘要")
        
        # 创建摘要卡片
        summary_cols = st.columns(4)
        
        with summary_cols[0]:
            result_card(
                "测试完成时间", 
                results.get("timestamp", "未知"),
                "测试执行的时间戳"
            )
        
        with summary_cols[1]:
            result_card(
                "测试模板数", 
                len(results.get("templates", {})),
                "参与测试的提示词模板数量"
            )
        
        with summary_cols[2]:
            result_card(
                "测试用例数", 
                len(results.get("test_cases", [])),
                "执行的测试用例数量"
            )
        
        with summary_cols[3]:
            result_card(
                "测试模型数", 
                len(results.get("models", [])),
                "参与测试的模型数量"
            )
        
        # 显示测试用例结果
        st.markdown("### 测试用例结果")
        
        # 创建测试用例选择器
        test_cases = results.get("test_cases", [])
        if not test_cases:
            st.warning("没有找到测试用例结果")
            return
        
        case_options = [f"{case.get('id', '')} - {case.get('description', '')}" for case in test_cases]
        selected_case_option = st.selectbox(
            "选择测试用例查看详细结果",
            case_options,
            key="select_result_case"
        )
        
        # 获取选中的测试用例
        selected_case_id = selected_case_option.split(" - ")[0] if selected_case_option else None
        selected_case = next((case for case in test_cases if case.get("id") == selected_case_id), None)
        
        if selected_case:
            # 显示用例详情
            st.markdown(f"#### 测试用例: {selected_case.get('description', '')}")
            
            # 创建响应标签页
            if "responses" in selected_case and selected_case["responses"]:
                display_response_tabs(selected_case["responses"], key_prefix=f"case_{selected_case_id}")
            else:
                st.info("此测试用例没有响应数据")
            
            # 显示评估结果
            if "evaluation" in selected_case:
                st.markdown("#### 评估结果")
                display_evaluation_results(selected_case["evaluation"], key_prefix=f"eval_{selected_case_id}")
            
        # 模型比较
        st.markdown("### 模型比较")
        
        # 准备模型比较数据
        models_data = prepare_model_comparison_data(results)
        
        if models_data:
            # 创建模型比较表格
            st.dataframe(pd.DataFrame(models_data), use_container_width=True)
            
            # 可以添加图表展示
            # TODO: 添加模型比较图表
        else:
            st.info("无法创建模型比较数据，可能缺少评估结果")
    
    # 设置标签页
    tabs_config = [
        {"title": "测试配置", "content": render_test_config},
        {"title": "模型选择", "content": render_model_selection},
        {"title": "测试执行", "content": render_test_execution},
        {"title": "测试结果", "content": render_test_results}
    ]
    
    tabs_section(tabs_config)

# 辅助函数
def run_test_with_progress(test_config):
    """运行测试并显示进度"""
    # 加载测试集
    test_set = load_test_set(test_config["test_set"])
    if not test_set or "cases" not in test_set:
        st.error("无法加载测试集或测试集不包含测试用例")
        return None
    
    # 准备结果结构
    results = {
        "timestamp": test_config["timestamp"],
        "templates": {},
        "models": test_config["models"],
        "test_cases": [],
        "total_tokens": 0,
        "total_responses": 0,
        "total_evaluations": 0
    }
    
    # 加载模板
    for template_name in test_config["templates"]:
        template = load_template(template_name)
        if template:
            results["templates"][template_name] = template
    
    # 准备测试用例
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    total_cases = len(test_set["cases"])
    total_models = len(test_config["models"])
    total_templates = len(test_config["templates"])
    num_runs = test_config["params"].get("num_runs", 1)  # 获取运行次数，默认为1
    
    total_tests = total_cases * total_models * total_templates
    completed_tests = 0
    
    # 处理每个测试用例
    for i, case in enumerate(test_set["cases"]):
        case_result = {
            "id": case.get("id", f"case_{i}"),
            "description": case.get("description", ""),
            "user_input": case.get("user_input", ""),
            "expected_output": case.get("expected_output", ""),
            "evaluation_criteria": case.get("evaluation_criteria", {}),
            "responses": []
        }
        
        status_text.text(f"测试用例 {i+1}/{total_cases}: {case.get('description', '')}")
        
        # 对每个模板和模型组合运行测试
        for template_name in test_config["templates"]:
            template = results["templates"].get(template_name)
            if not template:
                st.warning(f"无法加载模板: {template_name}，跳过")
                continue
            
            for model_info in test_config["models"]:
                model = model_info["model"]
                provider = model_info["provider"]
                
                status_text.text(f"测试用例 {i+1}/{total_cases}, 模板: {template_name}, 模型: {model}")
                
                try:
                    # 调用修改后的run_test函数
                    test_results = run_test(
                        template=template,  # 提示词模板
                        model=model,  # 模型名称
                        test_set={  # 单独为这个测试用例创建一个测试集
                            "cases": [case],
                            "variables": test_set.get("variables", {})
                        },
                        model_provider=provider,  # 模型提供商
                        repeat_count=num_runs,  # 重复次数
                        temperature=test_config["params"].get("temperature", 0.7)  # 温度参数
                    )
                    
                    # 处理测试结果
                    if test_results and "test_cases" in test_results and test_results["test_cases"]:
                        case_test_results = test_results["test_cases"][0]  # 只有一个测试用例
                        
                        # 提取所有响应
                        for resp_data in case_test_results.get("responses", []):
                            # 创建响应对象
                            response = {
                                "model": model,
                                "provider": provider,
                                "template": template_name,
                                "content": resp_data.get("response", ""),
                                "error": resp_data.get("error"),
                                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                                "run_index": resp_data.get("attempt", 1),
                                "tokens": {
                                    "prompt": resp_data.get("usage", {}).get("prompt_tokens", 0),
                                    "completion": resp_data.get("usage", {}).get("completion_tokens", 0),
                                    "total": resp_data.get("usage", {}).get("total_tokens", 0)
                                }
                            }
                            
                            # 添加评估结果
                            if resp_data.get("evaluation"):
                                response["evaluation"] = resp_data["evaluation"]
                                results["total_evaluations"] += 1
                            
                            # 添加到响应列表
                            case_result["responses"].append(response)
                            results["total_responses"] += 1
                            
                            # 更新token统计
                            results["total_tokens"] += response["tokens"]["total"]
                
                except Exception as e:
                    st.error(f"运行测试时出错 (模板: {template_name}, 模型: {model}): {str(e)}")
                    # 添加错误信息
                    case_result["responses"].append({
                        "model": model,
                        "provider": provider,
                        "template": template_name,
                        "content": f"错误: {str(e)}",
                        "error": True,
                        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        "run_index": 1
                    })
                
                # 更新进度
                completed_tests += 1
                progress_bar.progress(completed_tests / total_tests)
        
        # 计算用例的整体评估（如果有多个响应）
        if case_result["responses"] and any("evaluation" in resp for resp in case_result["responses"]):
            # 收集有评估结果的响应
            evaluated_responses = [resp for resp in case_result["responses"] if "evaluation" in resp]
            
            if evaluated_responses:
                # 计算平均分数
                overall_scores = [resp["evaluation"].get("overall_score", 0) for resp in evaluated_responses]
                dimension_scores = {}
                
                # 收集所有维度分数
                for resp in evaluated_responses:
                    for dim, score in resp["evaluation"].get("scores", {}).items():
                        if dim not in dimension_scores:
                            dimension_scores[dim] = []
                        dimension_scores[dim].append(score)
                
                # 计算平均维度分数
                avg_dimension_scores = {
                    dim: sum(scores) / len(scores) 
                    for dim, scores in dimension_scores.items()
                }
                
                # 添加整体评估
                case_result["evaluation"] = {
                    "overall_score": sum(overall_scores) / len(overall_scores),
                    "scores": avg_dimension_scores,
                    "num_responses": len(evaluated_responses)
                }
        
        # 添加用例结果
        results["test_cases"].append(case_result)
    
    # 清除进度显示
    progress_bar.empty()
    status_text.empty()
    
    # 计算整体平均分数
    if results["total_evaluations"] > 0:
        # 收集所有评分
        all_scores = []
        for case in results["test_cases"]:
            if "evaluation" in case and "overall_score" in case["evaluation"]:
                all_scores.append(case["evaluation"]["overall_score"])
        
        if all_scores:
            results["average_score"] = sum(all_scores) / len(all_scores)
            results["max_score"] = max(all_scores)
            results["min_score"] = min(all_scores)
    
    return results


def prepare_model_comparison_data(results):
    """准备模型比较数据"""
    if not results or "test_cases" not in results:
        return []
    
    model_scores = {}
    
    # 收集每个模型在每个用例中的评分
    for case in results.get("test_cases", []):
        for response in case.get("responses", []):
            model = response.get("model")
            template = response.get("template")
            run_index = response.get("run_index", 1)
            
            if "evaluation" not in response:
                continue
            
            eval_result = response["evaluation"]
            overall_score = eval_result.get("overall_score", 0)
            
            # 初始化模型数据
            if model not in model_scores:
                model_scores[model] = {
                    "模型": model,
                    "平均得分": 0,
                    "响应数": 0,
                    "响应总数": 0,
                    "运行次数": set()  # 使用集合跟踪不同的运行次数
                }
            
            # 更新统计信息
            model_scores[model]["响应总数"] += 1
            model_scores[model]["运行次数"].add(run_index)
            
            if overall_score > 0:
                model_scores[model]["响应数"] += 1
                # 累计得分
                current_total = model_scores[model]["平均得分"] * (model_scores[model]["响应数"] - 1)
                model_scores[model]["平均得分"] = (current_total + overall_score) / model_scores[model]["响应数"]
    
    # 转换为列表
    model_data = list(model_scores.values())
    
    # 格式化平均得分和运行次数
    for item in model_data:
        item["平均得分"] = f"{item['平均得分']:.2f}"
        item["运行次数"] = len(item["运行次数"])  # 转换集合为数量
    
    return model_data
