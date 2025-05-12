import json
import asyncio
from typing import Dict, List, Optional, Any
from models.api_clients import get_client, get_provider_from_model
from config import load_config, get_api_key, get_system_template
from models.token_counter import count_tokens
# Import the new parallel executor
from utils.parallel_executor import execute_model, execute_models, execute_model_sync, execute_models_sync
# Import new constants and helpers
from utils.constants import (
    DEFAULT_EVALUATION_CRITERIA, 
    DEFAULT_NO_SAMPLE_EVALUATION_CRITERIA,
    DEFAULT_WITH_SAMPLE_EVALUATION_CRITERIA,
    DEFAULT_EVALUATION_PARAMS
)
from utils.helpers import (
    parse_json_response, 
    ensure_test_case_fields, 
    calculate_prompt_efficiency
)

class PromptEvaluator:
    """提示词评估引擎"""
    def __init__(self, evaluator_model=None):
        config = load_config()
        self.evaluator_model = evaluator_model or config.get("evaluator_model", "gpt-4") 
        self.provider = get_provider_from_model(self.evaluator_model)
        
        # 验证API密钥
        api_key = get_api_key(self.provider)
        if not api_key:
            # 如果没有API密钥，强制使用本地评估
            config["use_local_evaluation"] = True
            print(f"警告: {self.provider} 的API密钥未配置，将使用本地评估")
        
        self.use_local_evaluation = config.get("use_local_evaluation", False)
        self.client = get_client(self.provider) if not self.use_local_evaluation else None
        
        # 获取评估模板
        self.evaluator_template = get_system_template("evaluator")
        # 获取测试用例生成模板
        self.testcase_generator_template = get_system_template("testcase_generator")

    async def evaluate_response(self, model_response: str, expected_output: str, 
                               criteria: Dict, prompt: str) -> Dict:
        """评估模型响应"""
        # 如果配置为使用本地评估，直接返回本地评估结果
        if self.use_local_evaluation:
            return self.perform_basic_evaluation(model_response, expected_output, prompt)
            
        prompt_tokens = count_tokens(prompt)
        
        # 使用系统模板而不是硬编码的提示词
        template = self.evaluator_template.get("template", "")
        evaluation_prompt = template\
            .replace("{{prompt}}", prompt)\
            .replace("{{model_response}}", model_response)\
            .replace("{{expected_output}}", expected_output)\
            .replace("{{evaluation_criteria}}", json.dumps(criteria, ensure_ascii=False, indent=2))
        
        try:
            # 使用并行执行器进行模型调用
            result = await execute_model(
                self.evaluator_model,
                prompt=evaluation_prompt,
                provider=self.provider,
                params=DEFAULT_EVALUATION_PARAMS
            )
            
            eval_text = result.get("text", "")
            
            # 尝试解析JSON结果
            eval_data, error = parse_json_response(eval_text)
            
            if error:
                # 解析失败，返回错误信息并使用本地评估作为备选
                local_result = self.perform_basic_evaluation(model_response, expected_output, prompt)
                local_result["error"] = f"评估结果格式错误: {error}，已切换到本地评估"
                local_result["raw_response"] = eval_text
                return local_result
            
            # 添加提示词token信息
            eval_data["prompt_info"] = {
                "token_count": prompt_tokens,
            }
            
            # 如果评估结果中没有提示词效率评分，添加一个
            if "scores" in eval_data and "prompt_efficiency" not in eval_data["scores"]:
                prompt_efficiency = calculate_prompt_efficiency(prompt_tokens)
                eval_data["scores"]["prompt_efficiency"] = prompt_efficiency
                
                # 重新计算总体分数，包含提示词效率
                if "overall_score" in eval_data:
                    scores = eval_data["scores"]
                    total = sum(scores.values())
                    eval_data["overall_score"] = int(total / len(scores))
            
            return eval_data
                
        except Exception as e:
            # 发生错误时使用本地评估作为备选
            local_result = self.perform_basic_evaluation(model_response, expected_output, prompt)
            local_result["error"] = f"评估过程出错: {str(e)}，已切换到本地评估"
            return local_result
            
    def evaluate_response_sync(self, model_response, expected_output, criteria, prompt):
        """同步评估模型响应"""
        # 如果配置为使用本地评估，直接返回本地评估结果
        if self.use_local_evaluation:
            return self.perform_basic_evaluation(model_response, expected_output, prompt)

        import time
        import os
        from pathlib import Path
        log_dir = Path("data/logs")
        log_dir.mkdir(exist_ok=True, parents=True)
        
        # 创建新的日志文件
        log_file = log_dir / f"evaluator_log_{int(time.time())}.txt"
        
        # 记录日志
        def log_message(message):
            with open(log_file, "a", encoding="utf-8") as f:
                f.write(f"{message}\n")
            print(message)
        
        try:
            # 记录基本信息
            log_message(f"开始评估 - 使用模型: {self.evaluator_model}, 提供商: {self.provider}")
            
            if self.use_local_evaluation:
                log_message("当前配置为使用本地评估")
                return self.perform_basic_evaluation(model_response, expected_output, prompt)
            
            # 记录评估请求内容
            log_message(f"评估请求 - 模型响应长度: {len(model_response)}, 期望输出长度: {len(expected_output)}")
            log_message(f"评估标准: {criteria}")
            
            # 使用更安全的方法执行评估
            try:
                start_time = time.time()
                
                # 使用并行执行器的同步版本
                result = self._run_async_evaluation_sync(model_response, expected_output, criteria, prompt)
                end_time = time.time()
                
                # 记录评估结果
                if "error" in result:
                    log_message(f"评估过程发生错误: {result['error']}")
                else:
                    log_message(f"评估成功完成，耗时: {end_time - start_time:.2f}秒")
                
                return result
            except Exception as e:
                log_message(f"处理评估时出错: {str(e)}")
                # 使用本地评估作为备选
                local_result = self.perform_basic_evaluation(model_response, expected_output, prompt)
                local_result["error"] = f"无法执行AI评估，已切换到本地评估: {str(e)}"
                return local_result
                
        except Exception as e:
            import traceback
            error_details = traceback.format_exc()
            log_message(f"评估过程发生错误: {str(e)}")
            log_message(f"错误详情: {error_details}")
            
            # 发生错误时使用本地评估
            local_result = self.perform_basic_evaluation(model_response, expected_output, prompt)
            local_result["error"] = f"评估过程出错，已切换到本地评估: {str(e)}"
            return local_result
    
    def _run_async_evaluation_sync(self, model_response, expected_output, criteria, prompt):
        """使用并行执行器的同步版本执行评估"""
        # 构建评估提示词
        prompt_tokens = count_tokens(prompt)
        
        # 使用系统模板而不是硬编码的提示词
        template = self.evaluator_template.get("template", "")
        evaluation_prompt = template\
            .replace("{{prompt}}", prompt)\
            .replace("{{model_response}}", model_response)\
            .replace("{{expected_output}}", expected_output)\
            .replace("{{evaluation_criteria}}", json.dumps(criteria, ensure_ascii=False, indent=2))
        
        try:
            # 使用并行执行器的同步版本
            result = execute_model_sync(
                self.evaluator_model,
                prompt=evaluation_prompt,
                provider=self.provider,
                params=DEFAULT_EVALUATION_PARAMS
            )
            
            eval_text = result.get("text", "")
            
            # 尝试解析JSON结果
            eval_data, error = parse_json_response(eval_text)
            
            if error:
                # 解析失败，返回错误信息并使用本地评估作为备选
                local_result = self.perform_basic_evaluation(model_response, expected_output, prompt)
                local_result["error"] = f"评估结果格式错误: {error}，已切换到本地评估"
                local_result["raw_response"] = eval_text
                return local_result
            
            # 添加提示词token信息
            eval_data["prompt_info"] = {
                "token_count": prompt_tokens,
            }
            
            # 如果评估结果中没有提示词效率评分，添加一个
            if "scores" in eval_data and "prompt_efficiency" not in eval_data["scores"]:
                prompt_efficiency = calculate_prompt_efficiency(prompt_tokens)
                eval_data["scores"]["prompt_efficiency"] = prompt_efficiency
                
                # 重新计算总体分数，包含提示词效率
                if "overall_score" in eval_data:
                    scores = eval_data["scores"]
                    total = sum(scores.values())
                    eval_data["overall_score"] = int(total / len(scores))
            
            return eval_data
                
        except Exception as e:
            # 发生错误时使用本地评估作为备选
            local_result = self.perform_basic_evaluation(model_response, expected_output, prompt)
            local_result["error"] = f"评估过程出错: {str(e)}，已切换到本地评估"
            return local_result

    def perform_basic_evaluation(self, model_response: str, expected_output: str, prompt: str = "") -> Dict:
        """当评估模型无法使用时，执行基本评估"""
        try:
            # 简单评估 - 使用字符串相似度
            from difflib import SequenceMatcher

            # 计算相似度 (0-100分)
            similarity = SequenceMatcher(None, model_response.lower(), expected_output.lower()).ratio()
            accuracy_score = int(similarity * 100)

            # 基于长度比计算完整性 (0-100分)
            if len(expected_output) > 0:
                len_ratio = min(len(model_response) / len(expected_output), 2.0)
                completeness = int(min(len_ratio * 70, 100))
            else:
                completeness = 50  # 如果期望输出为空，则给予中等分数

            # 相关性和清晰度默认值
            relevance = 70  # 默认相关性分数
            clarity = 75    # 默认清晰度分数

            # 计算提示词效率得分 (0-40分)
            prompt_tokens = count_tokens(prompt) if prompt else 0
            prompt_efficiency = calculate_prompt_efficiency(prompt_tokens)

            # 计算质量总分 (0-100分)
            quality_score = int((accuracy_score + completeness + relevance + clarity) / 4)

            # 返回分数拆分
            return {
                "scores": {
                    "accuracy": accuracy_score,
                    "completeness": completeness,
                    "relevance": relevance,
                    "clarity": clarity,
                    "prompt_efficiency": prompt_efficiency
                },
                "quality_score": quality_score,
                "efficiency_score": prompt_efficiency
            }

        except Exception as e:
            return {
                "scores": {},
                "error": f"评估过程中发生错误: {str(e)}"
            }

    async def generate_test_cases_async(self, model: str, test_purpose: str, example_case: Dict, target_count: int = None, progress_callback=None) -> Dict:
        """异步生成测试用例"""
        if self.use_local_evaluation:
            return {"error": "本地评估模式不支持生成测试用例，请配置评估模型API密钥"}

        # 构建示例测试用例的文本表示
        example_evaluation = example_case.get("evaluation", {})
        scores = example_evaluation.get("scores", {})
        scores_text = ""
        for dimension, score in scores.items():
            scores_text += f"{dimension}: {score}/100, "
        example_text = f"""用例ID: {example_case.get('id', 'test-1')}
描述: {example_case.get('description', '示例测试')}
用户输入: \"{example_case.get('user_input', '')}\"
期望输出: \"{example_case.get('expected_output', '')}\"
评估结果: {scores_text.rstrip(', ')}"""

        # 打印调用模型的日志到console
        print(f"[TestCaseGen] 使用模型: {model}, 提供商: {self.provider}, 测试用例ID: {example_case.get('id', 'example_case')}, 目标数量: {target_count}, 提示词模版: testcase_generator")
        
        # 自动补足逻辑
        all_cases = []
        max_try = 50 if target_count and target_count > 30 else 10
        batch_size = 3  # 每次并行生成的批次数
        tried = 0
        
        # 如果有进度回调，初始化进度
        if progress_callback:
            progress_callback(0, target_count if target_count else 10)
        
        async def generate_batch(batch_count):
            """并行生成一批测试用例"""
            # 动态调整test_purpose中的数量描述
            if target_count:
                left = target_count - len(all_cases)
                if left <= 0:
                    return []
                # 每个请求生成一个测试用例
                import re
                purpose = test_purpose
                # 用正确的正则替换"请生成N个"部分
                purpose, n_sub = re.subn(r"请生成\d+个", f"请生成{batch_count}个", purpose)
                if n_sub == 0:
                    # 如果原本没有数量描述，直接加
                    purpose = f"{purpose}，请生成{batch_count}个高质量测试用例，覆盖不同场景和边界。"
            else:
                purpose = test_purpose
                
            # 构建生成prompt
            template = self.testcase_generator_template.get("template", "")
            generator_prompt = template\
                .replace("{{model}}", model)\
                .replace("{{test_purpose}}", purpose)\
                .replace("{{example_test_case}}", example_text)
                
            # 使用默认参数
            from utils.constants import DEFAULT_GENERATION_PARAMS
            
            try:
                # 使用并行执行器
                result = await execute_model(
                    self.evaluator_model,
                    prompt=generator_prompt,
                    provider=self.provider,
                    params=DEFAULT_GENERATION_PARAMS
                )
                response_text = result.get("text", "")
                
                # 尝试解析JSON结果
                test_cases_data, error = parse_json_response(response_text)
                
                if error:
                    print(f"[TestCaseGen] 错误: {error}")
                    # 尝试更宽松的解析方式提取部分可用的测试用例
                    return self._extract_partial_test_cases(response_text)
                
                # 提取测试用例
                cases = []
                if isinstance(test_cases_data, dict):
                    cases = test_cases_data.get("test_cases", [])
                    if not cases and len(test_cases_data) > 0:
                        # 可能JSON的结构不是预期的{"test_cases": [...]}, 而是直接包含测试用例
                        if "id" in test_cases_data:
                            # 单个测试用例的情况
                            cases = [test_cases_data]
                        else:
                            # 尝试从其他键获取测试用例
                            for key, value in test_cases_data.items():
                                if isinstance(value, list) and len(value) > 0:
                                    if isinstance(value[0], dict) and "user_input" in value[0]:
                                        cases = value
                                        break
                else:
                    # 直接是测试用例列表
                    cases = test_cases_data if isinstance(test_cases_data, list) else []
                
                return cases
            except Exception as e:
                print(f"[TestCaseGen] 错误: {str(e)}")
                return []
        
        while True:
            # 准备批量请求
            batch_requests = []
            for _ in range(batch_size):
                if target_count and len(all_cases) >= target_count:
                    break
                batch_requests.append(generate_batch(1))  # 每次生成1个测试用例
            
            if not batch_requests:
                break
                
            # 并行执行所有批次
            batch_results = await asyncio.gather(*batch_requests)
            
            # 处理结果
            added_count = 0
            exist_keys = set((c.get("user_input", "")+"|||"+c.get("expected_output", "")) for c in all_cases)
            
            for batch_cases in batch_results:
                for c in batch_cases:
                    key = c.get("user_input", "")+"|||"+c.get("expected_output", "")
                    if key not in exist_keys:
                        # 确保测试用例包含所有必要字段
                        c = ensure_test_case_fields(c)
                        all_cases.append(c)
                        exist_keys.add(key)
                        added_count += 1
            
            # 更新进度
            if progress_callback and target_count:
                progress_callback(len(all_cases), target_count)
                
            print(f"[TestCaseGen] 已生成 {len(all_cases)}/{target_count if target_count else '未指定'} 个测试用例，本批次新增: {added_count}")
            
            if not target_count:
                break  # 只调用一次
            if added_count == 0 and tried >= 3:
                # 如果连续几次没有新增，可能已经生成不出更多不同的用例了
                print(f"[TestCaseGen] 警告: 已连续多次无法生成新的独特测试用例，已生成 {len(all_cases)}/{target_count} 个")
                break
                
            tried += 1
            if tried >= max_try:
                print(f"[TestCaseGen] 达到最大尝试次数 {max_try}，已生成 {len(all_cases)}/{target_count if target_count else '未指定'} 个测试用例")
                break
        
        # 如果有进度回调，最后更新为100%
        if progress_callback and target_count:
            progress_callback(target_count, target_count)
                
        # 返回结果
        return {"test_cases": all_cases[:target_count] if target_count else all_cases}

    def generate_test_cases(self, model: str, test_purpose: str, example_case: Dict, target_count: int = None, progress_callback=None) -> Dict:
        """生成新的测试用例，支持自动补足数量
        Args:
            model: 模型名称
            test_purpose: 测试目的
            example_case: 示例测试用例，需要包含id, description, user_input, expected_output, evaluation
            target_count: 期望生成的测试用例数量（可选）
            progress_callback: 进度回调函数（可选）
        Returns:
            Dict: 生成的测试用例或错误信息
        """
        # 使用asyncio运行异步函数
        import asyncio
        try:
            # 尝试获取当前事件循环
            try:
                loop = asyncio.get_event_loop()
                if loop.is_closed():
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
            except RuntimeError:
                # 如果没有事件循环，创建一个新的
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
            
            # 运行异步函数
            result = loop.run_until_complete(
                self.generate_test_cases_async(
                    model, 
                    test_purpose, 
                    example_case, 
                    target_count, 
                    progress_callback
                )
            )
            return result
        except Exception as e:
            import traceback
            traceback.print_exc()
            return {"error": f"生成测试用例时出错: {str(e)}"}

    async def generate_test_cases_batch_async(self, model: str, test_purposes: List[str], example_case: Dict, target_count_per_purpose: int = 3, progress_callback=None) -> Dict:
        """异步批量生成多组测试用例
        
        Args:
            model: 模型名称
            test_purposes: 测试目的列表
            example_case: 示例测试用例
            target_count_per_purpose: 每个测试目的生成的用例数量
            progress_callback: 进度回调函数（可选）
            
        Returns:
            Dict: 包含多组测试用例的字典或错误信息
        """
        if self.use_local_evaluation:
            return {"error": "本地评估模式不支持生成测试用例，请配置评估模型API密钥"}
            
        all_test_cases = []
        errors = []
        total_purposes = len(test_purposes)
        total_expected_cases = total_purposes * target_count_per_purpose
        
        # 初始化进度
        if progress_callback:
            progress_callback(0, total_expected_cases)
        
        import asyncio
        
        # 创建每个方向的生成任务
        async def generate_for_purpose(i, purpose):
            try:
                print(f"[TestCaseGen] 正在处理第 {i+1}/{total_purposes} 个测试方向: {purpose[:50]}...")
                
                # 为当前方向生成测试用例
                result = await self.generate_test_cases_async(
                    model, 
                    purpose, 
                    example_case,
                    target_count=target_count_per_purpose
                )
                
                if "error" in result:
                    return {"error": f"生成'{purpose}'的测试用例失败: {result['error']}", "test_cases": []}
                    
                test_cases = result.get("test_cases", [])
                return {"test_cases": test_cases}
            except Exception as e:
                return {"error": f"处理测试方向时出错: {str(e)}", "test_cases": []}
        
        # 并行执行所有方向的生成任务
        tasks = []
        for i, purpose in enumerate(test_purposes):
            tasks.append(generate_for_purpose(i, purpose))
            
        # 执行所有任务并等待结果
        batch_results = await asyncio.gather(*tasks)
        
        # 处理结果
        for i, result in enumerate(batch_results):
            if "error" in result and result["error"]:
                errors.append(result["error"])
            test_cases = result.get("test_cases", [])
            all_test_cases.extend(test_cases)
            
            # 更新进度
            if progress_callback:
                completed_cases = min(len(all_test_cases), total_expected_cases)
                progress_callback(completed_cases, total_expected_cases)
                
            print(f"[TestCaseGen] 已完成第 {i+1}/{total_purposes} 个测试方向，累计生成 {len(all_test_cases)} 个测试用例")
        
        # 确保最终进度为100%
        if progress_callback:
            progress_callback(total_expected_cases, total_expected_cases)
            
        return {
            "test_cases": all_test_cases,
            "errors": errors if errors else None
        }

    def generate_test_cases_batch(self, model: str, test_purposes: List[str], example_case: Dict, target_count_per_purpose: int = 3, progress_callback=None) -> Dict:
        """批量生成多组测试用例
        
        Args:
            model: 模型名称
            test_purposes: 测试目的列表
            example_case: 示例测试用例
            target_count_per_purpose: 每个测试目的生成的用例数量
            progress_callback: 进度回调函数（可选）
            
        Returns:
            Dict: 包含多组测试用例的字典或错误信息
        """
        # 使用asyncio运行异步函数
        import asyncio
        try:
            # 尝试获取当前事件循环
            try:
                loop = asyncio.get_event_loop()
                if loop.is_closed():
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
            except RuntimeError:
                # 如果没有事件循环，创建一个新的
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
            
            # 运行异步函数
            result = loop.run_until_complete(
                self.generate_test_cases_batch_async(
                    model, 
                    test_purposes, 
                    example_case, 
                    target_count_per_purpose, 
                    progress_callback
                )
            )
            return result
        except Exception as e:
            import traceback
            traceback.print_exc()
            return {"error": f"批量生成测试用例时出错: {str(e)}"}

    async def run_evaluation_async(self, evaluation_tasks: List[Dict]) -> List[Dict]:
        """异步批量评估多个响应"""
        if self.use_local_evaluation:
            # 使用本地评估，并行处理所有任务
            return [
                self.perform_basic_evaluation(
                    task.get("model_response", ""),
                    task.get("expected_output", ""),
                    task.get("prompt", "")  # 传递prompt参数
                )
                for task in evaluation_tasks
            ]
        
        # 准备并行请求
        requests = []
        for task in evaluation_tasks:
            model_response = task.get("model_response", "")
            expected_output = task.get("expected_output", "")
            criteria = task.get("criteria", {})
            prompt = task.get("prompt", "")
            
            # 构建评估提示词
            template = self.evaluator_template.get("template", "")
            evaluation_prompt = template\
                .replace("{{prompt}}", prompt)\
                .replace("{{model_response}}", model_response)\
                .replace("{{expected_output}}", expected_output)\
                .replace("{{evaluation_criteria}}", json.dumps(criteria, ensure_ascii=False, indent=2))
            
            # 添加请求到批处理队列
            requests.append({
                "model": self.evaluator_model,
                "provider": self.provider,
                "prompt": evaluation_prompt,
                "params": DEFAULT_EVALUATION_PARAMS,
                "context": {
                    "model_response": model_response,
                    "expected_output": expected_output,
                    "prompt": prompt  # 存储原始提示词以便后续使用
                }
            })
        
        # 批量执行请求
        try:
            responses = await execute_models(requests)
            
            # 处理响应结果
            results = []
            for i, response in enumerate(responses):
                task = evaluation_tasks[i]
                context = response.get("context", {})
                model_response = context.get("model_response", "")
                expected_output = context.get("expected_output", "")
                prompt = task.get("prompt", "")  # 获取原始提示词

                # 优先使用API返回的真实prompt_tokens
                prompt_tokens = None
                usage = response.get("usage", {})
                if usage:
                    # OpenAI/通用格式
                    prompt_tokens = usage.get("prompt_tokens")
                    # Anthropic格式
                    if prompt_tokens is None:
                        prompt_tokens = usage.get("input_tokens")
                if prompt_tokens is None:
                    prompt_tokens = count_tokens(prompt)

                # 如果API调用成功，解析结果
                if "text" in response and not response.get("error"):
                    try:
                        eval_text = response.get("text", "")
                        # 解析JSON结果
                        eval_data, error = parse_json_response(eval_text)
                        if error:
                            # 解析失败，使用本地评估
                            local_result = self.perform_basic_evaluation(model_response, expected_output, prompt)
                            local_result["error"] = f"评估结果解析失败: {error}"
                            local_result["raw_response"] = eval_text
                            results.append(local_result)
                            continue
                        # 添加提示词token信息
                        eval_data["prompt_info"] = {
                            "token_count": prompt_tokens,
                        }
                        # 如果评估结果中没有提示词效率评分，添加一个
                        if "scores" in eval_data and "prompt_efficiency" not in eval_data["scores"]:
                            prompt_efficiency = calculate_prompt_efficiency(prompt_tokens)
                            eval_data["scores"]["prompt_efficiency"] = prompt_efficiency
                            # 重新计算总体分数，包含提示词效率
                            if "overall_score" in eval_data:
                                scores = eval_data["scores"]
                                total = sum(scores.values())
                                eval_data["overall_score"] = int(total / len(scores))
                        results.append(eval_data)
                    except Exception as e:
                        # 解析错误，使用本地评估
                        local_result = self.perform_basic_evaluation(model_response, expected_output, prompt)
                        local_result["error"] = f"评估结果解析失败: {str(e)}"
                        local_result["raw_response"] = response.get("text", "")
                        results.append(local_result)
                else:
                    # API调用失败，使用本地评估
                    local_result = self.perform_basic_evaluation(model_response, expected_output, prompt)
                    local_result["error"] = response.get("error", "未知错误")
                    results.append(local_result)
            
            return results
        except Exception as e:
            # 批处理失败，回退到单个处理
            print(f"批量评估失败: {str(e)}，回退到单个处理模式")
            results = []
            for task in evaluation_tasks:
                try:
                    result = await self.evaluate_response(
                        task.get("model_response", ""),
                        task.get("expected_output", ""),
                        task.get("criteria", {}),
                        task.get("prompt", "")
                    )
                    results.append(result)
                except Exception as ex:
                    # 单个评估也失败，使用本地评估
                    local_result = self.perform_basic_evaluation(
                        task.get("model_response", ""),
                        task.get("expected_output", ""),
                        task.get("prompt", "")  # 传递prompt参数
                    )
                    local_result["error"] = f"评估失败: {str(ex)}"
                    results.append(local_result)
            
            return results

    def run_evaluation(self, evaluation_tasks: List[Dict]) -> List[Dict]:
        """同步批量评估，自动调度事件循环，支持并发"""
        import asyncio
        try:
            # 创建一个新的事件循环，不尝试重用现有循环
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
            try:
                result = loop.run_until_complete(self.run_evaluation_async(evaluation_tasks))
                return result
            finally:
                # 不关闭事件循环，后续操作可能还需要使用
                pass
        except Exception as e:
            import traceback
            print(f"批量评估遇到错误: {str(e)}")
            print(traceback.format_exc())
            # 如果出现异常，返回使用本地评估的结果
            return [
                self.perform_basic_evaluation(
                    task.get("model_response", ""),
                    task.get("expected_output", ""),
                    task.get("prompt", "")
                )
                for task in evaluation_tasks
            ]
    
    def evaluate_dialogue_turn(self, user_input: str, model_response: str, prompt_template: str, turn_number: int, expected_output: str = "") -> Dict:
        """评估单轮对话质量
        
        Args:
            user_input: 用户输入的消息
            model_response: 模型的回复
            prompt_template: 使用的提示词模板
            turn_number: 对话轮次编号
            expected_output: 期望输出，如果为空则为无样本评估
            
        Returns:
            Dict: 评估结果字典
        """
        # 构建评估提示
        combined_prompt = f"用户问题:\n{user_input}\n\n提示词模板:\n{prompt_template}"
        
        # 检查是否为无样本评估场景
        is_no_sample = expected_output == ""
        
        if is_no_sample:
            # 无样本评估时使用简化的评估标准
            evaluation_criteria = DEFAULT_NO_SAMPLE_EVALUATION_CRITERIA
            # 设置通用期望输出
            expected_output = f"回合 {turn_number}：根据提示词和用户问题给出有帮助、相关且连贯的回答"
        else:
            # 有样本评估时使用完整的评估标准
            evaluation_criteria = DEFAULT_WITH_SAMPLE_EVALUATION_CRITERIA
        
        # 调用评估器
        evaluation = self.evaluate_response_sync(
            model_response,
            expected_output,
            evaluation_criteria,
            combined_prompt
        )
        
        # 计算针对提示词和模型的问题诊断
        if "scores" in evaluation:
            scores = evaluation["scores"]
            
            # 分析可能的问题
            issues = []
            
            # 根据评估标准动态调整问题诊断逻辑
            if not is_no_sample and scores.get("accuracy", 0) < 70:
                issues.append({
                    "type": "model",
                    "severity": "high" if scores.get("accuracy", 0) < 50 else "medium",
                    "description": "模型生成的内容可能不准确",
                    "suggestion": "考虑使用更高级的模型或提供更明确的知识指导"
                })
                
            if scores.get("coherence", 0) < 70:
                issues.append({
                    "type": "model",
                    "severity": "medium",
                    "description": "模型生成的内容连贯性不足",
                    "suggestion": "调低temperature参数以提高回复的连贯性"
                })
            
            # 提示词问题判断标准
            if scores.get("prompt_following", 0) < 70:
                issues.append({
                    "type": "prompt",
                    "severity": "high" if scores.get("prompt_following", 0) < 50 else "medium",
                    "description": "模型未能良好地遵循提示词指令",
                    "suggestion": "明确提示词中的指令，增加详细的格式要求和约束"
                })
                
            if not is_no_sample and scores.get("consistency", 0) < 70:
                issues.append({
                    "type": "prompt",
                    "severity": "medium",
                    "description": "模型回复与之前对话缺乏一致性",
                    "suggestion": "在提示词中强调保持上下文一致性，或增加对话历史总结指令"
                })
                
            # 将问题分析添加到评估结果中
            evaluation["issues"] = issues
        
        return evaluation
    
    def _extract_partial_test_cases(self, text):
        """尝试从文本中提取部分可用的测试用例"""
        cases = []
        import re
        import time
        import uuid
        
        try:
            # 寻找可能的测试用例模式，即包含user_input和expected_output的段落
            user_input_pattern = r'"user_input"\s*:\s*"([^"]*)"|"user_input"\s*:\s*`([^`]*)`'
            expected_output_pattern = r'"expected_output"\s*:\s*"([^"]*)"|"expected_output"\s*:\s*`([^`]*)`'
            
            # 如果存在多个可能的测试用例，尝试分割
            case_blocks = re.split(r'[\{\}]\s*,\s*[\{\}]', text)
            
            for block in case_blocks:
                user_input_match = re.search(user_input_pattern, block)
                expected_output_match = re.search(expected_output_pattern, block)
                
                if user_input_match and expected_output_match:
                    # 提取用户输入
                    user_input = user_input_match.group(1) if user_input_match.group(1) else user_input_match.group(2)
                    
                    # 提取期望输出
                    expected_output = expected_output_match.group(1) if expected_output_match.group(1) else expected_output_match.group(2)
                    
                    # 创建基本测试用例
                    if user_input and expected_output:
                        case = {
                            "user_input": user_input,
                            "expected_output": expected_output,
                        }
                        # 使用工具函数确保所有必要字段
                        case = ensure_test_case_fields(case)
                        cases.append(case)
        except Exception as e:
            print(f"[TestCaseGen] 尝试提取测试用例时出错: {str(e)}")
            
        return cases