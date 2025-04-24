import json
import asyncio
from typing import Dict, List, Optional, Any
from models.api_clients import get_client, get_provider_from_model
from config import load_config, get_api_key, get_system_template
from models.token_counter import count_tokens

class PromptEvaluator:
    """提示词评估引擎"""
    def __init__(self):
        config = load_config()
        self.evaluator_model = config.get("evaluator_model", "gpt-4") 
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