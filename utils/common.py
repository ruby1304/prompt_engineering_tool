# utils/common.py

import streamlit as st
import json
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from typing import Dict, List, Any, Optional, Tuple, Callable
import asyncio
import time

from models.token_counter import count_tokens
from models.api_clients import get_client, get_provider_from_model
from utils.evaluator import PromptEvaluator
from config import load_config
# Import the new parallel executor
from utils.parallel_executor import execute_model, execute_models, execute_model_sync, execute_models_sync

def calculate_average_score(results):
    """计算平均得分"""
    total_score = 0
    count = 0
    
    # 遍历所有测试用例
    for case in results.get("test_cases", []):
        responses = case.get("responses", [])
        
        if responses:
            # 处理每个响应的评估
            for resp in responses:
                eval_result = resp.get("evaluation")
                if eval_result and "overall_score" in eval_result:
                    total_score += eval_result["overall_score"]
                    count += 1
        elif case.get("evaluation") and "overall_score" in case["evaluation"]:
            # 兼容旧格式
            total_score += case["evaluation"]["overall_score"]
            count += 1
    
    return total_score / count if count > 0 else 0

def get_dimension_scores(results):
    """获取各维度的平均分数"""
    dimensions = {"accuracy": 0, "completeness": 0, "relevance": 0, "clarity": 0}
    counts = {"accuracy": 0, "completeness": 0, "relevance": 0, "clarity": 0}
    
    # 遍历所有测试用例
    for case in results.get("test_cases", []):
        responses = case.get("responses", [])
        
        if responses:
            # 处理每个响应的评估
            for resp in responses:
                eval_result = resp.get("evaluation")
                if eval_result and "scores" in eval_result:
                    for dim, score in eval_result["scores"].items():
                        if dim in dimensions:
                            dimensions[dim] += score
                            counts[dim] += 1
        elif case.get("evaluation") and "scores" in case["evaluation"]:
            # 兼容旧格式
            for dim, score in case["evaluation"]["scores"].items():
                if dim in dimensions:
                    dimensions[dim] += score
                    counts[dim] += 1
    
    # 计算平均值
    for dim in dimensions:
        if counts[dim] > 0:
            dimensions[dim] /= counts[dim]
    
    return dimensions

def analyze_response_stability(results):
    """分析响应的稳定性"""
    stability_metrics = {
        "平均分": 0.0,
        "分数方差": 0.0,
        "最高分": 0.0,
        "最低分": 100.0,
        "响应成功率": 0.0,
        "稳定性指数": 0.0
    }
    
    total_responses = 0
    successful_responses = 0
    all_scores = []
    
    # 遍历所有测试用例
    for case in results.get("test_cases", []):
        responses = case.get("responses", [])
        
        for resp in responses:
            total_responses += 1
            
            # 检查是否成功
            if not resp.get("error") and resp.get("response"):
                successful_responses += 1
            
            # 获取分数
            eval_result = resp.get("evaluation")
            if eval_result and "overall_score" in eval_result:
                all_scores.append(eval_result["overall_score"])
    
    # 计算指标
    if successful_responses > 0:
        stability_metrics["响应成功率"] = (successful_responses / total_responses) * 100 if total_responses > 0 else 0
    
    if all_scores:
        stability_metrics["平均分"] = sum(all_scores) / len(all_scores)
        stability_metrics["最高分"] = max(all_scores)
        stability_metrics["最低分"] = min(all_scores)
        
        # 计算方差
        if len(all_scores) > 1:
            mean = stability_metrics["平均分"]
            variance = sum((x - mean) ** 2 for x in all_scores) / len(all_scores)
            stability_metrics["分数方差"] = variance
        
        # 计算稳定性指数 (介于0-100之间，越高越稳定)
        score_range = stability_metrics["最高分"] - stability_metrics["最低分"]
        normalized_variance = min(stability_metrics["分数方差"] / 100, 1.0)  # 将方差标准化到0-1
        
        # 稳定性指数 = 成功率 * (1 - 归一化方差) * (1 - 归一化分数范围)
        normalized_range = min(score_range / 100, 1.0)
        stability_metrics["稳定性指数"] = (
            stability_metrics["响应成功率"] / 100 * 
            (1 - normalized_variance) * 
            (1 - normalized_range) * 
            100
        )
    
    # 格式化为小数点后一位
    for key in stability_metrics:
        stability_metrics[key] = round(stability_metrics[key], 1)
    
    return stability_metrics

