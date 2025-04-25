import pandas as pd
import matplotlib.pyplot as plt
import plotly.express as px
import plotly.graph_objects as go
from typing import Dict, List, Any, Optional
import json
import streamlit as st

def create_score_comparison_chart(results: Dict[str, Dict]) -> go.Figure:
    """创建不同提示词版本得分对比图"""
    # 准备数据
    prompts = []
    scores = []
    categories = []

    for prompt_name, prompt_results in results.items():
        for test_case in prompt_results.get("test_cases", []):
            # 从 responses[0] 获取 evaluation
            response_list = test_case.get("responses", [])
            if not response_list:
                continue
            evaluation = response_list[0].get("evaluation")  # Get evaluation from the first response

            if evaluation:  # Check if evaluation exists
                score_dict = evaluation.get("scores")  # Get scores if evaluation exists
                if score_dict: # Check if score_dict exists and is not empty
                    for score_name, score_value in score_dict.items():
                        if score_value is not None: # Ensure score value is valid
                            prompts.append(prompt_name)
                            scores.append(score_value)
                            categories.append(score_name)

    # 如果没有有效数据，返回提示图表
    if not prompts:
        fig = go.Figure()
        fig.add_annotation(
            text="无有效评估数据",
            showarrow=False,
            font=dict(size=20)
        )
        return fig

    df = pd.DataFrame({
        "提示词": prompts,
        "分数": scores,
        "类别": categories
    })

    # 创建图表
    fig = px.bar(
        df,
        x="提示词",
        y="分数",
        color="类别",
        barmode="group",
        title="提示词性能对比",
        labels={"提示词": "提示词版本", "分数": "评分 (0-100)", "类别": "评估维度"},
        height=500
    )

    return fig

def create_token_comparison_chart(results: Dict[str, Dict]) -> go.Figure:
    """创建不同提示词版本token使用对比图"""
    # 准备数据
    prompts = []
    token_counts = []

    for prompt_name, prompt_results in results.items():
        total_tokens = 0
        count = 0

        for test_case in prompt_results.get("test_cases", []):
            # 从 responses[0] 获取 evaluation
            response_list = test_case.get("responses", [])
            if not response_list:
                continue
            evaluation = response_list[0].get("evaluation")  # Get evaluation from the first response

            if evaluation: # Check if evaluation exists
                prompt_info = evaluation.get("prompt_info") # Get prompt_info if evaluation exists
                if prompt_info and "token_count" in prompt_info and prompt_info["token_count"] is not None: # Check if prompt_info and token_count exist and are valid
                    total_tokens += prompt_info["token_count"]
                    count += 1

        if count > 0:
            prompts.append(prompt_name)
            token_counts.append(total_tokens / count)

    # 如果没有有效数据，返回提示图表
    if not prompts:
        fig = go.Figure()
        fig.add_annotation(
            text="无有效评估数据",
            showarrow=False,
            font=dict(size=20)
        )
        return fig

    # 创建图表
    fig = px.bar(
        x=prompts,
        y=token_counts,
        title="提示词Token长度对比",
        labels={"x": "提示词版本", "y": "平均Token数"},
        height=400
    )

    return fig

