import json
import asyncio
import concurrent.futures
import threading
from typing import Dict, List, Optional, Any, Tuple

from models.api_clients import get_client, get_provider_from_model
from config import load_config, get_system_template
from utils.common import render_prompt_template
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
    def __init__(self, optimization_retries=3):  # Added optimization_retries
        config = load_config()
        self.optimizer_model = config.get("evaluator_model", "gpt-4o")  # 使用与评估相同的模型
        self.provider = get_provider_from_model(self.optimizer_model)
        self.client = get_client(self.provider)
        self.optimization_retries = optimization_retries  # Store optimization_retries
        
        # 获取优化器和分析器模板
        self.optimizer_template = get_system_template("optimizer")
        self.problem_analyzer_template = get_system_template("problem_analyzer")  # 新增
    
    async def optimize_prompt(self, original_prompt: str, test_results: List[Dict], optimization_strategy: str = "balanced") -> Dict:
        # --- 修复类型问题 ---
        if isinstance(original_prompt, dict):
            # 你可以根据实际结构选择合适的字段
            original_prompt_str = original_prompt.get("template") or original_prompt.get("content") or json.dumps(original_prompt, ensure_ascii=False)
        else:
            original_prompt_str = original_prompt

        print(f"[调试-优化器] 收到 {len(test_results)} 条评估结果进行优化。原始提示词长度: {len(original_prompt_str)}")

        problem_analysis = await self.analyze_evaluation_problems_with_llm(test_results)
        if "error" in problem_analysis:
            print(f"[错误-优化器] 分析问题出错: {problem_analysis['error']}")
            return problem_analysis

        optimization_guidance = self.build_optimization_guidance(problem_analysis["analysis"], optimization_strategy)
        results_summary = self.format_test_results_summary(test_results)
        template = self.optimizer_template.get("template", "")

        # Truncate or summarize components if the prompt length exceeds a safe threshold
        MAX_PROMPT_LENGTH = 7500  # Set a safe limit below max_tokens

        def truncate_text(text, max_length):
            if len(text) > max_length:
                return text[:max_length] + "... (truncated)"
            return text

        # Calculate available space for each component
        available_length = MAX_PROMPT_LENGTH - len(template.replace("{{original_prompt}}", "").replace("{{results_summary}}", "").replace("{{problem_analysis}}", "").replace("{{optimization_guidance}}", ""))
        component_share = available_length // 3  # Divide space among results_summary, problem_analysis, and optimization_guidance

        results_summary = truncate_text(results_summary, component_share)
        problem_analysis = truncate_text(problem_analysis["analysis"], component_share)
        optimization_guidance = truncate_text(optimization_guidance, component_share)

        base_optimization_prompt = template\
            .replace("{{original_prompt}}", original_prompt_str)\
            .replace("{{results_summary}}", results_summary)\
            .replace("{{problem_analysis}}", problem_analysis)\
            .replace("{{optimization_guidance}}", optimization_guidance)

        print(f"[调试-优化器] 已准备基础优化提示词，长度: {len(base_optimization_prompt)} 字符")

        all_optimized_prompts = []
        max_single_prompt_retries = self.optimization_retries 
        
        for i in range(3): # 调用3次以获取3个独立的优化提示词
            print(f"[调试-优化器] 开始第 {i+1}/3 次提示词生成尝试...")
            retry_count = 0
            current_prompt_generated = False
            while retry_count < max_single_prompt_retries and not current_prompt_generated:
                print(f"[调试-优化器] 第 {i+1}/3 次生成 - 尝试 {retry_count + 1}/{max_single_prompt_retries}...")
                try:
                    call_params = dict(DEFAULT_GENERATION_PARAMS)
                    call_params["temperature"] = 0.9
                    call_params["max_tokens"] = 8000 # 修改 max_tokens

                    print(f"[调试-优化器] 调用LLM进行第 {i+1} 次优化。参数: {call_params}")
                    result = await execute_model(
                        self.optimizer_model,
                        prompt=base_optimization_prompt,
                        provider=self.provider,
                        params=call_params 
                    )
                    
                    opt_text = result.get("text", "")
                    raw_response_text = opt_text
                    request_id = result.get("id", "N/A") # 假设execute_model返回ID
                    print(f"[调试-优化器] LLM调用 {request_id} (尝试 {retry_count + 1}) 返回响应，长度: {len(opt_text)} 字符. 原始响应: '{raw_response_text[:500]}...' ")

                    current_parsed_result, error = parse_json_response(opt_text)
                    
                    if error:
                        error_message = f"JSON解析失败: {error}. 原始文本: '{raw_response_text[:500]}...'"
                        print(f"[错误-优化器] {error_message}")
                        retry_count += 1
                        if "空响应内容" in error or "未能生成优化提示词" in error or "JSON解析失败" in error:
                            print(f"[警告-优化器] 第 {i+1}/3 次生成 - 尝试 {retry_count}/{max_single_prompt_retries} 失败: {error_message}，准备重试...")
                            if retry_count < max_single_prompt_retries:
                                await asyncio.sleep(1)
                            continue
                        else: # 不可重试的JSON解析错误
                            break 
                    
                    if not current_parsed_result or "optimized_prompt" not in current_parsed_result or not current_parsed_result["optimized_prompt"]:
                        error_message = f"优化结果未包含有效的optimized_prompt. 解析结果: {current_parsed_result}"
                        print(f"[错误-优化器] {error_message}")
                        retry_count += 1
                        print(f"[警告-优化器] 第 {i+1}/3 次生成 - 尝试 {retry_count}/{max_single_prompt_retries} 失败: {error_message}，准备重试...")
                        if retry_count < max_single_prompt_retries:
                            await asyncio.sleep(1)
                        continue
                    
                    if current_parsed_result["optimized_prompt"]:
                        all_optimized_prompts.append(current_parsed_result["optimized_prompt"])
                        current_prompt_generated = True
                        print(f"[调试-优化器] 第 {i+1}/3 次提示词生成成功。")
                        break # 当前单个提示词生成成功，跳出重试循环
                    else:
                        error_message = f"优化结果未包含有效的optimized_prompt. 解析结果: {current_parsed_result}"
                        print(f"[错误-优化器] {error_message}")
                        retry_count += 1
                        print(f"[警告-优化器] 第 {i+1}/3 次生成 - 尝试 {retry_count}/{max_single_prompt_retries} 失败: {error_message}，准备重试...")
                        if retry_count < max_single_prompt_retries:
                             await asyncio.sleep(1)
                        continue

                except Exception as e:
                    error_message = f"第 {i+1}/3 次优化API调用失败: {str(e)}"
                    print(f"[错误-优化器] {error_message}")
                    import traceback
                    print(traceback.format_exc())
                    retry_count += 1
                    print(f"[警告-优化器] 第 {i+1}/3 次生成 - 尝试 {retry_count}/{max_single_prompt_retries} 失败: {error_message}，准备重试...")
                    if retry_count < max_single_prompt_retries:
                        await asyncio.sleep(1)
                    continue
            
            if not current_prompt_generated:
                 print(f"[警告-优化器] 第 {i+1}/3 次提示词生成在 {max_single_prompt_retries} 次尝试后失败。")

        if not all_optimized_prompts:
            print(f"[错误-优化器] 在 {3 * max_single_prompt_retries} 次总尝试后仍未能成功优化任何提示词。返回默认提示。")
            return {
                "error": f"在 {3 * max_single_prompt_retries} 次总尝试后优化失败",
                "raw_response": raw_response_text, # 最后一次的原始响应
                "optimized_prompts": [{
                    "strategy": "默认优化（所有尝试失败）",
                    "problem_addressed": "无法通过LLM生成优化版本",
                    "expected_improvements": "提供至少一个可用的提示词",
                    "prompt": original_prompt_str + "\n\n请确保回答详细、准确、有条理，并解决用户的全部需求。"
                }]
            }
            
        print(f"[调试-优化器] 总共生成 {len(all_optimized_prompts)} 个优化后的提示词。")
        return {"optimized_prompts": all_optimized_prompts}

    def optimize_prompt_sync(self, original_prompt: str, test_results: List[Dict], optimization_strategy: str = "balanced") -> Dict:
        """同步版本的优化函数（包装异步函数）"""
        # --- 修复类型问题 ---
        if isinstance(original_prompt, dict):
            original_prompt_str = original_prompt.get("template") or original_prompt.get("content") or json.dumps(original_prompt, ensure_ascii=False)
        else:
            original_prompt_str = original_prompt

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
                    "prompt": original_prompt_str + "\n\n请确保你的回答详尽、准确、清晰，并完全满足用户的需求。"
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
                    "prompt": original_prompt_str + "\n\n请确保你的回答全面、准确、简洁，并完全解决用户的需求。"
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
        params["max_tokens"] = 8000
            
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
            print("[错误-优化器] 未能加载问题分析器模板，使用默认分析")
            return {"analysis": "提示词可能需要在指令清晰度和结果格式方面进行优化，以提高响应的准确性和相关性。"}
            
        analysis_prompt = template.replace("{{evaluation_results_summary}}", results_summary)
        
        try:
            # 使用新的并行执行器和默认参数
            params = dict(DEFAULT_EVALUATION_PARAMS)
            params["max_tokens"] = 2000
            
            result = await execute_model(
                self.optimizer_model,
                prompt=analysis_prompt,
                provider=self.provider,
                params=params
            )
            
            analysis_text = result.get("text", "").strip()
            if not analysis_text:
                print("[警告-优化器] LLM未能生成问题分析，使用默认分析")
                # 提供默认分析而不是返回错误
                return {
                    "analysis": "基于评估结果的默认分析：提示词可能需要改进清晰度、具体指令和结构化输出的要求，以提高响应质量。建议优化指令的准确性，明确期望的输出格式，并增强提示词的上下文信息。"
                }
            print({"analysis": analysis_text})
            return {"analysis": analysis_text}
        except Exception as e:
            print(f"[错误-优化器] 使用LLM分析问题时出错: {str(e)}，使用默认分析")
            # 提供默认分析而不是返回错误
            return {
                "analysis": "由于技术原因无法进行详细分析。一般建议：提高提示词的清晰度，添加具体指令和格式要求，明确任务目标和约束条件，可能会提升响应质量。"
            }

    def format_test_results_summary_for_analysis(self, test_results: List[Dict]) -> str:
        """将测试结果格式化为更适合LLM分析的摘要"""
        # print("--- test_results ---")
        # print(test_results)
        summary = ""
        for i, result in enumerate(test_results):
            summary += f"--- Test Case {i+1} ---\n"
            if "case_description" in result:
                summary += f"Case Description: {result['case_description']}\n"
            if "user_input" in result:
                summary += f"USER INPUT:\n{result['user_input']}\n\n"
            if "variables" in result:
                summary += f"Variables: {json.dumps(result['variables'], ensure_ascii=False)}\n"
            if "expected_output" in result:
                summary += f"Expected Output:\n{result['expected_output']}\n\n"
            if "responses" in result:
                for j, resp in enumerate(result.get("responses", [])):
                    # 明确标注模型实际输出
                    if "output" in resp:
                        summary += f"Real Output:\n{resp['output']}\n\n"
                    summary += f"Evaluation:\n"
                    if "evaluation" in resp and resp["evaluation"]:
                        eval_data = resp["evaluation"]
                        if "scores" in eval_data:
                            summary += f"    Scores: {json.dumps(eval_data['scores'], ensure_ascii=False)}\n"
                        if "overall_score" in eval_data:
                            summary += f"    Overall Score: {eval_data['overall_score']}\n"
                        if "analysis" in eval_data:
                            summary += f"    Analysis:\n {eval_data['analysis']}\n"
                    elif "error" in resp:
                        summary += f"    Error: {resp['error']}\n"
            summary += "\n"
        print("llm summary")
        print(summary)
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
        import logging
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
            # 日志：每个用例的评估数据
            if not eval_data:
                logging.warning(f"[优化器] 用例{i+1}未找到evaluation字段: {result}")
            else:
                if "overall_score" not in eval_data:
                    logging.warning(f"[优化器] 用例{i+1}的evaluation缺少overall_score: {eval_data}")
                if "analysis" not in eval_data:
                    logging.warning(f"[优化器] 用例{i+1}的evaluation缺少analysis: {eval_data}")
            if eval_data:
                if "overall_score" in eval_data:
                    scores.append(eval_data["overall_score"])
                if "analysis" in eval_data:
                    analyses_texts.append(f"Case {i+1}: {eval_data['analysis']}")
        if not scores:
            summary += "平均总分: 0.0\n"
            summary += "[警告] 未找到任何有效的评估分数，请检查测试用例responses和evaluation结构。\n"
        else:
            avg_score = sum(scores) / len(scores)
            summary += f"平均总分: {avg_score:.1f}\n"
        if not analyses_texts:
            summary += "部分评估分析摘要: [警告] 未找到任何分析内容，请检查evaluation.analysis字段。"
        else:
            summary += "部分评估分析摘要:\n" + "\n".join(analyses_texts[:3])
        logging.info(f"[优化器] 评估摘要: {summary}")
        print("summary")
        print(summary)
        return summary

    def _evaluate_prompt_on_testcases(self, prompt_obj, test_cases, test_set_dict, evaluator, model, provider, progress_tracker=None, tracker_prefix=""):
        """
        评估一个提示词模板在一组test_cases上的表现，返回responses和eval_results。
        """
        requests = []
        for idx, test_case in enumerate(test_cases):
            user_input = test_case.get("user_input", "")
            replaced_prompt = render_prompt_template(prompt_obj, test_set_dict, test_case)
            requests.append({
                "model": model,
                "provider": provider,
                "messages": [
                    {"role": "system", "content": replaced_prompt},
                    {"role": "user", "content": user_input}
                ],
                "params": DEFAULT_GENERATION_PARAMS,
                "context": {
                    "expected_output": test_case.get("expected_output", ""),
                    "criteria": test_case.get("evaluation_criteria", {}),
                    "prompt_obj": prompt_obj,
                    "prompt_str": replaced_prompt,
                    "idx": idx
                }
            })
        gen_tracker = None
        eval_tracker = None
        if progress_tracker:
            gen_tracker = ProgressTracker(total_steps=len(test_cases), parent=progress_tracker, description=f"{tracker_prefix}gen")
            eval_tracker = ProgressTracker(total_steps=len(test_cases), parent=progress_tracker, description=f"{tracker_prefix}eval")
        responses = execute_models_sync(requests, progress_callback=lambda completed, total: gen_tracker.update(1) if gen_tracker else None)
        if gen_tracker: gen_tracker.complete()
        evaluation_tasks = []
        for idx, response in enumerate(responses):
            context = response.get("context", {})
            if not response.get("error") and response.get("text"):
                evaluation_tasks.append({
                    "model_response": response.get("text", ""),
                    "expected_output": context.get("expected_output", ""),
                    "criteria": context.get("criteria", {}),
                    "prompt_obj": context.get("prompt_obj", {}),
                    "prompt_str": context.get("prompt_str", ""),
                    "idx": context.get("idx", -1)
                })
        eval_results = []
        if evaluation_tasks:
            try:
                # 修复事件循环关闭问题
                try:
                    loop = asyncio.get_event_loop()
                    if loop.is_closed():
                        loop = asyncio.new_event_loop()
                        asyncio.set_event_loop(loop)
                except RuntimeError:
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                eval_results = loop.run_until_complete(evaluator.run_evaluation_async(evaluation_tasks))
                if eval_tracker: eval_tracker.complete()
            except Exception as e:
                print(f"[批量评估错误]: {e}")
        return responses, eval_results

    def iterative_prompt_optimization_sync(
        self,
        initial_prompt: object,  # 必须为提示词对象（dict），包含 template/variables 等
        test_set_dict: Dict,  # 修正类型为 dict，包含 variables 和 cases
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
        initial_prompt、current_prompt、best_iter_opt_prompt、best_prompt 均为提示词对象（dict），
        只有在实际 LLM 调用时才渲染为字符串。
        """
        # 获取用例列表
        test_cases = test_set_dict.get("cases", [])
        # Initialize event loop
        try:
            loop = asyncio.get_event_loop()
            if loop.is_closed():
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

        print(f"[调试] 开始迭代优化，计划执行 {max_iterations} 轮迭代")
        current_prompt_obj = initial_prompt  # 保持为 obj
        best_prompt_obj = initial_prompt
        best_score = -float('inf')
        history = []
        total_cases = len(test_cases)
        
        # Define expected number of optimized prompts for progress calculation consistency
        EXPECTED_OPTIMIZED_PROMPTS_COUNT = 3 
        # Steps for a single prompt's full evaluation cycle (generation + evaluation)
        STEPS_PER_SINGLE_FULL_EVALUATION = 2 * total_cases 

        # Logical steps per full iteration (current prompt eval + N optimized prompts eval)
        LOGICAL_STEPS_PER_FULL_ITERATION = STEPS_PER_SINGLE_FULL_EVALUATION * (1 + EXPECTED_OPTIMIZED_PROMPTS_COUNT)
        # Logical steps for the last iteration (only current prompt eval)
        LOGICAL_STEPS_FOR_LAST_ITERATION = STEPS_PER_SINGLE_FULL_EVALUATION

        progress_tracker_total_steps = 0
        if max_iterations > 0:
            if max_iterations == 1:
                progress_tracker_total_steps = LOGICAL_STEPS_FOR_LAST_ITERATION
            else:
                progress_tracker_total_steps = (max_iterations - 1) * LOGICAL_STEPS_PER_FULL_ITERATION + LOGICAL_STEPS_FOR_LAST_ITERATION
        
        # The 'total_eval_per_iter' for the callback lambda should represent the steps for a 'full' iteration type,
        # as the iteration number is calculated based on this.
        total_eval_per_iter_for_callback = LOGICAL_STEPS_PER_FULL_ITERATION
        
        if progress_callback:
            progress_tracker = ProgressTracker(
                total_steps=progress_tracker_total_steps, 
                callback=lambda current, total, desc, data: progress_callback(
                    current // total_eval_per_iter_for_callback + 1,  # iteration
                    max_iterations,
                    current % total_eval_per_iter_for_callback + 1,  # inner_idx (block level)
                    total_eval_per_iter_for_callback,                # inner_total (block level)
                    current,  # global_idx
                    total,    # global_total
                    desc,     # description/stage
                    data      # data from tracker
                ),
                description="初始化"
            )
        else:
            progress_tracker = None
        
        try:
            for i in range(max_iterations):
                print(f"[调试] 开始第 {i+1}/{max_iterations} 轮迭代")
                
                current_iteration_steps_contribution = 0

                # 创建每轮迭代的嵌套进度追踪器 (for current prompt evaluation)
                if progress_tracker:
                    iter_gen_tracker = ProgressTracker(
                        total_steps=total_cases, 
                        parent=progress_tracker,
                        description=f"gen_{i+1}" 
                    )
                    eval_tracker = ProgressTracker(
                        total_steps=total_cases, 
                        parent=progress_tracker,
                        description=f"eval_{i+1}" 
                    )
                else:
                    iter_gen_tracker = None
                    eval_tracker = None
                
                responses, eval_results = self._evaluate_prompt_on_testcases(
                    current_prompt_obj, test_cases, test_set_dict, evaluator, model, provider, progress_tracker, tracker_prefix=f"iter_{i+1}_"
                )

                avg_score = self._calc_avg_score(eval_results)
                print(f"[调试] 第 {i+1} 轮当前提示词评估完成，平均分: {avg_score:.2f}")

                # === 修复：组装标准 test_results 结构，便于后续分析 ===
                test_results_for_opt = []
                for idx, test_case in enumerate(test_cases):
                    # 取模型A输出
                    model_output = responses[idx].get("text", "") if idx < len(responses) else ""
                    # 取评估结果
                    eval_result = eval_results[idx] if idx < len(eval_results) else {}
                    test_results_for_opt.append({
                        "case_description": test_case.get("case_description", test_case.get("description", "")),
                        "user_input": test_case.get("user_input", ""),
                        "variables": test_case.get("variables", {}),
                        "expected_output": test_case.get("expected_output", ""),
                        "responses": [
                            {
                                "output": model_output,      # 明确用模型A输出
                                "evaluation": eval_result,   # 评估结果
                                # 可扩展 error 字段等
                            }
                        ]
                    })
                # === END 修复 ===

                history.append({
                    'iteration': i+1,
                    'stage': 'initial',
                    'prompt_obj': current_prompt_obj,  # 存 obj
                    'prompt_str': render_prompt_template(current_prompt_obj, test_set_dict, test_cases[0]) if test_cases else '',
                    'eval_results': eval_results,
                    'avg_score': avg_score
                })
                
                if avg_score > best_score:
                    best_score = avg_score
                    best_prompt_obj = current_prompt_obj
                
                if i < max_iterations - 1: 
                    print(f"[调试] 第 {i+1} 轮开始优化提示词")
                    print("--- eval_results ---")
                    print(eval_results)
                    # === 修复：传递标准 test_results_for_opt ===
                    opt_result = self.optimize_prompt_sync(
                        current_prompt_obj, test_results_for_opt, optimization_strategy
                    )
                    # === END 修复 ===
                    optimized_prompts = opt_result.get('optimized_prompts', [])
                    print(f"[调试] 第 {i+1} 轮生成了 {len(optimized_prompts)} 个优化版本")
                    
                    if not optimized_prompts:
                        print(f"[警告] 第 {i+1} 轮未能生成优化版本，使用当前提示词继续下一轮")
                        continue 
                    
                    best_iter_opt_prompt_obj = current_prompt_obj 
                    best_iter_opt_score = avg_score      

                    all_opt_versions_for_history = []
                    
                    for opt_idx, opt in enumerate(optimized_prompts):
                        if opt_idx >= EXPECTED_OPTIMIZED_PROMPTS_COUNT and progress_tracker:
                             print(f"[警告] 生成的优化提示词数量 ({len(optimized_prompts)}) 超出预期 ({EXPECTED_OPTIMIZED_PROMPTS_COUNT})，进度条可能不完全精确。")

                        # opt 现在应为 obj
                        # --- 修正：保证每个优化版本都为完整模板对象，保留变量默认值 ---
                        if isinstance(opt, dict) and "template" not in opt:
                            opt_prompt_obj = dict(current_prompt_obj)
                            opt_prompt_obj["template"] = opt.get("prompt", "")
                            # 保证 variables 字段完整
                            if "variables" in current_prompt_obj:
                                opt_prompt_obj["variables"] = current_prompt_obj["variables"]
                            # 复制其他常用字段
                            for k in ["name", "description"]:
                                if k in current_prompt_obj:
                                    opt_prompt_obj[k] = current_prompt_obj[k]
                            # 复制优化策略等信息
                            for k in ["strategy", "problem_addressed", "expected_improvements", "reasoning"]:
                                if k in opt:
                                    opt_prompt_obj[k] = opt[k]
                        else:
                            opt_prompt_obj = opt.get('prompt_obj', opt) if isinstance(opt, dict) else opt
                        opt_strategy = opt.get('strategy', '')
                        print(f"[调试] 第 {i+1} 轮评估优化版本 {opt_idx+1}: {opt_strategy}")

                        opt_responses, current_opt_eval_results = self._evaluate_prompt_on_testcases(
                            opt_prompt_obj, test_cases, test_set_dict, evaluator, model, provider, progress_tracker, tracker_prefix=f"opt_{i+1}_{opt_idx+1}_"
                        )
                        
                        opt_avg_score = self._calc_avg_score(current_opt_eval_results)
                        print(f"[调试] 第 {i+1} 轮优化版本 {opt_idx+1} ({opt_strategy}) 评分: {opt_avg_score:.2f}")
                        
                        opt_version_data = {
                            'iteration': i+1, 'stage': 'optimized', 'version': opt_idx + 1,
                            'prompt_obj': opt_prompt_obj, 'prompt_str': render_prompt_template(opt_prompt_obj, test_set_dict, test_cases[0]) if test_cases else '',
                            'strategy': opt_strategy,
                            'eval_results': current_opt_eval_results, 'avg_score': opt_avg_score,
                            'is_best': False 
                        }
                        all_opt_versions_for_history.append(opt_version_data)
                        
                        if opt_avg_score > best_iter_opt_score:
                            best_iter_opt_score = opt_avg_score
                            best_iter_opt_prompt_obj = opt_prompt_obj
                    
                    history.extend(all_opt_versions_for_history)

                    for hist_item in history:
                        if hist_item['iteration'] == i+1 and hist_item['stage'] == 'optimized' and hist_item['prompt_obj'] == best_iter_opt_prompt_obj:
                            hist_item['is_best'] = True
                            print(f"[调试] 第 {i+1} 轮选择优化版本 (策略: {hist_item.get('strategy')}) 作为本轮最佳，分数: {best_iter_opt_score:.2f}")
                            break
                    
                    # --- 修复逻辑：如果所有优化版本分数都不如当前提示词，则继续用原始提示词 ---
                    all_opt_scores = [v['avg_score'] for v in all_opt_versions_for_history]
                    if all_opt_scores and max(all_opt_scores) <= avg_score:
                        print(f"[修复] 所有优化版本分数({all_opt_scores})均不高于当前提示词({avg_score:.2f})，继续用原始提示词进入下一轮。")
                        current_prompt_obj = current_prompt_obj  # 保持不变
                    else:
                        current_prompt_obj = best_iter_opt_prompt_obj
                        if best_iter_opt_score > best_score:
                            best_score = best_iter_opt_score
                            best_prompt_obj = best_iter_opt_prompt_obj
                    # --- END 修复 ---
                else: 
                    print(f"[调试] 这是最后一轮迭代 ({i+1}/{max_iterations})，不进行新的优化。")

            # After the for loop, still inside the main try block
            print(f"[调试] 迭代优化完成，共记录 {len(history)} 条历史记录")
            for item_idx, item in enumerate(history): # Changed loop variable from i to item_idx
                print(f"[调试] 历史记录 #{item_idx+1}: 轮次={item.get('iteration')}, 阶段={item.get('stage')}, 版本={item.get('version', '-')}, 分数={item.get('avg_score'):.2f}")
            
            return {
                'best_prompt_obj': best_prompt_obj,  # 返回 obj
                'best_score': best_score,
                'history': history
            }
        except Exception as e:
            print(f"[严重错误] 迭代优化过程中出现异常: {e}")
            import traceback
            traceback.print_exc()
            return {
                'error': f"迭代优化失败: {str(e)}",
                'best_prompt_obj': best_prompt_obj, # Return current best even if error
                'best_score': best_score,
                'history': history # Return history up to the point of error
            }
        finally:
            # 确保事件循环在整个过程完成后关闭
            print("[调试] 关闭事件循环") 
            if 'loop' in locals() and loop and not loop.is_closed(): # Check if loop exists and is not closed
                loop.close()

    def _calc_avg_score(self, eval_results: List[Dict]) -> float:
        """计算评估结果的平均分"""
        scores = []
        for r in eval_results:
            if 'overall_score' in r and isinstance(r['overall_score'], (int, float)):
                scores.append(r['overall_score'])
        return sum(scores)/len(scores) if scores else 0

__all__ = ['PromptOptimizer']