import json
import asyncio
from typing import Dict, List, Optional, Any
from models.api_clients import get_client, get_provider_from_model
from config import load_config, get_api_key
from models.token_counter import count_tokens

class PromptEvaluator:
    """提示词评估引擎"""
    def __init__(self):
        config = load_config()
        self.evaluator_model = config.get("evaluator_model", "gpt-4") 
        self.provider = get_provider_from_model(self.evaluator_model)
        self.client = get_client(self.provider)
    
    async def evaluate_response(self, model_response: str, expected_output: str, 
                               criteria: Dict, prompt: str) -> Dict:
        """评估模型响应"""
        prompt_tokens = count_tokens(prompt)
        
        evaluation_prompt = f"""
你是一个专业的AI响应质量评估专家。请对以下AI生成的响应进行评估:

原始提示词: {prompt}

模型响应:
{model_response}

期望输出:
{expected_output}

评估标准:
{json.dumps(criteria, ensure_ascii=False, indent=2)}

请按以下格式给出评估分数和分析:
{{
  "scores": {{
    "accuracy": <0-100分，评估响应与期望输出的准确度>,
    "completeness": <0-100分，评估响应是否涵盖了所有期望的要点>,
    "relevance": <0-100分，评估响应与原始提示词的相关性>,
    "clarity": <0-100分，评估响应的清晰度和可理解性>
  }},
  "analysis": "<详细分析，包括优点和改进建议>",
  "overall_score": <0-100分，综合评分>
}}

仅返回JSON格式的评估结果，不要包含其他文本。
"""
        
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
                # 解析失败，返回错误信息
                return {
                    "error": "评估结果格式错误，无法解析为JSON",
                    "raw_response": eval_text,
                    "prompt_info": {
                        "token_count": prompt_tokens,
                    }
                }
        except Exception as e:
            return {
                "error": f"评估过程出错: {str(e)}",
                "prompt_info": {
                    "token_count": prompt_tokens,
                }
            }
            
    def evaluate_response_sync(self, model_response: str, expected_output: str, 
                             criteria: Dict, prompt: str) -> Dict:
        """同步版本的评估函数（包装异步函数）"""

        # 检查是否强制使用本地评估
        config = load_config()
        if config.get("use_local_evaluation", False):
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
            # 检查评估模型API密钥
            provider = get_provider_from_model(self.evaluator_model)
            api_key = get_api_key(provider)
            
            log_message(f"开始评估 - 使用模型: {self.evaluator_model}, 提供商: {provider}")
            
            if not api_key:
                log_message(f"警告: 评估模型 {self.evaluator_model} 的API密钥未设置或为空")
                local_result = self.perform_basic_evaluation(model_response, expected_output)
                log_message(f"使用本地评估作为后备: {local_result}")
                return local_result
            else:
                log_message(f"API密钥已配置 (长度: {len(api_key)})")
            
            # 创建事件循环
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                # 记录评估请求内容
                log_message(f"评估请求 - 模型响应长度: {len(model_response)}, 期望输出长度: {len(expected_output)}")
                log_message(f"评估标准: {criteria}")
                
                # 运行异步评估
                start_time = time.time()
                result = loop.run_until_complete(self.evaluate_response(
                    model_response, expected_output, criteria, prompt
                ))
                end_time = time.time()
                
                # 记录评估结果
                if "error" in result:
                    log_message(f"评估模型返回错误: {result['error']}")
                    if "raw_response" in result:
                        log_message(f"原始响应: {result['raw_response']}")
                    
                    log_message("使用本地评估作为后备")
                    local_result = self.perform_basic_evaluation(model_response, expected_output)
                    log_message(f"本地评估结果: {local_result}")
                    return local_result
                else:
                    log_message(f"评估成功完成，耗时: {end_time - start_time:.2f}秒")
                    log_message(f"评估结果: {result}")
                    return result
            finally:
                loop.close()
        except Exception as e:
            import traceback
            error_details = traceback.format_exc()
            log_message(f"评估过程发生错误: {str(e)}")
            log_message(f"错误详情: {error_details}")
            
            local_result = self.perform_basic_evaluation(model_response, expected_output)
            log_message(f"使用本地评估作为后备: {local_result}")
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