def create_radar_chart(results: Dict[str, Dict]) -> go.Figure:
    """创建雷达图展示不同提示词在各维度的表现"""
    # 准备数据
    prompt_names = list(results.keys())
    # Try to dynamically get categories from the first valid evaluation scores
    categories = []
    for prompt_name in prompt_names:
        for test_case in results[prompt_name].get("test_cases", []):
            # 从 responses[0] 获取 evaluation
            response_list = test_case.get("responses", [])
            if not response_list:
                continue
            evaluation = response_list[0].get("evaluation")  # Get evaluation from the first response

            if evaluation and evaluation.get("scores"):
                categories = list(evaluation["scores"].keys())
                break
        if categories:
            break

    # Default categories if none found
    if not categories:
        categories = ["accuracy", "completeness", "relevance", "clarity"]

    category_names = { # Keep default names, can be expanded if needed
        "accuracy": "准确性",
        "completeness": "完整性",
        "relevance": "相关性",
        "clarity": "清晰度"
    }
    # Add any new categories found with their own name
    for cat in categories:
        if cat not in category_names:
            category_names[cat] = cat.capitalize()


    fig = go.Figure()
    data_found = False # Flag to check if any data was added

    for prompt_name in prompt_names:
        prompt_results = results[prompt_name]

        # 计算各维度的平均分
        category_scores = {cat: 0 for cat in categories}
        category_counts = {cat: 0 for cat in categories} # Count per category

        for test_case in prompt_results.get("test_cases", []):
            # 从 responses[0] 获取 evaluation
            response_list = test_case.get("responses", [])
            if not response_list:
                continue
            evaluation = response_list[0].get("evaluation")  # Get evaluation from the first response

            if evaluation: # Check if evaluation exists
                scores = evaluation.get("scores") # Get scores if evaluation exists
                if scores: # Check if scores exist
                    for cat in categories:
                        if cat in scores and scores[cat] is not None: # Check category exists and score is valid
                            category_scores[cat] += scores[cat]
                            category_counts[cat] += 1

        # Calculate average scores only for categories with data
        avg_category_scores = []
        valid_categories_names = []
        prompt_has_data = False
        for cat in categories:
            if category_counts[cat] > 0:
                avg_score = category_scores[cat] / category_counts[cat]
                avg_category_scores.append(avg_score)
                valid_categories_names.append(category_names.get(cat, cat.capitalize()))
                prompt_has_data = True
            else:
                # Handle missing data - append 0 or None, depending on desired visualization
                avg_category_scores.append(0) # Or None
                valid_categories_names.append(category_names.get(cat, cat.capitalize()))


        # 添加雷达图 trace only if this prompt had some valid data
        if prompt_has_data:
            fig.add_trace(go.Scatterpolar(
                r=avg_category_scores,
                theta=valid_categories_names, # Use names corresponding to the scores calculated
                fill='toself',
                name=prompt_name
            ))
            data_found = True # Mark that we added at least one trace

    # Add annotation if no traces were added at all
    if not data_found:
        fig.add_annotation(
            text="无有效评估数据",
            showarrow=False,
            font=dict(size=20)
        )
        # Add dummy trace to show layout if no data
        fig.add_trace(go.Scatterpolar(r=[0]*len(categories), theta=[category_names.get(cat, cat.capitalize()) for cat in categories]))


    fig.update_layout(
        polar=dict(
            radialaxis=dict(
                visible=True,
                range=[0, 100] # Assuming scores are 0-100
            )
        ),
        showlegend=True,
        title="提示词多维度性能对比"
    )

    return fig

