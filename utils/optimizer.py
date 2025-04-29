import json
import asyncio
import concurrent.futures
import threading
from typing import Dict, List, Optional, Any, Tuple

from models.api_clients import get_client, get_provider_from_model
from config import load_config, get_system_template
# 导入新的并行执行器
from utils.parallel_executor import execute_model, execute_models, execute_model_sync, execute_models_sync

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
        # 输出调试信息，检查传入的测试结果数量
        print(f"[调试-优化器] 收到 {len(test_results)} 条评估结果")
        
        # 使用LLM分析评估结果，提取关键问题
        problem_analysis = await self.analyze_evaluation_problems_with_llm(test_results)
        if "error" in problem_analysis:
            print(f"[错误-优化器] 分析问题出错: {problem_analysis['error']}")
            return problem_analysis  # 返回分析错误
        
        # 构建更详细的优化指导
        optimization_guidance = self.build_optimization_guidance(problem_analysis["analysis"], optimization_strategy)
        
        # 将测试结果格式化为摘要
        results_summary = self.format_test_results_summary(test_results)
        
        # 使用系统模板而不是硬编码的提示词
        template = self.optimizer_template.get("template", "")
        optimization_prompt = template\
            .replace("{{original_prompt}}", original_prompt)\
            .replace("{{results_summary}}", results_summary)\
            .replace("{{problem_analysis}}", problem_analysis["analysis"])\
            .replace("{{optimization_guidance}}", optimization_guidance)
        
        print(f"[调试-优化器] 已准备优化提示词，长度: {len(optimization_prompt)} 字符")
        
        optimization_params = {
            "temperature": 0.8,  # 增加温度以确保更多样化的优化结果
            "max_tokens": 4000
        }
        
        try:
            # 使用新的并行执行器
            result = await execute_model(
                self.optimizer_model,
                prompt=optimization_prompt,
                provider=self.provider,
                params=optimization_params
            )
            
            opt_text = result.get("text", "")
            print(f"[调试-优化器] 收到优化响应，长度: {len(opt_text)} 字符")
            
            # 尝试解析JSON结果
            try:
                # 清理可能的前后缀文本
                if "```json" in opt_text:
                    opt_text = opt_text.split("```json")[1].split("```")[0].strip()
                elif "```" in opt_text:
                    opt_text = opt_text.split("```")[1].split("```")[0].strip()
                
                parsed_result = json.loads(opt_text)
                
                # 检查结果是否包含优化提示词数组
                if "optimized_prompts" in parsed_result and isinstance(parsed_result["optimized_prompts"], list):
                    optimized_prompts = parsed_result["optimized_prompts"]
                    print(f"[调试-优化器] 成功解析 {len(optimized_prompts)} 个优化提示词")
                    
                    # 确保至少有一个包含有效提示词的版本
                    valid_prompts = [p for p in optimized_prompts if p.get("prompt")]
                    if not valid_prompts:
                        print("[警告-优化器] 解析出的优化提示词列表中没有有效的提示词")
                        # 添加一个默认的优化版本
                        optimized_prompts.append({
                            "strategy": "默认微调优化",
                            "problem_addressed": "提示词可能需要整体改进",
                            "expected_improvements": "提高整体响应质量",
                            "prompt": original_prompt + "\n\n请确保你的回答准确、全面、简洁，并满足用户的所有要求。"
                        })
                        print("[调试-优化器] 已添加一个默认的优化版本")
                    
                    return parsed_result
                else:
                    print("[错误-优化器] 返回的JSON中没有optimized_prompts字段或格式不正确")
                    return {
                        "error": "优化结果格式错误，缺少optimized_prompts字段",
                        "raw_response": opt_text,
                        "optimized_prompts": [{
                            "strategy": "默认优化",
                            "problem_addressed": "无法从API获取有效的优化结果",
                            "expected_improvements": "确保至少有一个可用的优化版本",
                            "prompt": original_prompt + "\n\n请提供更详细、准确、结构化的回答，并确保解决用户的所有问题要点。"
                        }]
                    }
            except json.JSONDecodeError as e:
                print(f"[错误-优化器] JSON解析失败: {e}")
                # 即使解析失败也返回至少一个优化版本
                return {
                    "error": f"优化结果格式错误，无法解析为JSON: {str(e)}",
                    "raw_response": opt_text,
                    "optimized_prompts": [{
                        "strategy": "默认优化",
                        "problem_addressed": "无法解析API返回的优化结果",
                        "expected_improvements": "提供至少一个可用的优化版本",
                        "prompt": original_prompt + "\n\n请确保回答详细、准确、有条理，并解决用户的全部需求。"
                    }]
                }
        except Exception as e:
            print(f"[严重错误-优化器] 优化过程出现异常: {e}")
            # 返回错误信息，但也提供一个默认的优化版本
            return {
                "error": f"优化过程出错: {str(e)}",
                "optimized_prompts": [{
                    "strategy": "故障保护优化",
                    "problem_addressed": "API调用失败",
                    "expected_improvements": "确保有一个可用的优化版本",
                    "prompt": original_prompt + "\n\n请提供详尽、准确、有结构的回答，并确保完整解决用户的问题。"
                }]
            }
        
    def optimize_prompt_sync(self, original_prompt: str, test_results: List[Dict], optimization_strategy: str = "balanced") -> Dict:
        """同步版本的优化函数（包装异步函数）"""
        print(f"[调试-优化器-同步] 开始优化提示词，策略: {optimization_strategy}")
        
        # 检查是否已存在事件循环
        try:
            loop = asyncio.get_event_loop()
            if loop.is_closed():
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
        except RuntimeError:
            # 如果没有事件循环，创建一个新的
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        
        try:
            result = loop.run_until_complete(self.optimize_prompt(
                original_prompt, test_results, optimization_strategy
            ))
            
            # 检查结果是否有效
            if "optimized_prompts" not in result or not result["optimized_prompts"]:
                print("[警告-优化器-同步] 没有生成优化提示词，添加默认版本")
                result["optimized_prompts"] = [{
                    "strategy": "默认优化策略",
                    "problem_addressed": "原始提示词可能存在不足",
                    "expected_improvements": "提高整体响应质量",
                    "prompt": original_prompt + "\n\n请确保你的回答详尽、准确、清晰，并完全满足用户的需求。"
                }]
            
            print(f"[调试-优化器-同步] 优化完成，生成了 {len(result.get('optimized_prompts', []))} 个优化版本")
            return result
        except Exception as e:
            print(f"[严重错误-优化器-同步] 同步优化过程出现异常: {e}")
            import traceback
            traceback.print_exc()
            # 即使出错也返回至少一个优化版本
            return {
                "error": f"优化过程出错: {str(e)}",
                "optimized_prompts": [{
                    "strategy": "故障恢复优化",
                    "problem_addressed": "同步优化过程失败",
                    "expected_improvements": "确保至少有一个优化版本可用",
                    "prompt": original_prompt + "\n\n请确保你的回答全面、准确、简洁，并完全解决用户的需求。"
                }]
            }
        # 注意：不在这里关闭事件循环，因为它可能会被其他代码继续使用

    def zero_shot_optimize_prompt_sync(self, task_desc: str, task_goal: str, constraints: str = "") -> Dict:
        """同步：0样本优化主流程"""
        print(f"[调试-优化器-同步] 开始0样本优化，目标: {task_goal}")
        
        # 检查是否已存在事件循环
        try:
            loop = asyncio.get_event_loop()
            if loop.is_closed():
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
        except RuntimeError:
            # 如果没有事件循环，创建一个新的
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
        try:
            result = loop.run_until_complete(self.zero_shot_optimize_prompt(task_desc, task_goal, constraints))
            return result
        except Exception as e:
            import traceback
            traceback.print_exc()
            return {"error": f"0样本优化过程出错: {str(e)}"}
        # 注意：不在这里关闭事件循环，因为它可能会被其他代码继续使用

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
            # 使用新的并行执行器
            result = await execute_model(
                self.optimizer_model,
                prompt=optimization_prompt,
                provider=self.provider,
                params=params
            )
            
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
            # 使用新的并行执行器
            result = await execute_model(
                self.optimizer_model,
                prompt=analysis_prompt,
                provider=self.provider,
                params=analysis_params
            )
            
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
        支持并行生成和评估，并在每步调用进度回调。
        """
        print(f"[调试] 开始迭代优化，计划执行 {max_iterations} 轮迭代")
        current_prompt = initial_prompt
        best_prompt = initial_prompt
        best_score = -float('inf')
        history = []
        total_cases = len(test_set)
        total_eval_per_iter = total_cases
        
        # 创建一个事件循环，用于整个优化过程
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        try:
            for i in range(max_iterations):
                print(f"[调试] 开始第 {i+1}/{max_iterations} 轮迭代")
                # 准备迭代的请求
                requests = []
                for idx, test_case in enumerate(test_set):
                    user_input = test_case.get("user_input", "")
                    expected_output = test_case.get("expected_output", "")
                    criteria = test_case.get("evaluation_criteria", {})
                    
                    # 准备请求
                    request = {
                        "model": model,
                        "provider": provider,
                        "prompt": current_prompt + "\n\n" + user_input,
                        "params": {
                            "temperature": 0.7,
                            "max_tokens": 2000
                        },
                        "context": {
                            "expected_output": expected_output,
                            "criteria": criteria,
                            "prompt": current_prompt,
                            "idx": idx
                        }
                    }
                    requests.append(request)
                
                # 使用并行执行器批量处理请求
                print(f"[调试] 第 {i+1} 轮发送 {len(requests)} 个请求进行评估")
                responses = execute_models_sync(requests)
                
                # 处理模型响应
                evaluation_tasks = []
                for response in responses:
                    context = response.get("context", {})
                    idx = context.get("idx", -1)
                    
                    if not response.get("error") and response.get("text"):
                        evaluation_tasks.append({
                            "model_response": response.get("text", ""),
                            "expected_output": context.get("expected_output", ""),
                            "criteria": context.get("criteria", {}),
                            "prompt": context.get("prompt", ""),
                            "idx": idx
                        })
                    
                    # 更新进度
                    if progress_callback:
                        progress_callback(
                            i+1, max_iterations, idx+1, total_eval_per_iter,
                            i*total_eval_per_iter + idx+1, max_iterations*total_eval_per_iter,
                            stage="gen"
                        )
                
                # 批量评估所有响应，而不是一个一个评估
                eval_results = []
                if evaluation_tasks:
                    # 使用事件循环的run_until_complete方法运行异步的批量评估
                    try:
                        # 使用单一批处理而不是多次调用
                        print(f"[调试] 第 {i+1} 轮评估 {len(evaluation_tasks)} 个响应")
                        eval_results = loop.run_until_complete(evaluator.run_evaluation_async(evaluation_tasks))
                        
                        # 更新进度 - 一次性更新所有评估的进度
                        if progress_callback:
                            for idx in range(len(evaluation_tasks)):
                                progress_callback(
                                    i+1, max_iterations, idx+1, len(evaluation_tasks),
                                    i*total_eval_per_iter + idx+1, max_iterations*total_eval_per_iter,
                                    stage="eval"
                                )
                    except Exception as e:
                        print(f"[批量评估错误]: {e}")
                
                # 计算平均分数
                avg_score = self._calc_avg_score(eval_results)
                print(f"[调试] 第 {i+1} 轮当前提示词评估完成，平均分: {avg_score:.2f}")
                
                # 记录本轮结果
                history.append({
                    'iteration': i+1,
                    'stage': 'initial',  # 标记为初始提示词
                    'prompt': current_prompt,
                    'eval_results': eval_results,
                    'avg_score': avg_score
                })
                
                # 更新最佳结果
                if avg_score > best_score:
                    best_score = avg_score
                    best_prompt = current_prompt
                
                # 更新进度
                if progress_callback:
                    progress_callback(
                        i+1, max_iterations, total_eval_per_iter, total_eval_per_iter,
                        (i+1)*total_eval_per_iter, max_iterations*total_eval_per_iter, 
                        stage="eval_done", avg_score=avg_score
                    )
                
                # 如果是最后一轮迭代，可以跳过生成优化提示词的步骤
                if i == max_iterations - 1:
                    print(f"[调试] 这是最后一轮迭代 ({i+1}/{max_iterations})，跳过优化步骤")
                    break
                    
                # 进行优化
                print(f"[调试] 第 {i+1} 轮开始优化提示词")
                opt_result = self.optimize_prompt_sync(
                    current_prompt, eval_results, optimization_strategy
                )
                
                # 处理优化结果
                optimized_prompts = opt_result.get('optimized_prompts', [])
                print(f"[调试] 第 {i+1} 轮生成了 {len(optimized_prompts)} 个优化版本")
                
                # 如果没有生成优化提示词，继续使用当前提示词进行下一轮迭代
                if not optimized_prompts:
                    print(f"[警告] 第 {i+1} 轮未能生成优化版本，使用当前提示词继续")
                    continue
                    
                # 对优化后的提示词进行评估
                best_opt_prompt = current_prompt
                best_opt_score = avg_score
                
                # 为每个优化版本创建记录
                all_opt_versions = []
                
                for opt_idx, opt in enumerate(optimized_prompts):
                    opt_prompt = opt.get('prompt', '')
                    opt_strategy = opt.get('strategy', '')
                    
                    print(f"[调试] 第 {i+1} 轮评估优化版本 {opt_idx+1}: {opt_strategy}")
                    
                    # 准备优化提示词的评估请求
                    opt_requests = []
                    for idx, test_case in enumerate(test_set):
                        user_input = test_case.get("user_input", "")
                        expected_output = test_case.get("expected_output", "")
                        criteria = test_case.get("evaluation_criteria", {})
                        
                        # 准备请求
                        request = {
                            "model": model,
                            "provider": provider,
                            "prompt": opt_prompt + "\n\n" + user_input,
                            "params": {
                                "temperature": 0.7,
                                "max_tokens": 2000
                            },
                            "context": {
                                "expected_output": expected_output,
                                "criteria": criteria,
                                "prompt": opt_prompt,
                                "idx": idx
                            }
                        }
                        opt_requests.append(request)
                    
                    # 使用并行执行器批量处理优化提示词的请求
                    opt_responses = execute_models_sync(opt_requests)
                    
                    # 处理优化提示词的响应
                    opt_evaluation_tasks = []
                    for opt_response in opt_responses:
                        context = opt_response.get("context", {})
                        idx = context.get("idx", -1)
                        
                        if not opt_response.get("error") and opt_response.get("text"):
                            opt_evaluation_tasks.append({
                                "model_response": opt_response.get("text", ""),
                                "expected_output": context.get("expected_output", ""),
                                "criteria": context.get("criteria", {}),
                                "prompt": context.get("prompt", ""),
                                "idx": idx
                            })
                        
                        # 更新进度
                        if progress_callback:
                            progress_callback(
                                i+1, max_iterations, idx+1, total_eval_per_iter,
                                i*total_eval_per_iter + idx+1, max_iterations*total_eval_per_iter,
                                stage="opt_gen"
                            )
                    
                    # 评估优化提示词的响应 - 同样使用批处理方式
                    opt_eval_results = []
                    if opt_evaluation_tasks:
                        try:
                            # 使用单一批处理方式进行评估
                            opt_eval_results = loop.run_until_complete(evaluator.run_evaluation_async(opt_evaluation_tasks))
                            
                            # 更新进度 - 一次性更新所有评估的进度
                            if progress_callback:
                                for idx in range(len(opt_evaluation_tasks)):
                                    progress_callback(
                                        i+1, max_iterations, idx+1, len(opt_evaluation_tasks),
                                        i*total_eval_per_iter + idx+1, max_iterations*total_eval_per_iter,
                                        stage="opt_eval"
                                    )
                        except Exception as e:
                            print(f"[优化提示词批量评估错误]: {e}")
                    
                    # 计算优化提示词的平均分数
                    opt_avg_score = self._calc_avg_score(opt_eval_results)
                    print(f"[调试] 第 {i+1} 轮优化版本 {opt_idx+1} 评分: {opt_avg_score:.2f}")
                    
                    # 记录优化提示词的结果，添加策略信息
                    opt_version = {
                        'iteration': i+1,
                        'stage': 'optimized',  # 标记为优化版本
                        'version': opt_idx + 1,  # 版本号
                        'prompt': opt_prompt,
                        'strategy': opt_strategy,
                        'eval_results': opt_eval_results,
                        'avg_score': opt_avg_score,
                        'is_best': False  # 初始化为非最佳版本
                    }
                    
                    all_opt_versions.append(opt_version)
                    history.append(opt_version)
                    
                    # 更新最佳优化提示词
                    if opt_avg_score > best_opt_score:
                        best_opt_score = opt_avg_score
                        best_opt_prompt = opt_prompt
                
                # 使用最佳优化提示词继续迭代
                current_prompt = best_opt_prompt
                
                # 更新全局最佳结果
                if best_opt_score > best_score:
                    best_score = best_opt_score
                    best_prompt = best_opt_prompt
                
                # 标记最佳版本
                for version in all_opt_versions:
                    if version['prompt'] == best_opt_prompt:
                        version['is_best'] = True
                        print(f"[调试] 第 {i+1} 轮选择版本 {version.get('version')} 作为最佳版本，分数: {version.get('avg_score'):.2f}")
            
            # 返回优化结果
            print(f"[调试] 迭代优化完成，共记录 {len(history)} 条历史记录")
            for i, item in enumerate(history):
                print(f"[调试] 历史记录 #{i+1}: 轮次={item.get('iteration')}, 阶段={item.get('stage')}, 版本={item.get('version', '-')}, 分数={item.get('avg_score'):.2f}")
                
            return {
                'best_prompt': best_prompt,
                'best_score': best_score,
                'history': history
            }
        except Exception as e:
            print(f"[严重错误] 迭代优化过程中出现异常: {e}")
            import traceback
            traceback.print_exc()
            return {
                'error': f"迭代优化失败: {str(e)}",
                'best_prompt': best_prompt,
                'best_score': best_score,
                'history': history  # 返回已有的历史记录
            }
        finally:
            # 确保事件循环在整个过程完成后关闭
            loop.close()

    def _calc_avg_score(self, eval_results: List[Dict]) -> float:
        """计算评估结果的平均分"""
        scores = []
        for r in eval_results:
            if 'overall_score' in r and isinstance(r['overall_score'], (int, float)):
                scores.append(r['overall_score'])
        return sum(scores)/len(scores) if scores else 0

    def _run_tests(self, test_cases):
        """执行测试用例并评估结果"""
        try:
            self._log("DEBUG", f"开始运行 {len(test_cases)} 个测试")
            
            from utils.parallel_executor import execute_models_sync
            
            # 准备批量请求
            requests = []
            for idx, test_case in enumerate(test_cases):
                user_input = test_case.get("user_input", "")
                expected_output = test_case.get("expected_output", "")
                criteria = test_case.get("evaluation_criteria", {})
                
                # 准备请求
                request = {
                    "model": self.model,
                    "provider": self.provider,
                    "prompt": f"{self.current_prompt}\n\n{user_input}",
                    "params": {
                        "temperature": self.temperature,
                        "max_tokens": 2000
                    },
                    "context": {
                        "expected_output": expected_output,
                        "criteria": criteria,
                        "prompt": self.current_prompt,
                        "user_input": user_input,
                        "idx": idx
                    }
                }
                requests.append(request)
            
            # 批量执行模型调用
            responses = execute_models_sync(requests)
            
            # 准备评估任务
            evaluation_tasks = []
            for response in responses:
                if response.get("error"):
                    self._log("WARNING", f"测试调用错误: {response.get('error')}")
                    continue
                
                context = response.get("context", {})
                
                evaluation_tasks.append({
                    "model_response": response.get("text", ""),
                    "expected_output": context.get("expected_output", ""),
                    "criteria": context.get("criteria", {}),
                    "prompt": context.get("prompt", ""),
                    "user_input": context.get("user_input", "")
                })
            
            if not evaluation_tasks:
                self._log("ERROR", "所有测试调用均失败")
                return []
            
            # 执行评估
            eval_results = self.evaluator.run_evaluation(evaluation_tasks)
            
            # 处理评估结果，添加用户输入等信息
            processed_results = []
            for i, result in enumerate(eval_results):
                if i < len(evaluation_tasks):
                    processed_result = dict(result)
                    processed_result["user_input"] = evaluation_tasks[i].get("user_input", "")
                    processed_result["model_response"] = evaluation_tasks[i].get("model_response", "")
                    processed_results.append(processed_result)
            
            self._log("INFO", f"完成 {len(processed_results)} 个测试的评估")
            return processed_results
        except Exception as e:
            import traceback
            self._log("ERROR", f"运行测试失败: {str(e)}")
            self._log("DEBUG", traceback.format_exc())
            return []

    def _generate_test_directions(self):
        """生成测试方向"""
        try:
            # 尝试使用LLM生成针对当前提示词的测试方向
            from utils.parallel_executor import execute_model_sync
            
            # 准备生成测试方向的提示词
            prompt = f"""
