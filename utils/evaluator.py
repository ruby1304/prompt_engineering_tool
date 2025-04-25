import json
import asyncio
from typing import Dict, List, Optional, Any
from models.api_clients import get_client, get_provider_from_model
from config import load_config, get_api_key, get_system_template
from models.token_counter import count_tokens

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
            return self.perform_basic_evaluation(model_response, expected_output)
            
        prompt_tokens = count_tokens(prompt)
        
        # 使用系统模板而不是硬编码的提示词
        template = self.evaluator_template.get("template", "")
        evaluation_prompt = template\
            .replace("{{prompt}}", prompt)\
            .replace("{{model_response}}", model_response)\
            .replace("{{expected_output}}", expected_output)\
            .replace("{{evaluation_criteria}}", json.dumps(criteria, ensure_ascii=False, indent=2))
        
        evaluation_params = {
            "temperature": 0.2,  # 低温度以获得一致的评估
            "max_tokens": 1500
        }
        
        try:
            result = await self.client.generate(evaluation_prompt, self.evaluator_model, evaluation_params)
            eval_text = result.get("text", "")
            
            # 尝试解析JSON结果
            try:
                # 清理可能的前后缀文本
                if "```json" in eval_text:
                    eval_text = eval_text.split("```json")[1].split("```")[0].strip()
                elif "```" in eval_text:
                    eval_text = eval_text.split("```")[1].split("```")[0].strip()
                
                eval_data = json.loads(eval_text)
                
                # 添加提示词token信息
                eval_data["prompt_info"] = {
                    "token_count": prompt_tokens,
                }
                
                return eval_data
            except json.JSONDecodeError:
                # 解析失败，返回错误信息并使用本地评估作为备选
                local_result = self.perform_basic_evaluation(model_response, expected_output)
                local_result["error"] = "评估结果格式错误，已切换到本地评估"
                local_result["raw_response"] = eval_text
                return local_result
                
        except Exception as e:
            # 发生错误时使用本地评估作为备选
            local_result = self.perform_basic_evaluation(model_response, expected_output)
            local_result["error"] = f"评估过程出错: {str(e)}，已切换到本地评估"
            return local_result
            
    def evaluate_response_sync(self, model_response, expected_output, criteria, prompt):
        """同步评估模型响应"""
        # 如果配置为使用本地评估，直接返回本地评估结果
        if self.use_local_evaluation:
            return self.perform_basic_evaluation(model_response, expected_output)

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
                return self.perform_basic_evaluation(model_response, expected_output)
            
            # 记录评估请求内容
            log_message(f"评估请求 - 模型响应长度: {len(model_response)}, 期望输出长度: {len(expected_output)}")
            log_message(f"评估标准: {criteria}")
            
            # 在Streamlit环境中，使用更安全的方法运行异步函数
            try:
                start_time = time.time()
                # 直接运行异步评估函数，不创建新的事件循环
                result = self._run_async_evaluation(model_response, expected_output, criteria, prompt)
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
                local_result = self.perform_basic_evaluation(model_response, expected_output)
                local_result["error"] = f"无法执行AI评估，已切换到本地评估: {str(e)}"
                return local_result
                
        except Exception as e:
            import traceback
            error_details = traceback.format_exc()
            log_message(f"评估过程发生错误: {str(e)}")
            log_message(f"错误详情: {error_details}")
            
            # 发生错误时使用本地评估
            local_result = self.perform_basic_evaluation(model_response, expected_output)
            local_result["error"] = f"评估过程出错，已切换到本地评估: {str(e)}"
            return local_result
            
    def _run_async_evaluation(self, model_response, expected_output, criteria, prompt):
        """以同步方式运行异步评估函数，适合在Streamlit环境使用"""
        # 构建评估提示词
        prompt_tokens = count_tokens(prompt)
        
        # 使用系统模板而不是硬编码的提示词
        template = self.evaluator_template.get("template", "")
        evaluation_prompt = template\
            .replace("{{prompt}}", prompt)\
            .replace("{{model_response}}", model_response)\
            .replace("{{expected_output}}", expected_output)\
            .replace("{{evaluation_criteria}}", json.dumps(criteria, ensure_ascii=False, indent=2))
        
        evaluation_params = {
            "temperature": 0.2,  # 低温度以获得一致的评估
            "max_tokens": 1500
        }
        
        try:
            # 使用同步方式调用API客户端
            result = self.client.generate_sync(evaluation_prompt, self.evaluator_model, evaluation_params)
            eval_text = result.get("text", "")
            
            # 尝试解析JSON结果
            try:
                # 清理可能的前后缀文本
                if "```json" in eval_text:
                    eval_text = eval_text.split("```json")[1].split("```")[0].strip()
                elif "```" in eval_text:
                    eval_text = eval_text.split("```")[1].split("```")[0].strip()
                
                eval_data = json.loads(eval_text)
                
                # 添加提示词token信息
                eval_data["prompt_info"] = {
                    "token_count": prompt_tokens,
                }
                
                return eval_data
            except json.JSONDecodeError:
                # 解析失败，返回错误信息并使用本地评估作为备选
                local_result = self.perform_basic_evaluation(model_response, expected_output)
                local_result["error"] = "评估结果格式错误，已切换到本地评估"
                local_result["raw_response"] = eval_text
                return local_result
                
        except Exception as e:
            # 发生错误时使用本地评估作为备选
            local_result = self.perform_basic_evaluation(model_response, expected_output)
            local_result["error"] = f"评估过程出错: {str(e)}，已切换到本地评估"
            return local_result

    def perform_basic_evaluation(self, model_response: str, expected_output: str) -> Dict:
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

            # 计算总体分数
            overall_score = int((accuracy_score + completeness + relevance + clarity) / 4)

            # 生成基本评估结果
            return {
                "scores": {
                    "accuracy": accuracy_score,
                    "completeness": completeness,
                    "relevance": relevance,
                    "clarity": clarity
                },
                "analysis": "这是一个本地生成的基本评估，未使用评估模型。本地评估主要基于文本相似度，可能无法准确评估语义理解。",
                "overall_score": overall_score,
                "prompt_info": {
                    "token_count": count_tokens(model_response),
                },
                "is_local_evaluation": True  # 标记这是本地评估
            }
        except Exception as e:
            return {
                "error": f"本地评估出错: {str(e)}",
                "prompt_info": {
                    "token_count": count_tokens(model_response),
                },
                "is_local_evaluation": True
            }

    def generate_test_cases(self, model: str, test_purpose: str, example_case: Dict, target_count: int = None) -> Dict:
        """生成新的测试用例，支持自动补足数量
        Args:
            model: 模型名称
            test_purpose: 测试目的
            example_case: 示例测试用例，需要包含id, description, user_input, expected_output, evaluation
            target_count: 期望生成的测试用例数量（可选）
        Returns:
            Dict: 生成的测试用例或错误信息
        """
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
        print(f"[TestCaseGen] 使用模型: {self.evaluator_model}, 提供商: {self.provider}, 测试用例ID: {example_case.get('id', 'test-1')}, 提示词模版: testcase_generator")
        # 自动补足逻辑
        all_cases = []
        max_try = 10  # 最多尝试10次，防止死循环
        tried = 0
        while True:
            # 动态调整test_purpose中的数量描述
            if target_count:
                left = target_count - len(all_cases)
                if left <= 0:
                    break
                purpose = test_purpose
                import re
                # 用正确的正则替换“请生成N个”部分
                purpose, n_sub = re.subn(r"请生成\d+个", f"请生成{left}个", purpose)
                if n_sub == 0:
                    # 如果原本没有数量描述，直接加
                    purpose = f"{purpose}，请生成{left}个高质量测试用例，覆盖不同场景和边界。"
            else:
                purpose = test_purpose
            # 构建生成prompt
            template = self.testcase_generator_template.get("template", "")
            generator_prompt = template\
                .replace("{{model}}", model)\
                .replace("{{test_purpose}}", purpose)\
                .replace("{{example_test_case}}", example_text)
            generator_params = {
                "temperature": 0.7,
                "max_tokens": 2000
            }
            try:
                result = self.client.generate_sync(generator_prompt, self.evaluator_model, generator_params)
                response_text = result.get("text", "")
                # 尝试解析JSON结果
                try:
                    if "```json" in response_text:
                        response_text = response_text.split("```json")[1].split("```", 1)[0].strip()
                    elif "```" in response_text:
                        response_text = response_text.split("```", 1)[1].split("```", 1)[0].strip()
                    test_cases_data = json.loads(response_text)
                    cases = test_cases_data.get("test_cases", []) if isinstance(test_cases_data, dict) else test_cases_data
                    # 去重（按user_input+expected_output）
                    exist_keys = set((c.get("user_input", "")+"|||"+c.get("expected_output", "")) for c in all_cases)
                    for c in cases:
                        key = c.get("user_input", "")+"|||"+c.get("expected_output", "")
                        if key not in exist_keys:
                            all_cases.append(c)
                            exist_keys.add(key)
                    if not target_count:
                        break  # 只调用一次
                except json.JSONDecodeError:
                    return {
                        "error": "测试用例生成结果格式错误",
                        "raw_response": response_text
                    }
            except Exception as e:
                return {
                    "error": f"生成测试用例时出错: {str(e)}"
                }
            tried += 1
            if tried >= max_try:
                break
        # 返回结果
        return {"test_cases": all_cases[:target_count] if target_count else all_cases}

    def generate_user_inputs(self, test_set_desc: str, count: int = 5) -> Dict:
        """使用LLM生成一批高质量用户输入，仅返回用户输入列表"""
        if self.use_local_evaluation:
            return {"error": "本地评估模式不支持AI生成用户输入，请配置评估模型API密钥"}
        prompt = f"""你是一位专业的AI测试用例设计专家。请根据以下测试集描述，生成{count}个高质量的用户输入，覆盖不同场景和边界条件。只需返回用户输入本身，不要包含期望输出或其他内容。请以JSON数组格式返回，例如：\n[\n  "用户输入1",\n  "用户输入2",\n  ...\n]。\n\n测试集描述：{test_set_desc}\n"""
        params = {"temperature": 0.7, "max_tokens": 1000}
        try:
            result = self.client.generate_sync(prompt, self.evaluator_model, params)
            response_text = result.get("text", "")
            # 清理可能的前后缀文本
            if "```json" in response_text:
                response_text = response_text.split("```json")[1].split("```", 1)[0].strip()
            elif "```" in response_text:
                response_text = response_text.split("```", 1)[1].split("```", 1)[0].strip()
            # 解析JSON
            try:
                user_inputs = json.loads(response_text)
                if isinstance(user_inputs, list):
                    # 只保留非空字符串
                    user_inputs = [x for x in user_inputs if isinstance(x, str) and x.strip()]
                    return {"user_inputs": user_inputs[:count]}
                else:
                    return {"error": "AI返回内容格式不正确", "raw_response": response_text}
            except Exception:
                return {"error": "无法解析AI返回的用户输入JSON", "raw_response": response_text}
        except Exception as e:
            return {"error": f"生成用户输入时出错: {str(e)}"}

    async def run_evaluation_async(self, evaluation_tasks: List[Dict]) -> List[Dict]:
        """批量并发评估测试用例，返回评估结果列表"""
        import asyncio
        from config import get_concurrency_limit
        concurrency_limit = get_concurrency_limit(self.provider, self.evaluator_model)
        semaphore = asyncio.Semaphore(concurrency_limit)
        
        async def eval_one(task: Dict):
            # 从任务字典中提取所需参数
            model_response = task.get("model_response", "")
            expected_output = task.get("expected_output", "")
            criteria = task.get("criteria", {})
            prompt = task.get("prompt", "") # 获取提示词
            
            async with semaphore:
                # 调用单个评估函数
                return await self.evaluate_response(model_response, expected_output, criteria, prompt)

        # 为每个任务创建协程
        tasks = [eval_one(task) for task in evaluation_tasks]
        # 并发执行所有评估任务
        return await asyncio.gather(*tasks)

    def run_evaluation(self, evaluation_tasks: List[Dict]) -> List[Dict]:
        """同步批量评估，自动调度事件循环，支持并发"""
        import asyncio
        try:
            # 尝试获取当前线程的事件循环
            loop = asyncio.get_event_loop()
        except RuntimeError:
            # 如果没有事件循环，创建一个新的
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        
        try:
            # 运行异步批量评估函数
            return loop.run_until_complete(self.run_evaluation_async(evaluation_tasks))
        finally:
            # 如果事件循环不是由外部管理且未在运行，则关闭它
            if not loop.is_running():
                 try:
                     # Check if loop is closed before trying to close it
                     if not loop.is_closed():
                         loop.close()
                 except Exception as e:
                     print(f"Error closing event loop: {e}") # Log error if closing fails