def generate_report(results: Dict[str, Dict]) -> Dict:
    """生成测试结果分析报告"""
    report = {
        "summary": {},
        "prompt_comparison": [],
        "model_comparison": [],
        "recommendations": [],
        "is_model_comparison": False
    }

    # Determine the scenario: multi-prompt or single-prompt/multi-model
    prompt_names = list(results.keys())
    is_single_prompt = len(prompt_names) == 1
    models_in_single_prompt = set()
    if is_single_prompt:
        prompt_data = results[prompt_names[0]]
        for case in prompt_data.get("test_cases", []):
            models_in_single_prompt.add(case.get("model"))
        if len(models_in_single_prompt) > 1:
            report["is_model_comparison"] = True

    # --- Model Comparison Logic ---
    if report["is_model_comparison"]:
        prompt_name = prompt_names[0]
        prompt_data = results[prompt_name]
        model_results = {model: {"scores": [], "dimensions": {}, "token_counts": []} for model in models_in_single_prompt}

        # Aggregate results per model
        for case in prompt_data.get("test_cases", []):
            model = case.get("model")
            if not model:
                continue
            
            response_list = case.get("responses", [])
            if not response_list:
                continue
            evaluation = response_list[0].get("evaluation")
            if not evaluation:
                continue

            if "overall_score" in evaluation:
                model_results[model]["scores"].append(evaluation["overall_score"])
            
            if "scores" in evaluation:
                for dim, score in evaluation["scores"].items():
                    if score is not None:
                        if dim not in model_results[model]["dimensions"]:
                            model_results[model]["dimensions"][dim] = []
                        model_results[model]["dimensions"][dim].append(score)

            if "prompt_info" in evaluation and "token_count" in evaluation["prompt_info"]:
                 token_count = evaluation["prompt_info"]["token_count"]
                 if token_count is not None:
                    model_results[model]["token_counts"].append(token_count)

        # Calculate averages and analyze per model
        for model, data in model_results.items():
            avg_score = sum(data["scores"]) / len(data["scores"]) if data["scores"] else 0
            report["summary"][model] = {
                "average_score": avg_score,
                "test_cases_count": len(data["scores"])
            }

            strengths = []
            weaknesses = []
            avg_dimension_scores = {}
            for dim, scores in data["dimensions"].items():
                avg_dim_score = sum(scores) / len(scores) if scores else 0
                avg_dimension_scores[dim] = avg_dim_score
                dim_name = {"accuracy": "准确性", "completeness": "完整性", "relevance": "相关性", "clarity": "清晰度"}.get(dim, dim.capitalize())
                if avg_dim_score >= 85:
                    strengths.append(f"{dim_name}维度表现出色（{avg_dim_score:.1f}分）")
                elif avg_dim_score < 70:
                    weaknesses.append(f"{dim_name}维度需要改进（{avg_dim_score:.1f}分）")

            avg_tokens = sum(data["token_counts"]) / len(data["token_counts"]) if data["token_counts"] else 0
            token_efficiency = "未知"
            if avg_tokens > 0 and avg_score > 0:
                efficiency = avg_score / avg_tokens * 100
                if efficiency > 0.5:
                    token_efficiency = "高"
                elif efficiency > 0.3:
                    token_efficiency = "中"
                else:
                    token_efficiency = "低"

            report["model_comparison"].append({
                "name": model,
                "average_score": avg_score,
                "strengths": strengths,
                "weaknesses": weaknesses,
                "token_count": avg_tokens if data["token_counts"] else "未知",
                "token_efficiency": token_efficiency
            })
        
        # Find best model
        if report["summary"]:
            best_model_item = max(report["summary"].items(), key=lambda x: x[1]["average_score"])
            report["best_model"] = {
                "name": best_model_item[0],
                "score": best_model_item[1]["average_score"]
            }
            
        # Generate model recommendations
        if report["model_comparison"]:
            sorted_models = sorted(report["model_comparison"], key=lambda x: x["average_score"], reverse=True)
            if sorted_models:
                best_model = sorted_models[0]
                report["recommendations"].append(f"表现最佳的模型是 '{best_model['name']}'，平均得分为 {best_model['average_score']:.1f}分。")
                if best_model["strengths"]:
                    report["recommendations"].append(f"其主要优势在于: {', '.join(best_model['strengths'])}")
                
                if len(sorted_models) > 1:
                    worst_model = sorted_models[-1]
                    score_diff = best_model["average_score"] - worst_model["average_score"]
                    if score_diff > 10: # Threshold for significant difference
                        report["recommendations"].append(f"模型之间的性能差异较明显，最佳与最差模型的分数相差 {score_diff:.1f} 分。")
                        if worst_model["weaknesses"]:
                            report["recommendations"].append(f"表现较差的模型 '{worst_model['name']}' 主要问题在于: {', '.join(worst_model['weaknesses'])}")
            
            token_efficiencies = [m.get("token_efficiency") for m in report["model_comparison"] if m.get("token_efficiency") != "未知"]
            if "低" in token_efficiencies:
                 report["recommendations"].append("部分模型的token效率较低，考虑选择效率更高的模型或优化提示词以减少token消耗。")

    # --- Prompt Comparison Logic (Existing Logic) ---
    else:
        # Calculate average score per prompt (using the corrected access pattern)
        for prompt_name, prompt_results in results.items():
            overall_scores = []
            for test_case in prompt_results.get("test_cases", []):
                response_list = test_case.get("responses", [])
                if not response_list:
                    continue
                evaluation = response_list[0].get("evaluation")
                if evaluation and "overall_score" in evaluation:
                    overall_scores.append(evaluation["overall_score"])
            
            if overall_scores:
                avg_score = sum(overall_scores) / len(overall_scores)
                report["summary"][prompt_name] = {
                    "average_score": avg_score,
                    "test_cases_count": len(overall_scores)
                }
        
        # Find best prompt
        if report["summary"]:
            best_prompt_item = max(report["summary"].items(), key=lambda x: x[1]["average_score"])
            report["best_prompt"] = {
                "name": best_prompt_item[0],
                "score": best_prompt_item[1]["average_score"]
            }
        
        # Prompt comparison details (using corrected access pattern)
        for prompt_name, prompt_data_summary in report["summary"] .items(): # Iterate through calculated summary
            strengths = []
            weaknesses = []
            prompt_results = results[prompt_name]
            
            # Dynamically get categories
            first_eval_scores = {}
            for tc in prompt_results.get("test_cases", []):
                resp_list = tc.get("responses", [])
                if resp_list and resp_list[0].get("evaluation") and resp_list[0]["evaluation"].get("scores"):
                    first_eval_scores = resp_list[0]["evaluation"]["scores"]
                    break
            
            current_categories = list(first_eval_scores.keys()) if first_eval_scores else ["accuracy", "completeness", "relevance", "clarity"]
            dimension_scores = {cat: 0 for cat in current_categories}
            count = 0

            for test_case in prompt_results.get("test_cases", []):
                response_list = test_case.get("responses", [])
                if not response_list:
                    continue
                evaluation = response_list[0].get("evaluation")
                if evaluation and evaluation.get("scores"):
                    scores = evaluation["scores"]
                    for dim in current_categories:
                        if dim in scores and scores[dim] is not None:
                            dimension_scores[dim] += scores[dim]
                    count += 1
            
            if count > 0:
                for dim in dimension_scores:
                    dimension_scores[dim] /= count
                    dim_name = {"accuracy": "准确性", "completeness": "完整性", "relevance": "相关性", "clarity": "清晰度"}.get(dim, dim.capitalize())
                    if dimension_scores[dim] >= 85:
                        strengths.append(f"{dim_name}维度表现出色（{dimension_scores[dim]:.1f}分）")
                    elif dimension_scores[dim] < 70:
                        weaknesses.append(f"{dim_name}维度需要改进（{dimension_scores[dim]:.1f}分）")

            avg_tokens = 0
            token_count = 0
            for test_case in prompt_results.get("test_cases", []):
                response_list = test_case.get("responses", [])
                if not response_list:
                    continue
                evaluation = response_list[0].get("evaluation")
                if evaluation and "prompt_info" in evaluation:
                    prompt_info = evaluation["prompt_info"]
                    if "token_count" in prompt_info and prompt_info["token_count"] is not None:
                        avg_tokens += prompt_info["token_count"]
                        token_count += 1
            
            token_efficiency = "未知"
            avg_score_for_eff = prompt_data_summary["average_score"] 
            if token_count > 0 and avg_score_for_eff > 0: 
                avg_tokens = avg_tokens / token_count
                efficiency = avg_score_for_eff / avg_tokens * 100
                if efficiency > 0.5:
                    token_efficiency = "高"
                elif efficiency > 0.3:
                    token_efficiency = "中"
                else:
                    token_efficiency = "低"

            report["prompt_comparison"].append({
                "name": prompt_name,
                "average_score": avg_score_for_eff,
                "strengths": strengths,
                "weaknesses": weaknesses,
                "token_count": avg_tokens if token_count > 0 else "未知",
                "token_efficiency": token_efficiency
            })
        
        if report["prompt_comparison"]:
            sorted_prompts = sorted(report["prompt_comparison"], key=lambda x: x["average_score"], reverse=True)
            if sorted_prompts:
                best_prompt = sorted_prompts[0]
                report["recommendations"].append(f"最佳提示词是 '{best_prompt['name']}'，平均得分为 {best_prompt['average_score']:.1f}分。")
                if best_prompt["strengths"]:
                    report["recommendations"].append(f"其主要优势在于: {', '.join(best_prompt['strengths'])}")
                
                if len(sorted_prompts) > 1:
                    worst_prompt = sorted_prompts[-1]
                    score_diff = best_prompt["average_score"] - worst_prompt["average_score"]
                    if score_diff > 15:
                        report["recommendations"].append(f"提示词之间的性能差异显著，最佳与最差提示词的分数相差 {score_diff:.1f} 分。")
                        if worst_prompt["weaknesses"]:
                            report["recommendations"].append(f"表现最差的提示词 '{worst_prompt['name']}' 主要问题在于: {', '.join(worst_prompt['weaknesses'])}")

            token_efficiencies = [p.get("token_efficiency") for p in report["prompt_comparison"] if p.get("token_efficiency") != "未知"]
            if "低" in token_efficiencies:
                report["recommendations"].append("部分提示词的token效率较低，建议精简提示词结构，减少冗余内容，提高信息密度。")

    return report