def create_dimension_radar_chart(dimension_scores_list, labels, title="维度表现对比"):
    """创建维度雷达图"""
    fig = go.Figure()
    
    # 添加每个数据集的雷达图
    for i, dimensions in enumerate(dimension_scores_list):
        fig.add_trace(go.Scatterpolar(
            r=list(dimensions.values()),
            theta=list(dimensions.keys()),
            fill='toself',
            name=labels[i]
        ))
    
    fig.update_layout(
        polar=dict(
            radialaxis=dict(
                visible=True,
                range=[0, 100]
            )
        ),
        showlegend=True,
        title=title
    )
    
    return fig

def create_score_bar_chart(scores, labels, title="平均得分对比"):
    """创建得分条形图"""
    fig = px.bar(
        x=labels, 
        y=scores,
        labels={"x": "提示词版本", "y": "平均得分"},
        title=title,
        color=scores,
        color_continuous_scale="RdYlGn"
    )
    
    # 添加最佳版本标记
    if scores:
        best_index = scores.index(max(scores)) if max(scores) > 0 else -1
        if best_index >= 0:
            fig.add_annotation(
                x=labels[best_index],
                y=scores[best_index],
                text="最佳版本",
                showarrow=True,
                arrowhead=1,
                ax=0,
                ay=-40
            )
    
    return fig

async def call_model_with_messages(client, provider, model, system_prompt, user_input, params):
    """调用模型API并返回响应"""
    try:
        # 使用新的并行执行器实现
        if provider in ["openai", "xai"]:
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_input}
            ]
            return await execute_model(model, messages=messages, provider=provider, params=params)
        else:
            # 对于其他API客户端
            combined_prompt = f"System: {system_prompt}\n\nUser: {user_input}"
            return await execute_model(model, prompt=combined_prompt, provider=provider, params=params)
    except Exception as e:
        return {"error": str(e), "text": "", "usage": {}}

async def evaluate_response(evaluator, response_text, expected_output, criteria, prompt):
    """评估模型响应"""
    try:
        evaluation = evaluator.evaluate_response_sync(
            response_text,
            expected_output,
            criteria,
            prompt
        )
        return evaluation
    except Exception as e:
        return {"error": str(e)}

def render_prompt_template(template: dict, test_set: dict, case: dict) -> str:
    """通用模板渲染函数，合并变量并替换模板中的变量"""
    prompt_template = template.get("template", "")
    # 合并全局变量和用例变量
    variables = {**test_set.get("variables", {}), **case.get("variables", {})}
    # 如果变量未提供，使用提示词模板中的默认值
    for var_name in template.get("variables", {}):
        if var_name not in variables:
            variables[var_name] = template["variables"][var_name].get("default", "")
    # 替换模板中的变量
    for var_name, var_value in variables.items():
        prompt_template = prompt_template.replace(f"{{{{{var_name}}}}}", var_value)
    return prompt_template

