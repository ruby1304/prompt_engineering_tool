import streamlit as st
import json
import pandas as pd
import asyncio
from datetime import datetime
import time
# 修改导入方式
from config import get_template_list, load_template, get_test_set_list, load_test_set, save_result, get_available_models
from models.api_clients import get_client, get_provider_from_model
from models.token_counter import count_tokens, estimate_cost
from utils.evaluator import PromptEvaluator

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
        "重复次数": repeat_count
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
    """运行测试并显示进度"""
    st.subheader("测试运行中...")
    
    # 创建进度条
    progress_bar = st.progress(0)
    status_text = st.empty()
    result_area = st.empty()
    
    # 计算总任务数
    total_tasks = len(templates) * len(test_set["cases"]) * len(selected_models) * repeat_count
    completed_tasks = 0
    
    # 准备结果存储
    results = {}
    for template in templates:
        results[template["name"]] = {
            "template": template,
            "test_set": test_set["name"],
            "models": selected_models,
            "params": {
                "temperature": temperature,
                "max_tokens": max_tokens
            },
            "test_cases": []
        }
    
    # 设置评估器
    evaluator = PromptEvaluator()
    
    # 运行测试
    for template in templates:
        template_name = template["name"]
        status_text.text(f"正在测试提示词模板: {template_name}")
        
        for case in test_set["cases"]:
            case_id = case["id"]
            status_text.text(f"正在测试模板 '{template_name}' 的用例 '{case_id}'")
            
            # 渲染提示词（替换变量）
            prompt_template = template["template"]
            
            # 应用全局变量和用例变量
            variables = {**test_set.get("variables", {}), **case.get("variables", {})}
            
            # 如果变量未提供，使用提示词模板中的默认值
            for var_name in template.get("variables", {}):
                if var_name not in variables:
                    variables[var_name] = template["variables"][var_name].get("default", "")

            # 应用变量到提示词模板  
            for var_name, var_value in variables.items():
                prompt_template = prompt_template.replace(f"{{{{{var_name}}}}}", var_value)
            
            # 获取用户输入
            user_input = case.get("user_input", "")
            
            # 保存当前测试用例的结果
            case_results = {
                "case_id": case_id,
                "case_description": case.get("description", ""),
                "prompt": prompt_template,
                "user_input": user_input,
                "expected_output": case.get("expected_output", ""),
                "model_responses": [],
                "evaluation": None
            }
            
            # 为每个模型运行测试
            for model in selected_models:
                # 获取模型对应的提供商
                if hasattr(st.session_state, 'model_provider_map') and model in st.session_state.model_provider_map:
                    provider = st.session_state.model_provider_map[model]
                else:
                    # 兼容旧代码，尝试从模型名称推断提供商
                    try:
                        provider = get_provider_from_model(model)
                    except ValueError:
                        st.error(f"无法确定模型 '{model}' 的提供商")
                        continue
                
                client = get_client(provider)
                
                # 重复测试
                for i in range(repeat_count):
                    status_text.text(f"正在测试模板 '{template_name}' 的用例 '{case_id}', 模型 '{model}', 重复 #{i+1}")
                    
                    try:
                        # 修改调用模型API的方式，将提示词作为系统提示，用户输入作为用户消息
                        loop = asyncio.new_event_loop()
                        asyncio.set_event_loop(loop)
                        
                        # 根据不同客户端类型构建不同的消息格式
                        if provider in ["openai", "xai"]:
                            response = loop.run_until_complete(client.generate_with_messages(
                                [
                                    {"role": "system", "content": prompt_template},
                                    {"role": "user", "content": user_input}
                                ],
                                model, 
                                {"temperature": temperature, "max_tokens": max_tokens}
                            ))
                        else:
                            # 对于其他API客户端，我们可能需要调整消息格式或者合并内容
                            combined_prompt = f"System: {prompt_template}\n\nUser: {user_input}"
                            response = loop.run_until_complete(client.generate(
                                combined_prompt, 
                                model, 
                                {"temperature": temperature, "max_tokens": max_tokens}
                            ))
                        
                        loop.close()
                        
                        # 存储响应
                        case_results["model_responses"].append({
                            "model": model,
                            "attempt": i+1,
                            "response": response.get("text", ""),
                            "error": response.get("error", None),
                            "usage": response.get("usage", {})
                        })
                        
                    except Exception as e:
                        # 存储错误
                        case_results["model_responses"].append({
                            "model": model,
                            "attempt": i+1,
                            "response": "",
                            "error": str(e),
                            "usage": {}
                        })
                    
                    # 更新进度
                    completed_tasks += 1
                    progress_bar.progress(completed_tasks / total_tasks)
                    
                    # 模拟API调用延迟
                    time.sleep(0.5)
            
            # 对测试结果进行评估
            # 选择最后一次响应进行评估
            response_text = ""
            for resp in reversed(case_results["model_responses"]):
                if not resp.get("error") and resp.get("response"):
                    response_text = resp.get("response")
                    break
            if response_text:
                try:
                    # 使用同步方法替代
                    evaluation = evaluator.evaluate_response_sync(
                        response_text,
                        case.get("expected_output", ""),
                        case.get("evaluation_criteria", {}),
                        prompt_template
                    )
                    case_results["evaluation"] = evaluation
                except Exception as e:
                    case_results["evaluation"] = {"error": str(e)}
            
            # 添加到结果
            results[template_name]["test_cases"].append(case_results)
            
            # 显示中间结果
            result_summary = f"已完成: {completed_tasks}/{total_tasks} 测试"
            result_area.text(result_summary)
    
    # 测试完成
    progress_bar.progress(1.0)
    status_text.text("✅ 测试完成!")
    
    # 保存结果
    result_name = f"test_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    save_result(result_name, results)
    
    st.success(f"测试结果已保存: {result_name}")
    
    # 建议跳转到结果查看页面
    st.session_state.last_result = result_name
    if st.button("📊 查看详细结果"):
        st.session_state.page = "results_viewer"
        st.experimental_rerun()