请分析以下提示词，并生成5个不同角度的测试方向，用于全面评估提示词的效果。
每个测试方向应该从不同角度测试提示词的能力，包括基本功能、边界条件、特殊情况等。

当前提示词:
```
{self.current_prompt}
```

请返回5个测试方向，每个测试方向应该是一句话描述，格式如下:
1. [测试方向描述]
2. [测试方向描述]
...
5. [测试方向描述]
"""
            
            # 调用模型
            result = execute_model_sync(
                model=self.iter_model,
                prompt=prompt,
                provider=self.iter_provider,
                params={
                    "temperature": 0.7,
                    "max_tokens": 1000
                }
            )
            
            if "error" in result:
                self._log("ERROR", f"生成测试方向时出错: {result['error']}")
                return self._get_default_test_directions()
                
            response_text = result.get("text", "")
            
            # 解析响应文本，提取测试方向
            import re
            directions = []
            
            # 尝试匹配格式为 "1. xxx", "2. xxx" 的行
            numbered_directions = re.findall(r'\d+\.\s*(.*?)(?=\n\d+\.|\Z)', response_text, re.DOTALL)
            if numbered_directions:
                directions.extend([d.strip() for d in numbered_directions if d.strip()])
            
            # 如果没有找到足够的方向，尝试按行分割
            if len(directions) < 3:
                lines = response_text.split('\n')
                for line in lines:
                    line = line.strip()
                    # 跳过空行和已经添加的方向
                    if not line or any(line in d for d in directions):
                        continue
                    # 删除可能的序号前缀
                    line = re.sub(r'^\d+[\.\)]\s*', '', line)
                    if line:
                        directions.append(line)
            
            # 如果仍然不够，添加默认方向
            if len(directions) < 3:
                missing = 3 - len(directions)
                directions.extend(self._get_default_test_directions()[:missing])
            
            # 为每个方向添加具体的测试用例生成指示
            expanded_directions = []
            for d in directions[:5]:  # 最多取5个
                expanded_directions.append(
                    f"测试方向：{d} - 请为此方向生成详细的测试用例，包含用户输入和期望输出，用于评估提示词的效果。"
                )
            
            self._log("DEBUG", f"生成了 {len(expanded_directions)} 个测试方向")
            return expanded_directions
            
        except Exception as e:
            self._log("ERROR", f"生成测试方向失败: {str(e)}")
            return self._get_default_test_directions()
    
    def _get_default_test_directions(self):
        """返回默认的测试方向"""
        return [
            "测试方向：基本功能测试 - 请生成测试用例检查提示词的基本功能是否正常工作，能否按预期响应简单问题。",
            "测试方向：格式遵循测试 - 请生成测试用例检查提示词是否能按照指定的格式要求输出内容。",
            "测试方向：复杂度测试 - 请生成测试用例包含复杂问题或多个问题，检查提示词处理复杂信息的能力。",
            "测试方向：边界条件测试 - 请生成一些边界情况的测试用例，检查提示词在极端情况下的表现。",
            "测试方向：指令跟随测试 - 请生成测试用例，检查提示词是否能严格按照用户指令执行。"
        ]
    
    def _calculate_average_score(self, results):
        """计算评估结果的平均分数"""
        if not results:
            return 0
            
        scores = []
        for result in results:
            if "overall_score" in result and isinstance(result["overall_score"], (int, float)):
                scores.append(result["overall_score"])
                
        return sum(scores) / len(scores) if scores else 0
    
    def _optimize_prompt(self, test_results):
        """基于测试结果优化提示词"""
        try:
            self._log("DEBUG", "开始基于测试结果优化提示词")
            
            # 使用优化器优化提示词
            optimization_result = self.optimizer.optimize_prompt_sync(
                original_prompt=self.current_prompt,
                test_results=test_results,
                optimization_strategy=self.optimization_strategy
            )
            
            if "error" in optimization_result:
                self._log("ERROR", f"优化提示词时出错: {optimization_result['error']}")
                return None
                
            # 获取优化结果
            optimized_prompts = optimization_result.get("optimized_prompts", [])
            if not optimized_prompts:
                self._log("WARNING", "未能生成优化提示词")
                return None
                
            # 选择第一个优化提示词
            best_opt = optimized_prompts[0]
            new_prompt = best_opt.get("prompt", "")
            
            if not new_prompt:
                self._log("WARNING", "优化提示词为空")
                return None
                
            self._log("INFO", f"提示词优化成功，新长度: {len(new_prompt)} 字符")
            self._log("DEBUG", f"优化策略: {best_opt.get('strategy', '未指定')}")
            self._log("DEBUG", f"解决的问题: {best_opt.get('problem_addressed', '未指定')}")
            
            return new_prompt
            
        except Exception as e:
            import traceback
            self._log("ERROR", f"优化提示词失败: {str(e)}")
            self._log("DEBUG", traceback.format_exc())
            return None
        
    def _generate_default_test_cases(self):
        """生成默认测试用例，当自动生成失败时使用"""
        import time, uuid
        
        # 基于当前提示词内容，创建几个通用测试用例
        test_cases = [
            {
                "id": f"default_{int(time.time())}_{uuid.uuid4().hex[:6]}",
                "description": "基本功能测试",
                "user_input": "为这个提示词提供一个基本的测试输入，检查基本功能是否正常工作。",
                "expected_output": "一个完整、准确的回应，满足提示词的基本要求。",
                "evaluation_criteria": {
                    "accuracy": "评估回答的准确性",
                    "completeness": "评估回答的完整性",
                    "relevance": "评估回答的相关性",
                    "clarity": "评估回答的清晰度"
                }
            },
            {
                "id": f"default_{int(time.time())+1}_{uuid.uuid4().hex[:6]}",
                "description": "边界条件测试",
                "user_input": "这是一个复杂的测试用例，包含多个需求和边界条件，用于测试提示词的鲁棒性。",
                "expected_output": "一个能全面处理复杂需求和边界条件的回答。",
                "evaluation_criteria": {
                    "accuracy": "评估回答的准确性",
                    "completeness": "评估回答的完整性",
                    "relevance": "评估回答的相关性",
                    "clarity": "评估回答的清晰度"
                }
            },
            {
                "id": f"default_{int(time.time())+2}_{uuid.uuid4().hex[:6]}",
                "description": "指令遵循测试",
                "user_input": "请严格按照以下格式回答：1. 问题分析 2. 可能的解决方案 3. 建议的最佳方案。问题是：如何提高提示词效果？",
                "expected_output": "一个严格按照指定格式的回答，包含问题分析、解决方案列表和最佳建议。",
                "evaluation_criteria": {
                    "accuracy": "评估回答的准确性",
                    "completeness": "评估回答的完整性",
                    "relevance": "评估回答的相关性",
                    "clarity": "评估回答的清晰度",
                    "instruction_following": "评估是否严格遵循了指令要求"
                }
            }
        ]
        
        self._log("INFO", f"已生成 {len(test_cases)} 个默认测试用例")
        return test_cases

# 在文件末尾添加AutomaticPromptOptimizer类定义

class AutomaticPromptOptimizer:
    """全自动提示词优化器，支持自动测试用例生成、评估和持续迭代"""
    
    def __init__(self, initial_prompt, model, provider, eval_model=None, eval_provider=None,
                iter_model=None, iter_provider=None, max_iterations=10, test_cases_per_iter=3, 
                optimization_strategy="balanced", temperature=0.7):
        """
        初始化全自动提示词优化器
        
        参数:
        - initial_prompt: 初始提示词
        - model: 对话模型名称
        - provider: 对话模型提供商
        - eval_model: 评估模型名称，如果为None则使用对话模型
        - eval_provider: 评估模型提供商，如果为None则使用对话模型提供商
        - iter_model: 迭代优化模型名称，如果为None则使用对话模型
        - iter_provider: 迭代优化模型提供商，如果为None则使用对话模型提供商
        - max_iterations: 最大迭代次数
        - test_cases_per_iter: 每轮迭代生成多少个测试用例
        - optimization_strategy: 优化策略
        - temperature: 温度参数
        """
        from utils.evaluator import PromptEvaluator
        
        # 初始化基本参数
        self.current_prompt = initial_prompt
        self.initial_prompt = initial_prompt
        self.model = model
        self.provider = provider
        self.eval_model = eval_model or model
        self.eval_provider = eval_provider or provider
        self.iter_model = iter_model or model
        self.iter_provider = iter_provider or provider
        self.max_iterations = max_iterations
        self.test_cases_per_iter = test_cases_per_iter
        self.optimization_strategy = optimization_strategy
        self.temperature = temperature
        
        # 初始化相关对象
        self.evaluator = PromptEvaluator()
        self.optimizer = PromptOptimizer()
        
        # 初始化状态变量
        self.current_iteration = 0
        self.best_prompt = initial_prompt
        self.best_score = 0
        self.iterations_history = []
        self.logs = []
        self._completed = False
        
        # 记录日志
        self._log("INFO", f"初始化自动优化器，初始提示词长度: {len(initial_prompt)} 字符")
        self._log("INFO", f"对话模型: {model} ({provider})")
        self._log("INFO", f"评估模型: {eval_model} ({eval_provider})")
        self._log("INFO", f"迭代模型: {iter_model} ({iter_provider})")
        self._log("INFO", f"优化策略: {optimization_strategy}, 最大迭代次数: {max_iterations}, 每轮测试用例数: {test_cases_per_iter}")
    
    def is_completed(self):
        """检查优化过程是否已完成"""
        return self._completed or self.current_iteration >= self.max_iterations
    
    def mark_completed(self):
        """标记优化已完成"""
        self._completed = True
    
    def get_latest_logs(self):
        """获取最新日志并清空日志队列"""
        logs = self.logs.copy()
        self.logs = []
        return logs
    
    def _log(self, level, message):
        """记录日志"""
        import time
        self.logs.append({
            "time": time.time(),
            "level": level,
            "message": message
        })
        print(f"[AutoOptimizer] [{level}] {message}")
    
    def run_single_iteration(self):
        """运行单次优化迭代，包括生成测试、评估、优化"""
        if self.is_completed():
            self._log("WARNING", "优化已完成，无法继续迭代")
            return None
        
        self._log("INFO", f"开始第 {self.current_iteration + 1}/{self.max_iterations} 轮优化")
        
        # 步骤1: 生成此轮的测试方向和测试用例
        test_cases = self._generate_test_cases()
        if not test_cases:
            self._log("ERROR", "未能生成测试用例，跳过本轮优化")
            self.current_iteration += 1
            return None
        
        self._log("INFO", f"成功生成 {len(test_cases)} 个测试用例")
        
        # 步骤2: 使用当前提示词对测试用例进行测试
        test_results = self._run_tests(test_cases)
        if not test_results:
            self._log("ERROR", "测试运行失败，跳过本轮优化")
            self.current_iteration += 1
            return None
        
        # 计算平均分数
        avg_score = self._calculate_average_score(test_results)
        self._log("INFO", f"本轮测试平均得分: {avg_score:.2f}")
        
        # 记录结果
        iteration_result = {
            "iteration": self.current_iteration + 1,
            "prompt": self.current_prompt,
            "test_cases": test_cases,
            "test_results": test_results,
            "score": avg_score,
            "strategy": self.optimization_strategy
        }
        
        # 更新最佳提示词
        if avg_score > self.best_score:
            self.best_prompt = self.current_prompt
            self.best_score = avg_score
            self._log("INFO", f"发现新的最佳提示词，得分: {avg_score:.2f}")
        
        # 如果不是最后一轮，进行优化
        if self.current_iteration + 1 < self.max_iterations:
            # 步骤3: 基于测试结果优化提示词
            new_prompt = self._optimize_prompt(test_results)
            if new_prompt:
                self.current_prompt = new_prompt
                self._log("INFO", f"提示词已优化，新长度: {len(new_prompt)} 字符")
            else:
                self._log("WARNING", "优化失败，继续使用当前提示词")
        else:
            self._log("INFO", "已达到最大迭代次数，完成优化")
            self._completed = True
        
        # 增加迭代计数
        self.current_iteration += 1
        
        # 添加到历史记录
        self.iterations_history.append(iteration_result)
        
        return iteration_result
    
    def _generate_test_cases(self):
        """生成本轮测试用例"""
        try:
            self._log("DEBUG", f"开始生成测试用例，目标数量: {self.test_cases_per_iter}")
            
            # 生成测试用例的几个方向
            directions = self._generate_test_directions()
            if not directions:
                self._log("ERROR", "未能生成测试方向")
                return []
            
            self._log("DEBUG", f"生成了 {len(directions)} 个测试方向")
            
            # 创建一个简单的示例测试用例作为基础
            example_case = {
                "id": "example_case",
                "description": "示例测试用例",
                "user_input": "这是一个测试用例的用户输入示例",
                "expected_output": "期望的输出应该包含完整、准确的回答",
                "evaluation_criteria": {
                    "accuracy": "评估回答的准确性",
                    "completeness": "评估回答的完整性",
                    "relevance": "评估回答的相关性",
                    "clarity": "评估回答的清晰度"
                }
            }
            
            # 计算每个方向应生成的测试用例数量
            cases_per_direction = max(1, self.test_cases_per_iter // len(directions))
            
            try:
                # 使用评估器生成测试用例，直接调用同步方法
                # 注意：由于我们不在这里创建和关闭事件循环，所以不会遇到"Event loop is closed"的错误
                batch_result = self.evaluator.generate_test_cases_batch(
                    model=self.iter_model,
                    test_purposes=directions,
                    example_case=example_case,
                    target_count_per_purpose=cases_per_direction
                )
                
                if "error" in batch_result:
                    self._log("ERROR", f"批量生成测试用例失败: {batch_result['error']}")
                    # 如果批量生成失败，返回一些默认测试用例
                    return self._generate_default_test_cases()
                
                if "errors" in batch_result and batch_result["errors"]:
                    for error in batch_result["errors"]:
                        self._log("WARNING", f"生成测试用例警告: {error}")
                
                test_cases = batch_result.get("test_cases", [])
                
                # 确保测试用例有所有必要的字段
                for tc in test_cases:
                    if "id" not in tc:
                        import time, uuid
                        tc["id"] = f"auto_{int(time.time())}_{uuid.uuid4().hex[:6]}"
                    if "evaluation_criteria" not in tc or not tc["evaluation_criteria"]:
                        tc["evaluation_criteria"] = {
                            "accuracy": "评估回答的准确性",
                            "completeness": "评估回答的完整性",
                            "relevance": "评估回答的相关性",
                            "clarity": "评估回答的清晰度"
                        }
                
                # 如果没有生成足够的测试用例，生成一些默认测试用例补充
                if not test_cases or len(test_cases) < 1:
                    self._log("WARNING", "生成的测试用例数量不足，添加默认测试用例")
                    test_cases.extend(self._generate_default_test_cases())
                
                return test_cases
                
            except Exception as e:
                import traceback
                self._log("ERROR", f"调用测试用例生成器时出错: {str(e)}")
                self._log("DEBUG", traceback.format_exc())
                # 如果生成失败，返回默认测试用例
                return self._generate_default_test_cases()
            
        except Exception as e:
            import traceback
            self._log("ERROR", f"生成测试用例失败: {str(e)}")
            self._log("DEBUG", traceback.format_exc())
            return self._generate_default_test_cases()
    
    def _run_tests(self, test_cases):
        """执行测试用例并评估结果"""
        try:
            self._log("DEBUG", f"开始运行 {len(test_cases)} 个测试")
            
            from utils.parallel_executor import execute_models_sync
            
            # 准备批量请求
            requests = []
            for idx, test_case in enumerate(test_cases):
                user_input = test_case.get("user_input", "")
                expected_output = test_case.get("expected_output", "")
                criteria = test_case.get("evaluation_criteria", {})
                
                # 准备请求
                request = {
                    "model": self.model,
                    "provider": self.provider,
                    "prompt": f"{self.current_prompt}\n\n{user_input}",
                    "params": {
                        "temperature": self.temperature,
                        "max_tokens": 2000
                    },
                    "context": {
                        "expected_output": expected_output,
                        "criteria": criteria,
                        "prompt": self.current_prompt,
                        "user_input": user_input,
                        "idx": idx
                    }
                }
                requests.append(request)
            
            # 批量执行模型调用
            responses = execute_models_sync(requests)
            
            # 准备评估任务
            evaluation_tasks = []
            for response in responses:
                if response.get("error"):
                    self._log("WARNING", f"测试调用错误: {response.get('error')}")
                    continue
                
                context = response.get("context", {})
                
                evaluation_tasks.append({
                    "model_response": response.get("text", ""),
                    "expected_output": context.get("expected_output", ""),
                    "criteria": context.get("criteria", {}),
                    "prompt": context.get("prompt", ""),
                    "user_input": context.get("user_input", "")
                })
            
            if not evaluation_tasks:
                self._log("ERROR", "所有测试调用均失败")
                return []
            
            # 执行评估
            eval_results = self.evaluator.run_evaluation(evaluation_tasks)
            
            # 处理评估结果，添加用户输入等信息
            processed_results = []
            for i, result in enumerate(eval_results):
                if i < len(evaluation_tasks):
                    processed_result = dict(result)
                    processed_result["user_input"] = evaluation_tasks[i].get("user_input", "")
                    processed_result["model_response"] = evaluation_tasks[i].get("model_response", "")
                    processed_results.append(processed_result)
            
            self._log("INFO", f"完成 {len(processed_results)} 个测试的评估")
            return processed_results
        except Exception as e:
            import traceback
            self._log("ERROR", f"运行测试失败: {str(e)}")
            self._log("DEBUG", traceback.format_exc())
            return []
    
    def _generate_test_directions(self):
        """生成测试方向"""
        try:
            # 尝试使用LLM生成针对当前提示词的测试方向
            from utils.parallel_executor import execute_model_sync
            
            # 准备生成测试方向的提示词
            prompt = f"""