def run_test(template, model, test_set, model_provider=None, repeat_count=1, temperature=0.7, progress_callback: Optional[Callable] = None):
    """运行测试，使用并行执行器处理并发请求"""
    import asyncio
    from utils.evaluator import PromptEvaluator

    results = {
        "template": template,
        "model": model,
        "model_provider": model_provider,
        "test_params": {
            "repeat_count": repeat_count,
            "temperature": temperature
        },
        "test_cases": []
    }
    total_cases = len(test_set.get("cases", []))

    # 确定提供商
    if model_provider:
        provider = model_provider
    else:
        try:
            provider = get_provider_from_model(model)
        except ValueError:
            from config import get_available_models
            found = False
            available_models = get_available_models()
            for p, models in available_models.items():
                if model in models:
                    provider = p
                    found = True
                    break
            if not found:
                st.error(f"无法确定模型 '{model}' 的提供商")
                return None

    async def run_all_tests():
        all_requests = []
        
        # 准备所有请求，整理成适合批处理的格式
        for case_idx, case in enumerate(test_set.get("cases", [])):
            case_id = case.get("id", "")
            prompt_template = render_prompt_template(template, test_set, case)
            user_input = case.get("user_input", "")
            
            # 为每次尝试创建请求
            for attempt in range(repeat_count):
                params = {"temperature": temperature, "max_tokens": 1000}
                
                # 根据不同提供商准备不同格式的请求
                request = {
                    "model": model,
                    "provider": provider,
                    "params": params,
                    "context": {
                        "case_id": case_id,
                        "case_idx": case_idx,
                        "attempt": attempt,
                        "user_input": user_input,
                        "expected_output": case.get("expected_output", ""),
                        "evaluation_criteria": case.get("evaluation_criteria", {}),
                        "prompt": prompt_template
                    }
                }
                
                # 根据提供商选择消息格式或普通文本格式
                if provider in ["openai", "xai"]:
                    request["messages"] = [
                        {"role": "system", "content": prompt_template},
                        {"role": "user", "content": user_input}
                    ]
                else:
                    request["prompt"] = f"System: {prompt_template}\n\nUser: {user_input}"
                
                all_requests.append(request)
        
        # 使用并行执行器批量处理请求
        model_responses = await execute_models(all_requests, progress_callback=lambda current, total: None)
        
        # 整理测试用例结果
        case_results = {}
        for response in model_responses:
            context = response.get("context", {})
            case_id = context.get("case_id", "")
            case_idx = context.get("case_idx", -1)
            attempt = context.get("attempt", 0)
            
            # 如果这是新的测试用例，创建结果字典
            if case_id not in case_results:
                case_results[case_id] = {
                    "case_id": case_id,
                    "case_description": test_set.get("cases", [])[case_idx].get("description", "") if case_idx >= 0 else "",
                    "prompt": context.get("prompt", ""),
                    "user_input": context.get("user_input", ""),
                    "expected_output": context.get("expected_output", ""),
                    "responses": []
                }
            
            # 处理响应结果
            if "error" not in response and response.get("text"):
                response_data = {
                    "attempt": attempt + 1,
                    "response": response.get("text", ""),
                    "error": None,
                    "usage": response.get("usage", {}),
                    "evaluation": None,
                    "_eval_input": {
                        "response_text": response.get("text", ""),
                        "expected_output": context.get("expected_output", ""),
                        "criteria": context.get("evaluation_criteria", {}),
                        "prompt": context.get("prompt", "")
                    }
                }
            else:
                response_data = {
                    "attempt": attempt + 1,
                    "response": response.get("text", ""),
                    "error": response.get("error", "模型未返回内容"),
                    "usage": response.get("usage", {}),
                    "evaluation": None,
                    "_eval_input": None
                }
            
            # 添加响应并触发 UI 回调（不同于并行执行器的内部进度回调）
            case_results[case_id]["responses"].append(response_data)
            if progress_callback:
                progress_callback()
        
        # 返回结果列表，按原始用例索引排序
        sorted_results = []
        for case_idx, case in enumerate(test_set.get("cases", [])):
            case_id = case.get("id", "")
            if case_id in case_results:
                sorted_results.append(case_results[case_id])
        
        return sorted_results
            
    # 创建新的事件循环执行测试
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    all_case_results = loop.run_until_complete(run_all_tests())
    
    # 处理评估：收集需要评估的响应
    eval_inputs = []
    eval_response_refs = []
    for case in all_case_results:
        for resp in case["responses"]:
            if resp.get("_eval_input"):
                eval_inputs.append(resp["_eval_input"])
                eval_response_refs.append(resp)
    
    # 并行执行评估
    if eval_inputs:
        evaluator = PromptEvaluator()
        # 传递包含所有评估所需信息的任务列表
        eval_results = evaluator.run_evaluation(
            evaluation_tasks=[{
                "model_response": item["response_text"], # 传递实际的模型响应
                "expected_output": item["expected_output"],
                "criteria": item["criteria"],
                "prompt": item["prompt"] # 传递对应的提示词
            } for item in eval_inputs]
        )
        # 更新评估结果
        for resp, eval_result in zip(eval_response_refs, eval_results):
            resp["evaluation"] = eval_result
            del resp["_eval_input"] # 清理临时数据
    
    results["test_cases"] = all_case_results
    loop.close()
    return results

