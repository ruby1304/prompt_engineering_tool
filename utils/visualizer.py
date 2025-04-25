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
            evaluation = test_case.get("evaluation") or {}
            score_dict = evaluation.get("scores") or {}
            for score_name, score_value in score_dict.items():
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
        avg_tokens = 0
        count = 0
        
        for test_case in prompt_results.get("test_cases", []):
            if "prompt_info" in test_case.get("evaluation", {}):
                avg_tokens += test_case["evaluation"]["prompt_info"]["token_count"]
                count += 1
        
        if count > 0:
            prompts.append(prompt_name)
            token_counts.append(avg_tokens / count)
    
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
    categories = ["accuracy", "completeness", "relevance", "clarity"]
    category_names = {
        "accuracy": "准确性",
        "completeness": "完整性",
        "relevance": "相关性", 
        "clarity": "清晰度"
    }
    
    fig = go.Figure()
    
    for prompt_name in prompt_names:
        prompt_results = results[prompt_name]
        
        # 计算各维度的平均分
        category_scores = {cat: 0 for cat in categories}
        count = 0
        
        for test_case in prompt_results.get("test_cases", []):
            for cat in categories:
                if cat in test_case.get("evaluation", {}).get("scores", {}):
                    category_scores[cat] += test_case["evaluation"]["scores"][cat]
            count += 1
        
        if count > 0:
            for cat in categories:
                category_scores[cat] /= count
        
        # 添加雷达图
        fig.add_trace(go.Scatterpolar(
            r=[category_scores[cat] for cat in categories],
            theta=[category_names[cat] for cat in categories],
            fill='toself',
            name=prompt_name
        ))
    
    fig.update_layout(
        polar=dict(
            radialaxis=dict(
                visible=True,
                range=[0, 100]
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
        "recommendations": []
    }
    
    # 计算每个提示词的平均得分
    for prompt_name, prompt_results in results.items():
        overall_scores = []
        for test_case in prompt_results.get("test_cases", []):
            if "overall_score" in test_case.get("evaluation", {}):
                overall_scores.append(test_case["evaluation"]["overall_score"])
        
        if overall_scores:
            avg_score = sum(overall_scores) / len(overall_scores)
            report["summary"][prompt_name] = {
                "average_score": avg_score,
                "test_cases_count": len(overall_scores)
            }
    
    # 找出最佳提示词
    if report["summary"]:
        best_prompt = max(report["summary"].items(), key=lambda x: x[1]["average_score"])
        report["best_prompt"] = {
            "name": best_prompt[0],
            "score": best_prompt[1]["average_score"]
        }
    
    # 提示词对比
    for prompt_name, prompt_data in report["summary"].items():
        strengths = []
        weaknesses = []
        
        # 分析强项和弱项
        prompt_results = results[prompt_name]
        dimension_scores = {"accuracy": 0, "completeness": 0, "relevance": 0, "clarity": 0}
        count = 0
        
        for test_case in prompt_results.get("test_cases", []):
            for dim, score in test_case.get("evaluation", {}).get("scores", {}).items():
                dimension_scores[dim] += score
            count += 1
        
        if count > 0:
            for dim in dimension_scores:
                dimension_scores[dim] /= count
                if dimension_scores[dim] >= 85:
                    strengths.append(f"{dim}维度表现出色（{dimension_scores[dim]:.1f}分）")
                elif dimension_scores[dim] < 70:
                    weaknesses.append(f"{dim}维度需要改进（{dimension_scores[dim]:.1f}分）")
        
        # 计算Token效率
        avg_tokens = 0
        token_count = 0
        for test_case in prompt_results.get("test_cases", []):
            if "prompt_info" in test_case.get("evaluation", {}):
                avg_tokens += test_case["evaluation"]["prompt_info"]["token_count"]
                token_count += 1
        
        token_efficiency = "未知"
        if token_count > 0:
            avg_tokens = avg_tokens / token_count
            if prompt_data["average_score"] > 0:
                # 定义效率为分数/token数的比率
                efficiency = prompt_data["average_score"] / avg_tokens * 100
                if efficiency > 0.5:
                    token_efficiency = "高"
                elif efficiency > 0.3:
                    token_efficiency = "中"
                else:
                    token_efficiency = "低"
        
        report["prompt_comparison"].append({
            "name": prompt_name,
            "average_score": prompt_data["average_score"],
            "strengths": strengths,
            "weaknesses": weaknesses,
            "token_count": avg_tokens if token_count > 0 else "未知",
            "token_efficiency": token_efficiency
        })
    
    # 生成建议
    if report["prompt_comparison"]:
        # 按平均分排序
        sorted_prompts = sorted(report["prompt_comparison"], 
                               key=lambda x: x["average_score"], reverse=True)
        
        # 提取最佳提示词的特点
        if sorted_prompts:
            best_prompt = sorted_prompts[0]
            report["recommendations"].append(
                f"最佳提示词是 '{best_prompt['name']}'，平均得分为 {best_prompt['average_score']:.1f}分。"
            )
            
            if best_prompt["strengths"]:
                report["recommendations"].append(
                    f"其主要优势在于: {', '.join(best_prompt['strengths'])}"
                )
            
            # 如果有多个提示词，分析差异
            if len(sorted_prompts) > 1:
                worst_prompt = sorted_prompts[-1]
                score_diff = best_prompt["average_score"] - worst_prompt["average_score"]
                
                if score_diff > 15:
                    report["recommendations"].append(
                        f"提示词之间的性能差异显著，最佳与最差提示词的分数相差 {score_diff:.1f} 分。"
                    )
                    
                    if worst_prompt["weaknesses"]:
                        report["recommendations"].append(
                            f"表现最差的提示词 '{worst_prompt['name']}' 主要问题在于: "
                            f"{', '.join(worst_prompt['weaknesses'])}"
                        )
    
    # 对token效率的建议
    token_efficiencies = [p.get("token_efficiency") for p in report["prompt_comparison"] 
                         if p.get("token_efficiency") != "未知"]
    
    if "低" in token_efficiencies:
        report["recommendations"].append(
            "部分提示词的token效率较低，建议精简提示词结构，减少冗余内容，提高信息密度。"
        )
    
    return report

def display_report(report: Dict) -> None:
    """在Streamlit中展示报告"""
    st.header("📊 测试结果分析报告")
    
    # 显示最佳提示词
    if "best_prompt" in report:
        st.subheader("🏆 最佳提示词")
        st.success(
            f"**{report['best_prompt']['name']}** (平均得分: "
            f"{report['best_prompt']['score']:.1f}分)"
        )
    
    # 显示提示词对比
    if report["prompt_comparison"]:
        st.subheader("📈 提示词对比")
        
        # 创建表格数据
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
    
    # 显示建议
    if report["recommendations"]:
        st.subheader("💡 优化建议")
        for i, rec in enumerate(report["recommendations"]):
            st.markdown(f"{i+1}. {rec}")