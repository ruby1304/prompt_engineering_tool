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
        
        # 获取优化器和分析器模板
        self.optimizer_template = get_system_template("optimizer")
        self.problem_analyzer_template = get_system_template("problem_analyzer")  # 新增
    
    async def optimize_prompt(self, original_prompt: str, test_results: List[Dict], optimization_strategy: str = "balanced") -> Dict:
        """基于测试结果优化提示词"""
        # 使用LLM分析评估结果，提取关键问题
        problem_analysis = await self.analyze_evaluation_problems_with_llm(test_results)
        if "error" in problem_analysis:
            return problem_analysis  # 返回分析错误
        
        # 构建更详细的优化指导
        optimization_guidance = self.build_optimization_guidance(problem_analysis["analysis"], optimization_strategy)
        
        # 将测试结果格式化为摘要 (复用之前的逻辑，或者可以简化)
        results_summary = self.format_test_results_summary(test_results)
        
        # 使用系统模板而不是硬编码的提示词
        template = self.optimizer_template.get("template", "")
        optimization_prompt = template\
            .replace("{{original_prompt}}", original_prompt)\
            .replace("{{results_summary}}", results_summary)\
            .replace("{{problem_analysis}}", problem_analysis["analysis"])\
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

    def zero_shot_optimize_prompt_sync(self, task_desc: str, task_goal: str, constraints: str = "") -> Dict:
        """同步：0样本优化主流程"""
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            result = loop.run_until_complete(self.zero_shot_optimize_prompt(task_desc, task_goal, constraints))
            return result
        except Exception as e:
            import traceback
            traceback.print_exc()
            return {"error": f"0样本优化过程出错: {str(e)}"}
        finally:
            loop.close()

    async def zero_shot_optimize_prompt(self, task_desc: str, task_goal: str, constraints: str = "") -> Dict:
        """异步：0样本优化主流程"""
        # 获取0样本优化专用系统模板
        zero_shot_template = get_system_template("zero_shot_optimizer")
        template = zero_shot_template.get("template", "")
        # 构建优化提示词
        optimization_prompt = template \
            .replace("{{task_description}}", task_desc) \
            .replace("{{task_goal}}", task_goal) \
            .replace("{{constraints}}", constraints or "无")
        params = {"temperature": 0.8, "max_tokens": 2000}
        try:
            result = await self.client.generate(optimization_prompt, self.optimizer_model, params)
            opt_text = result.get("text", "")
            try:
                if "```json" in opt_text:
                    opt_text = opt_text.split("```json")[1].split("```", 1)[0].strip()
                elif "```" in opt_text:
                    opt_text = opt_text.split("```", 1)[1].split("```", 1)[0].strip()
                return json.loads(opt_text)
            except Exception:
                return {"error": "优化结果格式错误，无法解析为JSON", "raw_response": opt_text}
        except Exception as e:
            return {"error": f"0样本优化过程出错: {str(e)}"}

    async def analyze_evaluation_problems_with_llm(self, test_results: List[Dict]) -> Dict:
        """使用LLM分析评估结果中的主要问题"""
        # 格式化评估结果供LLM分析
        results_summary = self.format_test_results_summary_for_analysis(test_results)
        
        # 获取分析器模板
        template = self.problem_analyzer_template.get("template", "")
        if not template:
            return {"error": "未能加载问题分析器模板"}
            
        analysis_prompt = template.replace("{{evaluation_results_summary}}", results_summary)
        
        analysis_params = {
            "temperature": 0.3,  # 较低温度以获得更集中的分析
            "max_tokens": 1000
        }
        
        try:
            result = await self.client.generate(analysis_prompt, self.optimizer_model, analysis_params)
            analysis_text = result.get("text", "").strip()
            if not analysis_text:
                return {"error": "LLM未能生成问题分析"}
            return {"analysis": analysis_text}
        except Exception as e:
            return {"error": f"使用LLM分析问题时出错: {str(e)}"}

    def format_test_results_summary_for_analysis(self, test_results: List[Dict]) -> str:
        """将测试结果格式化为更适合LLM分析的摘要"""
        summary = ""
        for i, result in enumerate(test_results):
            summary += f"--- Test Case {i+1} ---\n"
            # 包含输入、输出、期望、分数和分析
            if "case_description" in result:
                summary += f"Description: {result['case_description']}\n"
            if "user_input" in result:
                summary += f"Input: {result['user_input']}\n"
            if "responses" in result:
                for j, resp in enumerate(result.get("responses", [])):
                    summary += f"  Response {j+1}:\n"
                    if "output" in resp:
                        summary += f"    Output: {resp['output']}\n"
                    if "evaluation" in resp and resp["evaluation"]:
                        eval_data = resp["evaluation"]
                        if "scores" in eval_data:
                            summary += f"    Scores: {json.dumps(eval_data['scores'])}\n"
                        if "overall_score" in eval_data:
                            summary += f"    Overall Score: {eval_data['overall_score']}\n"
                        if "analysis" in eval_data:
                            summary += f"    Analysis: {eval_data['analysis']}\n"
                    elif "error" in resp:
                        summary += f"    Error: {resp['error']}\n"
            elif "evaluation" in result:  # 兼容旧格式
                eval_data = result["evaluation"]
                if "scores" in eval_data:
                    summary += f"  Scores: {json.dumps(eval_data['scores'])}\n"
                if "overall_score" in eval_data:
                    summary += f"  Overall Score: {eval_data['overall_score']}\n"
                if "analysis" in eval_data:
                    summary += f"  Analysis: {eval_data['analysis']}\n"
            summary += "\n"
        return summary

    def build_optimization_guidance(self, problem_analysis: str, strategy: str) -> str: 
        """构建优化指导""" 
        strategy_guidance = { "accuracy": "提高响应的准确性，确保输出与预期结果精确匹配", "completeness": "确保响应全面覆盖所有必要信息，不遗漏关键内容", "conciseness": "使提示词更简洁有效，移除冗余内容，保持核心指令清晰", "balanced": "平衡改进所有维度，注重整体性能提升" }
        strategy_text = strategy_guidance.get(strategy, strategy_guidance["balanced"])

        guidance = f"""
优化策略: {strategy_text}

基于LLM的问题分析总结:
{problem_analysis}

请根据以上分析和策略，重点优化提示词。
提示词优化技巧参考:
- 明确角色和期望
- 提供具体约束
- 细化指令语言
- 结构优化
- 示例引导
请确保优化后的提示词保留原始目标和功能，同时解决已识别的问题。 """
        return guidance

    def format_test_results_summary(self, test_results: List[Dict]) -> str: 
        """将测试结果格式化为摘要 (简化版，供优化器使用)""" 
        summary = ""
        scores = []
        analyses_texts = []
        for i, result in enumerate(test_results):
            eval_data = None
            if "responses" in result:
                for resp in result.get("responses", []):
                    if resp.get("evaluation"):
                        eval_data = resp["evaluation"]
                        break
            elif "evaluation" in result:
                eval_data = result["evaluation"]
            
            if eval_data:
                if "overall_score" in eval_data:
                    scores.append(eval_data["overall_score"])
                if "analysis" in eval_data:
                    analyses_texts.append(f"Case {i+1}: {eval_data['analysis']}")

        avg_score = sum(scores) / len(scores) if scores else 0
        summary += f"平均总分: {avg_score:.1f}\n"
        summary += "部分评估分析摘要:\n" + "\n".join(analyses_texts[:3])
        return summary

    def iterative_prompt_optimization_sync(
        self,
        initial_prompt: str,
        test_set: List[Dict],
        evaluator,
        optimization_strategy: str = "balanced",
        model: str = None,
        provider: str = None,
        max_iterations: int = 3,
        progress_callback=None
    ) -> Dict:
        """
        自动多轮提示词优化主流程（同步）。
        参数：
            initial_prompt: 初始提示词内容
            test_set: 测试用例列表
            evaluator: 评估器实例（需有run_evaluation方法）
            optimization_strategy: 优化策略
            model/provider: 用于评估的模型及提供商
            max_iterations: 迭代次数
            progress_callback: 进度回调（可选）
        返回：
            {
                'best_prompt': 最优提示词内容,
                'best_score': 最优分数,
                'history': 每轮优化与评估详情
            }
        """
        current_prompt = initial_prompt
        best_prompt = initial_prompt
        best_score = -float('inf')
        history = []
        for i in range(max_iterations):
            # 创建评估任务列表
            evaluation_tasks = []
            for test_case in test_set:
                user_input = test_case.get("user_input", "")
                expected_output = test_case.get("expected_output", "")
                criteria = test_case.get("criteria", {})
                # 准备模型调用
                client = get_client(provider) if provider else None
                if not client:
                    continue
                # 生成响应
                try:
                    response = client.generate_sync(
                        current_prompt + "\n\n" + user_input,
                        model,
                        {"temperature": 0.7, "max_tokens": 2000}
                    )
                    model_response = response.get("text", "")
                    # 创建评估任务
                    evaluation_tasks.append({
                        "model_response": model_response,
                        "expected_output": expected_output,
                        "criteria": criteria,
                        "prompt": current_prompt
                    })
                except Exception as e:
                    print(f"Error generating response: {e}")
                    continue
            
            # 执行评估
            eval_results = evaluator.run_evaluation(evaluation_tasks)
            avg_score = self._calc_avg_score(eval_results)
            history.append({
                'iteration': i+1,
                'prompt': current_prompt,
                'eval_results': eval_results,
                'avg_score': avg_score
            })
            if avg_score > best_score:
                best_score = avg_score
                best_prompt = current_prompt
            if progress_callback:
                progress_callback(i+1, max_iterations, avg_score)
            opt_result = self.optimize_prompt_sync(
                current_prompt, eval_results, optimization_strategy
            )
            optimized_prompts = opt_result.get('optimized_prompts', [])
            if not optimized_prompts:
                break
            best_opt_prompt = current_prompt
            best_opt_score = avg_score
            for opt in optimized_prompts:
                opt_prompt = opt.get('prompt', '')
                # 创建评估任务列表
                opt_evaluation_tasks = []
                for test_case in test_set:
                    user_input = test_case.get("user_input", "")
                    expected_output = test_case.get("expected_output", "")
                    criteria = test_case.get("criteria", {})
                    # 准备模型调用
                    client = get_client(provider) if provider else None
                    if not client:
                        continue
                    # 生成响应
                    try:
                        response = client.generate_sync(
                            opt_prompt + "\n\n" + user_input,
                            model,
                            {"temperature": 0.7, "max_tokens": 2000}
                        )
                        model_response = response.get("text", "")
                        # 创建评估任务
                        opt_evaluation_tasks.append({
                            "model_response": model_response,
                            "expected_output": expected_output,
                            "criteria": criteria,
                            "prompt": opt_prompt
                        })
                    except Exception as e:
                        print(f"Error generating response: {e}")
                        continue
                
                opt_eval_results = evaluator.run_evaluation(opt_evaluation_tasks)
                opt_avg_score = self._calc_avg_score(opt_eval_results)
                history.append({
                    'iteration': i+1,
                    'prompt': opt_prompt,
                    'eval_results': opt_eval_results,
                    'avg_score': opt_avg_score
                })
                if opt_avg_score > best_opt_score:
                    best_opt_score = opt_avg_score
                    best_opt_prompt = opt_prompt
            current_prompt = best_opt_prompt
            if best_opt_score > best_score:
                best_score = best_opt_score
                best_prompt = best_opt_prompt
        return {
            'best_prompt': best_prompt,
            'best_score': best_score,
            'history': history
        }

    def _calc_avg_score(self, eval_results: List[Dict]) -> float:
        """计算评估结果的平均分"""
        scores = []
        for r in eval_results:
            if 'overall_score' in r and isinstance(r['overall_score'], (int, float)):
                scores.append(r['overall_score'])
        return sum(scores)/len(scores) if scores else 0