def regenerate_expected_output(case: dict, template: dict, model: str, provider: str = None, temperature: float = 0.7):
    """使用AI重新生成期望输出，使用并行执行器"""
    try:
        # 如果未指定提供商，从模型名称推断
        if not provider:
            try:
                provider = get_provider_from_model(model)
            except ValueError:
                # 尝试在所有提供商中查找模型
                from config import get_available_models
                found = False
                available_models = get_available_models()
                for p, models in available_models.items():
                    if model in models:
                        provider = p
                        found = True
                        break
                
                if not found:
                    return {"error": f"无法确定模型 '{model}' 的提供商"}
        
        # 获取测试用例输入
        user_input = case.get("user_input", "")
        if not user_input:
            return {"error": "测试用例没有用户输入"}
            
        # 渲染提示词模板
        # 注意：这里我们只有case，没有test_set，所以我们只使用case中的变量
        test_set = {"variables": {}}  # 创建一个空的测试集，只用于提供变量结构
        prompt_template = render_prompt_template(template, test_set, case)
        
        # 参数设置
        params = {"temperature": temperature, "max_tokens": 1000}
        
        # 使用并行执行器的同步方法
        if provider in ["openai", "xai"]:
            messages = [
                {"role": "system", "content": prompt_template},
                {"role": "user", "content": user_input}
            ]
            response = execute_model_sync(model, messages=messages, provider=provider, params=params)
        else:
            combined_prompt = f"System: {prompt_template}\n\nUser: {user_input}"
            response = execute_model_sync(model, prompt=combined_prompt, provider=provider, params=params)
        
        if "error" in response:
            return {"error": response["error"]}
        
        # 返回生成的文本
        return {
            "text": response.get("text", ""),
            "usage": response.get("usage", {})
        }
            
    except Exception as e:
        return {"error": f"生成期望输出时发生错误: {str(e)}"}

def generate_evaluation_criteria(case_description, user_input, expected_output):
    """使用AI生成测试用例的评估标准，使用并行执行器"""
    try:
        # 获取配置的评估模型
        config = load_config()
        evaluator_model = config.get("evaluator_model", "gpt-4")
        provider = get_provider_from_model(evaluator_model)
        
        # 获取系统模板
        from config import get_system_template
        criteria_generator_template = get_system_template("criteria_generator")
        
        # 使用模板替换变量
        criteria_generation_prompt = criteria_generator_template.get("template", "")\
            .replace("{{case_description}}", case_description)\
            .replace("{{user_input}}", user_input)\
            .replace("{{expected_output}}", expected_output)

        # 设置参数
        params = {
            "temperature": 0.2,
            "max_tokens": 1000
        }
        
        # 使用并行执行器的同步方法
        result = execute_model_sync(
            evaluator_model, 
            prompt=criteria_generation_prompt,
            provider=provider, 
            params=params
        )
        
        if "error" in result:
            return {
                "error": result["error"],
                "criteria": {
                    "accuracy": "评估响应与期望输出的匹配程度",
                    "completeness": "评估响应是否包含所有必要信息",
                    "relevance": "评估响应与提示词的相关性",
                    "clarity": "评估响应的清晰度和可理解性"
                }
            }
        
        # 处理响应文本，提取JSON
        response_text = result.get("text", "")
        
        # 清理可能的前后缀文本
        if "```json" in response_text:
            response_text = response_text.split("```json")[1].split("```")[0].strip()
        elif "```" in response_text:
            response_text = response_text.split("```")[1].split("```")[0].strip()
        
        # 解析JSON
        try:
            criteria = json.loads(response_text)
            return {
                "criteria": criteria
            }
        except json.JSONDecodeError:
            return {
                "error": "无法解析生成的评估标准",
                "raw_response": response_text,
                "criteria": {
                    "accuracy": "评估响应与期望输出的匹配程度",
                    "completeness": "评估响应是否包含所有必要信息",
                    "relevance": "评估响应与提示词的相关性",
                    "clarity": "评估响应的清晰度和可理解性"
                }
            }
    
    except Exception as e:
        return {
            "error": f"生成评估标准时出错: {str(e)}",
            "criteria": {
                "accuracy": "评估响应与期望输出的匹配程度",
                "completeness": "评估响应是否包含所有必要信息",
                "relevance": "评估响应与提示词的相关性",
                "clarity": "评估响应的清晰度和可理解性"
            }
        }