def display_report(report: Dict) -> None:
    """在Streamlit中展示报告"""
    st.header("📊 测试结果分析报告")

    if report.get("is_model_comparison"):
        if "best_model" in report:
            st.subheader("🏆 最佳模型")
            st.success(
                f"**{report['best_model']['name']}** (平均得分: "
                f"{report['best_model']['score']:.1f}分)"
            )
        
        if report["model_comparison"]:
            st.subheader("📈 模型对比")
            comparison_data = {
                "模型": [],
                "平均得分": [],
                "Token数": [],
                "Token效率": [],
                "优势": [],
                "劣势": []
            }
            for model_comp in report["model_comparison"]:
                comparison_data["模型"].append(model_comp["name"])
                comparison_data["平均得分"].append(f"{model_comp['average_score']:.1f}")
                comparison_data["Token数"].append(str(model_comp["token_count"]))
                comparison_data["Token效率"].append(model_comp["token_efficiency"])
                comparison_data["优势"].append("\n".join(model_comp["strengths"]) if model_comp["strengths"] else "无特别优势")
                comparison_data["劣势"].append("\n".join(model_comp["weaknesses"]) if model_comp["weaknesses"] else "无明显劣势")
            st.dataframe(pd.DataFrame(comparison_data))

    else:
        if "best_prompt" in report:
            st.subheader("🏆 最佳提示词")
            st.success(
                f"**{report['best_prompt']['name']}** (平均得分: "
                f"{report['best_prompt']['score']:.1f}分)"
            )
        
        if report["prompt_comparison"]:
            st.subheader("📈 提示词对比")
            comparison_data = {
                "提示词": [],
                "平均得分": [],
                "Token数": [],
                "Token效率": [],
                "优势": [],
                "劣势": []
            }
            for prompt in report["prompt_comparison"]:
                comparison_data["提示词"].append(prompt["name"])
                comparison_data["平均得分"].append(f"{prompt['average_score']:.1f}")
                comparison_data["Token数"].append(str(prompt["token_count"]))
                comparison_data["Token效率"].append(prompt["token_efficiency"])
                comparison_data["优势"].append("\n".join(prompt["strengths"]) if prompt["strengths"] else "无特别优势")
                comparison_data["劣势"].append("\n".join(prompt["weaknesses"]) if prompt["weaknesses"] else "无明显劣势")
            st.dataframe(pd.DataFrame(comparison_data))

    if report["recommendations"]:
        st.subheader("💡 优化建议")
        for i, rec in enumerate(report["recommendations"]):
            st.markdown(f"{i+1}. {rec}")