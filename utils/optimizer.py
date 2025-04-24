import json
import asyncio
from typing import Dict, List, Optional, Any, Tuple

from models.api_clients import get_client, get_provider_from_model
from config import load_config, get_system_template

class PromptOptimizer:
    """提示词自动优化器"""
    def __init__(self):
        config = load_config()
        self.optimizer_model = config.get("evaluator_model", "gpt-4")  # 使用与评估相同的模型
        self.provider = get_provider_from_model(self.optimizer_model)
        self.client = get_client(self.provider)
        
        # 获取优化器模板
        self.optimizer_template = get_system_template("optimizer")
    
    async def optimize_prompt(self, original_prompt: str, test_results: List[Dict], optimization_strategy: str = "balanced") -> Dict:
        """基于测试结果优化提示词"""
        # 分析评估结果，提取关键问题
        problem_analysis = self.analyze_evaluation_problems(test_results)
        
        # 构建更详细的优化指导
        optimization_guidance = self.build_optimization_guidance(problem_analysis, optimization_strategy)
        
        # 将测试结果格式化为摘要
        results_summary = self.format_test_results_summary(test_results)
        
        # 使用系统模板而不是硬编码的提示词
        template = self.optimizer_template.get("template", "")
        optimization_prompt = template\
            .replace("{{original_prompt}}", original_prompt)\
            .replace("{{results_summary}}", results_summary)\
            .replace("{{problem_analysis}}", problem_analysis)\
            .replace("{{optimization_guidance}}", optimization_guidance)
        
        optimization_params = {
            "temperature": 0.7,  # 适当提高温度以获得更多样化的优化结果
            "max_tokens": 4000
        }
        
        try:
            result = await self.client.generate(optimization_prompt, self.optimizer_model, optimization_params)
            opt_text = result.get("text", "")
            
            # 尝试解析JSON结果
            try:
                # 清理可能的前后缀文本
                if "```json" in opt_text:
                    opt_text = opt_text.split("```json")[1].split("```")[0].strip()
                elif "```" in opt_text:
                    opt_text = opt_text.split("```")[1].split("```")[0].strip()
                
                return json.loads(opt_text)
            except json.JSONDecodeError:
                # 解析失败，返回错误信息
                return {
                    "error": "优化结果格式错误，无法解析为JSON",
                    "raw_response": opt_text
                }
        except Exception as e:
            return {
                "error": f"优化过程出错: {str(e)}"
            }
            
    def optimize_prompt_sync(self, original_prompt: str, test_results: List[Dict], optimization_strategy: str = "balanced") -> Dict:
        """同步版本的优化函数（包装异步函数）"""
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            result = loop.run_until_complete(self.optimize_prompt(
                original_prompt, test_results, optimization_strategy
            ))
            return result
        except Exception as e:
            import traceback
            traceback.print_exc()
            return {"error": f"优化过程出错: {str(e)}"}
        finally:
            loop.close()

    def analyze_evaluation_problems(self, test_results: List[Dict]) -> str:
        """分析评估结果中的主要问题"""
        # 初始化各维度的分数统计
        dimension_scores = {
            "accuracy": {"total": 0, "count": 0},
            "completeness": {"total": 0, "count": 0},
            "relevance": {"total": 0, "count": 0},
            "clarity": {"total": 0, "count": 0}
        }
        
        # 收集所有分析文本
        all_analyses = []
        
        # 处理不同格式的评估结果
        for result in test_results:
            # 如果是完整的评估结果对象（含scores和analysis）
            if "scores" in result:
                for dim, score in result["scores"].items():
                    if dim in dimension_scores:
                        dimension_scores[dim]["total"] += score
                        dimension_scores[dim]["count"] += 1
                
                if "analysis" in result:
                    all_analyses.append(result["analysis"])
            
            # 如果是来自responses的评估结果
            elif "evaluation" in result and result["evaluation"]:
                eval_result = result["evaluation"]
                if "scores" in eval_result:
                    for dim, score in eval_result["scores"].items():
                        if dim in dimension_scores:
                            dimension_scores[dim]["total"] += score
                            dimension_scores[dim]["count"] += 1
                
                if "analysis" in eval_result:
                    all_analyses.append(eval_result["analysis"])
            
            # 如果是测试用例
            elif "responses" in result:
                for resp in result.get("responses", []):
                    if resp.get("evaluation"):
                        eval_result = resp["evaluation"]
                        if "scores" in eval_result:
                            for dim, score in eval_result["scores"].items():
                                if dim in dimension_scores:
                                    dimension_scores[dim]["total"] += score
                                    dimension_scores[dim]["count"] += 1
                        
                        if "analysis" in eval_result:
                            all_analyses.append(eval_result["analysis"])
        
        # 计算各维度的平均分数
        dimension_averages = {}
        for dim, data in dimension_scores.items():
            if data["count"] > 0:
                dimension_averages[dim] = data["total"] / data["count"]
            else:
                dimension_averages[dim] = 0
        
        # 找出得分最低的维度
        weakest_dimensions = []
        for dim, avg in sorted(dimension_averages.items(), key=lambda x: x[1]):
            if avg < 75:  # 假设75分以下需要改进
                weakest_dimensions.append(f"{dim} ({avg:.1f}分)")
        
        # 从分析文本中提取常见问题
        common_problems = self.extract_common_problems(all_analyses)
        
        # 构建问题分析文本
        problem_analysis = "根据评估结果，以下是主要需要改进的方面:\n\n"
        
        if weakest_dimensions:
            problem_analysis += f"1. 最薄弱的维度: {', '.join(weakest_dimensions)}\n\n"
        
        if common_problems:
            problem_analysis += f"2. 常见问题:\n"
            for i, problem in enumerate(common_problems):
                problem_analysis += f"   - {problem}\n"
        
        return problem_analysis


    def extract_common_problems(self, analyses: List[str]) -> List[str]: 
        """从分析文本中提取常见问题""" 
        # 这里可以使用简单的文本分析或关键词匹配 
        # 在实际实现中，可以使用更复杂的NLP技术
        common_problems = []
        problem_indicators = [
            "缺乏", "不足", "不够", "没有", "缺少", 
            "过于", "太", "不清晰", "模糊",
            "未能", "失败", "错误", "不准确", "偏离"
        ]

        for analysis in analyses:
            sentences = analysis.split(". ")
            for sentence in sentences:
                for indicator in problem_indicators:
                    if indicator in sentence and sentence not in common_problems:
                        common_problems.append(sentence)
                        break

        # 限制问题数量
        return common_problems[:5]  # 返回最多5个常见问题

    def build_optimization_guidance(self, problem_analysis: str, strategy: str) -> str: 
        """构建优化指导""" 
        strategy_guidance = { "accuracy": "提高响应的准确性，确保输出与预期结果精确匹配", "completeness": "确保响应全面覆盖所有必要信息，不遗漏关键内容", "conciseness": "使提示词更简洁有效，移除冗余内容，保持核心指令清晰", "balanced": "平衡改进所有维度，注重整体性能提升" }
        # 基于策略的通用优化指导
        strategy_text = strategy_guidance.get(strategy, strategy_guidance["balanced"])

        # 构建完整的优化指导
        guidance = f"""
优化策略: {strategy_text}

基于问题分析，请重点关注以下方面: {problem_analysis}

提示词优化技巧:

明确角色和期望 - 清晰定义模型扮演的角色和预期输出格式
提供具体约束 - 添加明确的限制条件和边界
细化指令语言 - 使用准确、无歧义的语言
结构优化 - 改进提示词的逻辑组织和层次结构
示例引导 - 考虑添加少量示例以引导模型理解期望
请确保优化后的提示词保留原始目标和功能，同时解决已识别的问题。 """
        return guidance

    def format_test_results_summary(self, test_results: List[Dict]) -> str: 
        """将测试结果格式化为摘要""" 
        summary = ""
        for i, result in enumerate(test_results):
            overall_score = result.get("overall_score", "N/A")
            
            summary += f"测试用例 {i+1}:\n"
            summary += f"  总分: {overall_score}\n"
            
            if "scores" in result:
                summary += "  维度分数:\n"
                for dim, score in result["scores"].items():
                    summary += f"    - {dim}: {score}\n"
            
            if "analysis" in result:
                summary += f"  分析: {result['analysis']}\n"
            
            summary += "\n"

        return summary