def save_optimized_template(template: dict, opt_prompt: dict, index: int = 0) -> str:
    """保存优化后的提示词为新模板，返回新模板名称"""
    from config import save_template
    from datetime import datetime
    current_time = datetime.now().strftime("%Y%m%d_%H%M%S")
    new_template = dict(template)
    new_template["name"] = f"{template.get('name', 'template')}_{current_time}_v{index+1}"
    new_template["description"] = f"从 '{template.get('name', 'unknown')}' 优化: {opt_prompt.get('strategy', '')}"
    new_template["template"] = opt_prompt.get("prompt", "")
    save_template(new_template["name"], new_template)
    return new_template["name"]

def compare_dimension_performance(results_list, labels, section_title="维度表现对比", show_table=True):
    """通用维度对比雷达图和改进表格展示"""
    import streamlit as st
    import pandas as pd
    from .common import get_dimension_scores, create_dimension_radar_chart
    st.subheader(section_title)
    # 计算各版本维度分数
    dimension_scores_list = [get_dimension_scores(res) for res in results_list]
    # 创建雷达图
    fig = create_dimension_radar_chart(dimension_scores_list, labels, section_title)
    st.plotly_chart(fig, use_container_width=True)
    if show_table and len(dimension_scores_list) > 1:
        # 只对比第一个和后续版本
        base = dimension_scores_list[0]
        improvement_data = []
        for idx, dims in enumerate(dimension_scores_list[1:]):
            improvements = {}
            for dim in base:
                if base[dim] > 0:
                    improvement = (dims[dim] - base[dim]) / base[dim] * 100
                else:
                    improvement = 0
                improvements[dim] = improvement
            row = {"版本": labels[idx+1]}
            for dim in base:
                row[dim] = f"{improvements[dim]:.1f}%"
            improvement_data.append(row)
        if improvement_data:
            st.subheader("各维度改进情况")
            st.dataframe(pd.DataFrame(improvement_data), use_container_width=True)

def generate_dialogue_improvement_report(dialogue_history: List[Dict], evaluation_results: List[Dict]) -> str:
    """生成对话改进报告
    
    Args:
        dialogue_history: 对话历史
        evaluation_results: 评估结果列表
        
    Returns:
        str: 生成的Markdown格式报告
    """
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

def format_chat_history(history: List[Dict], max_turns: int = 5) -> str:
    """将对话历史格式化为模板可用的格式，只保留最近n轮对话
    
    Args:
        history: 对话历史
        max_turns: 最大保留轮次
        
    Returns:
        str: 格式化后的对话历史
    """
    # 只保留最近的n轮对话
    recent_history = history[-max_turns:] if len(history) > max_turns else history
    
    formatted = ""
    
    for exchange in recent_history:
        formatted += f"用户: {exchange['user']}\n"
        formatted += f"助手: {exchange['assistant']}\n\n"
    
    return formatted.strip()
