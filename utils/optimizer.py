import json
import asyncio
import concurrent.futures
import threading
from typing import Dict, List, Optional, Any, Tuple

from models.api_clients import get_client, get_provider_from_model
from config import load_config, get_system_template
# 导入新的并行执行器
from utils.parallel_executor import execute_model, execute_models, execute_model_sync, execute_models_sync
# 导入新的常量和工具函数
from utils.constants import (
    DEFAULT_EVALUATION_CRITERIA,
    DEFAULT_GENERATION_PARAMS,
    DEFAULT_EVALUATION_PARAMS
)
from utils.helpers import (
    parse_json_response,
    ensure_test_case_fields,
    calculate_prompt_efficiency,
    ProgressTracker
)

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
        
        try:
            # 使用新的并行执行器，采用默认参数
            params = dict(DEFAULT_GENERATION_PARAMS)
            params["temperature"] = 0.8  # 增加温度以确保更多样化的优化结果
            params["max_tokens"] = 4000 # 需要更多tokens进行优化
            
            result = await execute_model(
                self.optimizer_model,
                prompt=optimization_prompt,
                provider=self.provider,
                params=params
            )
            
            opt_text = result.get("text", "")
            print(f"[调试-优化器] 收到优化响应，长度: {len(opt_text)} 字符")
            
            # 使用通用JSON解析函数解析结果
            parsed_result, error = parse_json_response(opt_text)
            
            if error:
                print(f"[错误-优化器] JSON解析失败: {error}")
                # 即使解析失败也返回至少一个优化版本
                return {
                    "error": f"优化结果格式错误: {error}",
                    "raw_response": opt_text,
                    "optimized_prompts": [{
                        "strategy": "默认优化",
                        "problem_addressed": "无法解析API返回的优化结果",
                        "expected_improvements": "提供至少一个可用的优化版本",
                        "prompt": original_prompt + "\n\n请确保回答详细、准确、有条理，并解决用户的全部需求。"
                    }]
                }
            
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
        
        # 使用统一的事件循环管理方法
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
        
        # 使用统一的事件循环管理方法
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
            
        # 使用默认参数
        params = dict(DEFAULT_GENERATION_PARAMS)
        params["max_tokens"] = 2000
            
        try:
            # 使用新的并行执行器
            result = await execute_model(
                self.optimizer_model,
                prompt=optimization_prompt,
                provider=self.provider,
                params=params
            )
            
            opt_text = result.get("text", "")
            
            # 使用通用JSON解析函数
            parsed_result, error = parse_json_response(opt_text)
            
            if error:
                return {"error": f"优化结果格式错误: {error}", "raw_response": opt_text}
            
            return parsed_result
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
        
        try:
            # 使用新的并行执行器和默认参数
            params = dict(DEFAULT_EVALUATION_PARAMS)
            params["max_tokens"] = 1000
            
            result = await execute_model(
                self.optimizer_model,
                prompt=analysis_prompt,
                provider=self.provider,
                params=params
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
        strategy_guidance = { 
            "accuracy": "提高响应的准确性，确保输出与预期结果精确匹配", 
            "completeness": "确保响应全面覆盖所有必要信息，不遗漏关键内容", 
            "conciseness": "使提示词更简洁有效，移除冗余内容，保持核心指令清晰", 
            "balanced": "平衡改进所有维度，注重整体性能提升" 
        }
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
        
        # 使用统一的进度跟踪器进行复杂进度更新
        if progress_callback:
            progress_tracker = ProgressTracker(
                total_steps=max_iterations * total_eval_per_iter,
                callback=lambda current, total, desc: progress_callback(
                    current // total_eval_per_iter + 1,  # iteration
                    max_iterations,
                    current % total_eval_per_iter + 1,  # inner_idx
                    total_eval_per_iter,
                    current,  # global_idx
                    total,    # global_total
                    desc     # description/stage
                ),
                description="初始化"
            )
        else:
            progress_tracker = None
        
        # 创建一个事件循环，用于整个优化过程
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        try:
            for i in range(max_iterations):
                print(f"[调试] 开始第 {i+1}/{max_iterations} 轮迭代")
                
                # 创建每轮迭代的嵌套进度追踪器
                if progress_tracker:
                    iter_tracker = ProgressTracker(
                        total_steps=total_eval_per_iter,
                        parent=progress_tracker,
                        description=f"gen_{i+1}"
                    )
                else:
                    iter_tracker = None
                
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
                        "params": DEFAULT_GENERATION_PARAMS,
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
                for idx, response in enumerate(responses):
                    context = response.get("context", {})
                    
                    if not response.get("error") and response.get("text"):
                        evaluation_tasks.append({
                            "model_response": response.get("text", ""),
                            "expected_output": context.get("expected_output", ""),
                            "criteria": context.get("criteria", {}),
                            "prompt": context.get("prompt", ""),
                            "idx": context.get("idx", -1)
                        })
                    
                    # 更新生成阶段进度
                    if iter_tracker:
                        iter_tracker.update(1, f"gen_{i+1}")
                
                # 创建评估阶段的进度追踪器
                if progress_tracker:
                    eval_tracker = ProgressTracker(
                        total_steps=len(evaluation_tasks),
                        parent=progress_tracker,
                        description=f"eval_{i+1}"
                    )
                else:
                    eval_tracker = None
                
                # 批量评估所有响应
                eval_results = []
                if evaluation_tasks:
                    try:
                        print(f"[调试] 第 {i+1} 轮评估 {len(evaluation_tasks)} 个响应")
                        eval_results = loop.run_until_complete(evaluator.run_evaluation_async(evaluation_tasks))
                        
                        # 更新评估阶段进度
                        if eval_tracker:
                            eval_tracker.complete(f"eval_{i+1}")
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
                    
                    # 创建优化版本评估的进度追踪器
                    if progress_tracker:
                        opt_gen_tracker = ProgressTracker(
                            total_steps=len(test_set),
                            parent=progress_tracker,
                            description=f"opt_gen_{i+1}_{opt_idx+1}"
                        )
                        opt_eval_tracker = ProgressTracker(
                            total_steps=len(test_set),
                            parent=progress_tracker,
                            description=f"opt_eval_{i+1}_{opt_idx+1}"
                        )
                    else:
                        opt_gen_tracker = None
                        opt_eval_tracker = None
                    
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
                            "params": DEFAULT_GENERATION_PARAMS,
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
                    for idx, opt_response in enumerate(opt_responses):
                        context = opt_response.get("context", {})
                        
                        if not opt_response.get("error") and opt_response.get("text"):
                            opt_evaluation_tasks.append({
                                "model_response": opt_response.get("text", ""),
                                "expected_output": context.get("expected_output", ""),
                                "criteria": context.get("criteria", {}),
                                "prompt": context.get("prompt", ""),
                                "idx": context.get("idx", -1)
                            })
                        
                        # 更新优化生成阶段进度
                        if opt_gen_tracker:
                            opt_gen_tracker.update(1, f"opt_gen_{i+1}_{opt_idx+1}")
                    
                    # 评估优化提示词的响应 - 同样使用批处理方式
                    opt_eval_results = []
                    if opt_evaluation_tasks:
                        try:
                            # 使用单一批处理方式进行评估
                            opt_eval_results = loop.run_until_complete(evaluator.run_evaluation_async(opt_evaluation_tasks))
                            
                            # 更新优化评估阶段进度
                            if opt_eval_tracker:
                                opt_eval_tracker.complete(f"opt_eval_{i+1}_{opt_idx+1}")
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

    def _generate_default_test_cases(self):
        """生成默认测试用例，当自动生成失败时使用"""
        # 创建几个通用测试用例
        test_cases = [
            {
                "description": "基本功能测试",
                "user_input": "为这个提示词提供一个基本的测试输入，检查基本功能是否正常工作。",
                "expected_output": "一个完整、准确的回应，满足提示词的基本要求。"
            },
            {
                "description": "边界条件测试",
                "user_input": "这是一个复杂的测试用例，包含多个需求和边界条件，用于测试提示词的鲁棒性。",
                "expected_output": "一个能全面处理复杂需求和边界条件的回答。"
            },
            {
                "description": "指令遵循测试",
                "user_input": "请严格按照以下格式回答：1. 问题分析 2. 可能的解决方案 3. 建议的最佳方案。问题是：如何提高提示词效果？",
                "expected_output": "一个严格按照指定格式的回答，包含问题分析、解决方案列表和最佳建议。"
            }
        ]
        
        # 使用辅助函数确保所有测试用例字段完整
        test_cases = [ensure_test_case_fields(case) for case in test_cases]
        
        print(f"[INFO] 已生成 {len(test_cases)} 个默认测试用例")
        return test_cases
        
    def _get_default_test_directions(self):
        """返回默认的测试方向"""
        return [
            "测试方向：基本功能测试 - 请生成测试用例检查提示词的基本功能是否正常工作，能否按预期响应简单问题。",
            "测试方向：格式遵循测试 - 请生成测试用例检查提示词是否能按照指定的格式要求输出内容。",
            "测试方向：复杂度测试 - 请生成测试用例包含复杂问题或多个问题，检查提示词处理复杂信息的能力。",
            "测试方向：边界条件测试 - 请生成一些边界情况的测试用例，检查提示词在极端情况下的表现。",
            "测试方向：指令跟随测试 - 请生成测试用例，检查提示词是否能严格按照用户指令执行。"
        ]


__all__ = ['PromptOptimizer']