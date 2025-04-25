# utils/common.py

import streamlit as st
import json
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from typing import Dict, List, Any, Optional, Tuple
import asyncio

from models.token_counter import count_tokens
from models.api_clients import get_client, get_provider_from_model
from utils.evaluator import PromptEvaluator
from config import load_config

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
        if provider in ["openai", "xai"]:
            response = await client.generate_with_messages(
                [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_input}
                ],
                model, 
                params
            )
        else:
            # 对于其他API客户端
            combined_prompt = f"System: {system_prompt}\n\nUser: {user_input}"
            response = await client.generate(
                combined_prompt, 
                model, 
                params
            )
        
        return response
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

def run_test(template, model, test_set, model_provider=None, repeat_count=1, temperature=0.7):
    """运行单提示词单模型测试"""
    # 准备结果存储
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
    
    # 显示进度条和状态
    progress_bar = st.progress(0)
    status_text = st.empty()
    total_cases = len(test_set.get("cases", []))
    
    # 设置评估器
    evaluator = PromptEvaluator()
    
    # 获取模型的API客户端
    if model_provider:
        provider = model_provider
    else:
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
                st.error(f"无法确定模型 '{model}' 的提供商")
                return None
    
    client = get_client(provider)
    
    # 运行测试
    for case_idx, case in enumerate(test_set.get("cases", [])):
        case_id = case.get("id", "")
        status_text.text(f"正在测试用例 {case_idx+1}/{total_cases}: {case_id}")
        
        # 渲染提示词（替换变量）
        prompt_template = render_prompt_template(template, test_set, case)
        
        # 获取用户输入
        user_input = case.get("user_input", "")
        
        # 保存当前测试用例的结果
        case_results = {
            "case_id": case_id,
            "case_description": case.get("description", ""),
            "prompt": prompt_template,
            "user_input": user_input,
            "expected_output": case.get("expected_output", ""),
            "responses": []  # 存储多个响应及其评估结果
        }
        
        # 多次运行测试
        for attempt in range(repeat_count):
            status_text.text(f"正在测试用例 {case_idx+1}/{total_cases}: {case_id}, 重复 #{attempt+1}/{repeat_count}")
            
            # 创建异步事件循环
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
            try:
                # 调用模型API
                params = {"temperature": temperature, "max_tokens": 1000}
                response = loop.run_until_complete(call_model_with_messages(
                    client, provider, model, prompt_template, user_input, params
                ))
                
                # 初始化响应结果
                response_data = {
                    "attempt": attempt + 1,
                    "response": response.get("text", ""),
                    "error": response.get("error", None),
                    "usage": response.get("usage", {}),
                    "evaluation": None  # 将在后面填充评估结果
                }
                
                # 对当前响应进行评估
                if not response_data["error"] and response_data["response"]:
                    evaluation = loop.run_until_complete(evaluate_response(
                        evaluator,
                        response_data["response"],
                        case.get("expected_output", ""),
                        case.get("evaluation_criteria", {}),
                        prompt_template
                    ))
                    
                    response_data["evaluation"] = evaluation
                
            except Exception as e:
                # 存储错误
                response_data = {
                    "attempt": attempt + 1,
                    "response": "",
                    "error": str(e),
                    "usage": {},
                    "evaluation": None
                }
            finally:
                loop.close()
            
            # 将响应数据添加到测试用例结果中
            case_results["responses"].append(response_data)
        
        # 添加测试用例结果到总结果中
        results["test_cases"].append(case_results)
        
        # 更新进度条
        progress_bar.progress((case_idx + 1) / total_cases)
    
    # 测试完成
    progress_bar.progress(1.0)
    status_text.text("✅ 测试完成!")
    
    return results

def regenerate_expected_output(case: dict, template: dict, model: str, provider: str = None, temperature: float = 0.7):
    """使用AI重新生成期望输出
    
    Args:
        case (dict): 测试用例
        template (dict): 提示词模板
        model (str): 模型名称
        provider (str, optional): 模型提供商. Defaults to None (将从模型名称推断).
        temperature (float, optional): 温度参数. Defaults to 0.7.
        
    Returns:
        dict: 包含生成结果或错误信息的字典
    """
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
        
        # 获取API客户端
        client = get_client(provider)
        
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
        
        # 同步调用模型API
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        # 根据不同客户端类型构建不同的消息格式
        try:
            if provider in ["openai", "xai"]:
                response = loop.run_until_complete(client.generate_with_messages(
                    [
                        {"role": "system", "content": prompt_template},
                        {"role": "user", "content": user_input}
                    ],
                    model, 
                    params
                ))
            else:
                # 对于其他API客户端
                combined_prompt = f"System: {prompt_template}\n\nUser: {user_input}"
                response = loop.run_until_complete(client.generate(
                    combined_prompt, 
                    model, 
                    params
                ))
                
            loop.close()
            
            if "error" in response:
                return {"error": response["error"]}
            
            # 返回生成的文本
            return {
                "text": response.get("text", ""),
                "usage": response.get("usage", {})
            }
            
        except Exception as e:
            return {"error": str(e)}
        finally:
            if loop and not loop.is_closed():
                loop.close()
    
    except Exception as e:
        return {"error": f"生成期望输出时发生错误: {str(e)}"}

def display_template_info(template, show_token_count=True, inside_expander=False):
    """显示提示词模板信息"""
    st.info(f"**名称**: {template.get('name', '未命名')}")
    st.markdown(f"**描述**: {template.get('description', '无描述')}")
    
    if inside_expander:
        # 如果已经在expander内，不使用嵌套expander
        st.markdown("**提示词内容:**")
        st.code(template.get("template", ""))
        
        if show_token_count:
            token_count = count_tokens(template.get("template", ""))
            st.caption(f"Token数: {token_count}")
    else:
        # 正常使用expander
        with st.expander("查看提示词内容"):
            st.code(template.get("template", ""))
            
            if show_token_count:
                token_count = count_tokens(template.get("template", ""))
                st.caption(f"Token数: {token_count}")

def generate_evaluation_criteria(case_description, user_input, expected_output):
    """使用AI生成测试用例的评估标准"""
    try:
        # 获取配置的评估模型
        config = load_config()
        evaluator_model = config.get("evaluator_model", "gpt-4")
        provider = get_provider_from_model(evaluator_model)
        
        # 获取API客户端
        client = get_client(provider)
        
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
        
        # 同步调用模型API
        result = client.generate_sync(criteria_generation_prompt, evaluator_model, params)
        
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