请分析以下提示词，并生成5个不同角度的测试方向，用于全面评估提示词的效果。
每个测试方向应该从不同角度测试提示词的能力，包括基本功能、边界条件、特殊情况等。

当前提示词:
```
{self.current_prompt}
```

请返回5个测试方向，每个测试方向应该是一句话描述，格式如下:
1. [测试方向描述]
2. [测试方向描述]
...
5. [测试方向描述]
"""
            
            # 调用模型
            result = execute_model_sync(
                model=self.iter_model,
                prompt=prompt,
                provider=self.iter_provider,
                params={
                    "temperature": 0.7,
                    "max_tokens": 1000
                }
            )
            
            if "error" in result:
                self._log("ERROR", f"生成测试方向时出错: {result['error']}")
                return self._get_default_test_directions()
                
            response_text = result.get("text", "")
            
            # 解析响应文本，提取测试方向
            import re
            directions = []
            
            # 尝试匹配格式为 "1. xxx", "2. xxx" 的行
            numbered_directions = re.findall(r'\d+\.\s*(.*?)(?=\n\d+\.|\Z)', response_text, re.DOTALL)
            if numbered_directions:
                directions.extend([d.strip() for d in numbered_directions if d.strip()])
            
            # 如果没有找到足够的方向，尝试按行分割
            if len(directions) < 3:
                lines = response_text.split('\n')
                for line in lines:
                    line = line.strip()
                    # 跳过空行和已经添加的方向
                    if not line or any(line in d for d in directions):
                        continue
                    # 删除可能的序号前缀
                    line = re.sub(r'^\d+[\.\)]\s*', '', line)
                    if line:
                        directions.append(line)
            
            # 如果仍然不够，添加默认方向
            if len(directions) < 3:
                missing = 3 - len(directions)
                directions.extend(self._get_default_test_directions()[:missing])
            
            # 为每个方向添加具体的测试用例生成指示
            expanded_directions = []
            for d in directions[:5]:  # 最多取5个
                expanded_directions.append(
                    f"测试方向：{d} - 请为此方向生成详细的测试用例，包含用户输入和期望输出，用于评估提示词的效果。"
                )
            
            self._log("DEBUG", f"生成了 {len(expanded_directions)} 个测试方向")
            return expanded_directions
            
        except Exception as e:
            self._log("ERROR", f"生成测试方向失败: {str(e)}")
            return self._get_default_test_directions()
    
    def _get_default_test_directions(self):
        """返回默认的测试方向"""
        return [
            "测试方向：基本功能测试 - 请生成测试用例检查提示词的基本功能是否正常工作，能否按预期响应简单问题。",
            "测试方向：格式遵循测试 - 请生成测试用例检查提示词是否能按照指定的格式要求输出内容。",
            "测试方向：复杂度测试 - 请生成测试用例包含复杂问题或多个问题，检查提示词处理复杂信息的能力。",
            "测试方向：边界条件测试 - 请生成一些边界情况的测试用例，检查提示词在极端情况下的表现。",
            "测试方向：指令跟随测试 - 请生成测试用例，检查提示词是否能严格按照用户指令执行。"
        ]
    
    def _calculate_average_score(self, results):
        """计算评估结果的平均分数"""
        if not results:
            return 0
            
        scores = []
        for result in results:
            if "overall_score" in result and isinstance(result["overall_score"], (int, float)):
                scores.append(result["overall_score"])
                
        return sum(scores) / len(scores) if scores else 0
    
    def _optimize_prompt(self, test_results):
        """基于测试结果优化提示词"""
        try:
            self._log("DEBUG", "开始基于测试结果优化提示词")
            
            # 使用优化器优化提示词
            optimization_result = self.optimizer.optimize_prompt_sync(
                original_prompt=self.current_prompt,
                test_results=test_results,
                optimization_strategy=self.optimization_strategy
            )
            
            if "error" in optimization_result:
                self._log("ERROR", f"优化提示词时出错: {optimization_result['error']}")
                return None
                
            # 获取优化结果
            optimized_prompts = optimization_result.get("optimized_prompts", [])
            if not optimized_prompts:
                self._log("WARNING", "未能生成优化提示词")
                return None
                
            # 选择第一个优化提示词
            best_opt = optimized_prompts[0]
            new_prompt = best_opt.get("prompt", "")
            
            if not new_prompt:
                self._log("WARNING", "优化提示词为空")
                return None
                
            self._log("INFO", f"提示词优化成功，新长度: {len(new_prompt)} 字符")
            self._log("DEBUG", f"优化策略: {best_opt.get('strategy', '未指定')}")
            self._log("DEBUG", f"解决的问题: {best_opt.get('problem_addressed', '未指定')}")
            
            return new_prompt
            
        except Exception as e:
            import traceback
            self._log("ERROR", f"优化提示词失败: {str(e)}")
            self._log("DEBUG", traceback.format_exc())
            return None
        
    def _generate_default_test_cases(self):
        """生成默认测试用例，当自动生成失败时使用"""
        import time, uuid
        
        # 基于当前提示词内容，创建几个通用测试用例
        test_cases = [
            {
                "id": f"default_{int(time.time())}_{uuid.uuid4().hex[:6]}",
                "description": "基本功能测试",
                "user_input": "为这个提示词提供一个基本的测试输入，检查基本功能是否正常工作。",
                "expected_output": "一个完整、准确的回应，满足提示词的基本要求。",
                "evaluation_criteria": {
                    "accuracy": "评估回答的准确性",
                    "completeness": "评估回答的完整性",
                    "relevance": "评估回答的相关性",
                    "clarity": "评估回答的清晰度"
                }
            },
            {
                "id": f"default_{int(time.time())+1}_{uuid.uuid4().hex[:6]}",
                "description": "边界条件测试",
                "user_input": "这是一个复杂的测试用例，包含多个需求和边界条件，用于测试提示词的鲁棒性。",
                "expected_output": "一个能全面处理复杂需求和边界条件的回答。",
                "evaluation_criteria": {
                    "accuracy": "评估回答的准确性",
                    "completeness": "评估回答的完整性",
                    "relevance": "评估回答的相关性",
                    "clarity": "评估回答的清晰度"
                }
            },
            {
                "id": f"default_{int(time.time())+2}_{uuid.uuid4().hex[:6]}",
                "description": "指令遵循测试",
                "user_input": "请严格按照以下格式回答：1. 问题分析 2. 可能的解决方案 3. 建议的最佳方案。问题是：如何提高提示词效果？",
                "expected_output": "一个严格按照指定格式的回答，包含问题分析、解决方案列表和最佳建议。",
                "evaluation_criteria": {
                    "accuracy": "评估回答的准确性",
                    "completeness": "评估回答的完整性",
                    "relevance": "评估回答的相关性",
                    "clarity": "评估回答的清晰度",
                    "instruction_following": "评估是否严格遵循了指令要求"
                }
            }
        ]
        
        self._log("INFO", f"已生成 {len(test_cases)} 个默认测试用例")
        return test_cases

# 确保导出AutomaticPromptOptimizer类
__all__ = ['PromptOptimizer', 'AutomaticPromptOptimizer']