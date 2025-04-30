import json
import asyncio
import concurrent.futures
import threading
from typing import Dict, List, Optional, Any, Tuple

from models.api_clients import get_client, get_provider_from_model
from config import load_config, get_system_template
# 导入新的并行执行器
from utils.parallel_executor import execute_model, execute_models, execute_model_sync, execute_models_sync
from utils.optimizer import PromptOptimizer

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
                    "temperature": 0.9,
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
            
            # 检测原始提示词中的变量结构 - 使用正则表达式匹配 {{variable}}
            import re
            template_vars = re.findall(r'{{(.*?)}}', self.current_prompt)
            self._log("DEBUG", f"检测到原始提示词中包含 {len(template_vars)} 个模板变量: {', '.join(template_vars)}")
            
            # 添加重试机制，最多尝试3次
            max_retries = 10
            retry_count = 0
            optimization_result = None
            
            while retry_count < max_retries:
                # 使用优化器优化提示词
                optimization_result = self.optimizer.optimize_prompt_sync(
                    original_prompt=self.current_prompt,
                    test_results=test_results,
                    optimization_strategy=self.optimization_strategy
                )
                
                # 检查结果是否有错误
                if "error" in optimization_result:
                    error_msg = optimization_result["error"]
                    if "空响应内容" in error_msg or "JSON解析失败" in error_msg:
                        retry_count += 1
                        self._log("WARNING", f"优化尝试 {retry_count}/{max_retries} 失败: {error_msg}，准备重试...")
                        continue
                    else:
                        # 如果是其他错误，不重试
                        self._log("ERROR", f"优化提示词时出错: {error_msg}")
                        return None
                
                # 获取优化结果
                optimized_prompts = optimization_result.get("optimized_prompts", [])
                if not optimized_prompts:
                    retry_count += 1
                    self._log("WARNING", f"优化尝试 {retry_count}/{max_retries} 未生成优化提示词，准备重试...")
                    continue
                
                # 选择第一个优化提示词
                best_opt = optimized_prompts[0]
                new_prompt = best_opt.get("prompt", "")
                
                if not new_prompt:
                    retry_count += 1
                    self._log("WARNING", f"优化尝试 {retry_count}/{max_retries} 生成了空提示词，准备重试...")
                    continue
                
                # 如果执行到这里，表示成功获得优化提示词，跳出循环
                break
            
            # 如果所有尝试都失败，记录错误并返回 None
            if retry_count == max_retries:
                self._log("ERROR", f"在 {max_retries} 次尝试后仍未能成功优化提示词")
                return None
                
            # 检查优化后的提示词是否保留了所有原始变量
            # 如果有变量丢失，尝试恢复它们
            if template_vars:
                missing_vars = []
                for var in template_vars:
                    var_pattern = r'{{' + re.escape(var) + r'}}'
                    if not re.search(var_pattern, new_prompt):
                        missing_vars.append(var)
                
                if missing_vars:
                    self._log("WARNING", f"优化后提示词中缺少以下变量: {', '.join(missing_vars)}")
                    
                    # 尝试恢复丢失的变量 - 这是一个简化的修复方法
                    # 如果原始提示词中变量在特定的位置或上下文中，我们应该尝试保持这个上下文
                    for var in missing_vars:
                        # 查找变量在原始提示词中的上下文
                        var_pattern = r'{{' + re.escape(var) + r'}}'
                        var_match = re.search(r'(.{0,30})' + var_pattern + r'(.{0,30})', self.current_prompt)
                        if var_match:
                            # 获取变量前后的上下文
                            before_context = var_match.group(1)
                            after_context = var_match.group(2)
                            
                            # 尝试找到适合插入变量的位置
                            # 这里使用一个简化的启发式方法：
                            # 查找上下文前部分的最后出现位置，或上下文后部分的第一次出现位置
                            
                            # 尝试查找前部分上下文
                            if before_context and len(before_context.strip()) > 5:
                                last_before = new_prompt.rfind(before_context.strip())
                                if last_before != -1:
                                    insert_pos = last_before + len(before_context)
                                    new_prompt = new_prompt[:insert_pos] + f" {{{{{var}}}}} " + new_prompt[insert_pos:]
                                    self._log("INFO", f"在位置 {insert_pos} 恢复了变量 {{{{{var}}}}}")
                                    continue
                            
                            # 尝试查找后部分上下文
                            if after_context and len(after_context.strip()) > 5:
                                first_after = new_prompt.find(after_context.strip())
                                if first_after != -1:
                                    insert_pos = first_after
                                    new_prompt = new_prompt[:insert_pos] + f" {{{{{var}}}}} " + new_prompt[insert_pos:]
                                    self._log("INFO", f"在位置 {insert_pos} 恢复了变量 {{{{{var}}}}}")
                                    continue
                            
                            # 如果无法找到合适的位置，则添加到提示词末尾
                            self._log("WARNING", f"无法找到合适位置恢复变量 {{{{{var}}}}}，将添加到提示词末尾")
                            new_prompt = new_prompt + f"\n\n请使用 {{{{{var}}}}} 变量替换相应内容。"
                
                # 进行最终检查，确保所有变量都已恢复
                all_recovered = True
                for var in template_vars:
                    var_pattern = r'{{' + re.escape(var) + r'}}'
                    if not re.search(var_pattern, new_prompt):
                        all_recovered = False
                        break
                
                if all_recovered:
                    self._log("INFO", "成功恢复所有模板变量")
                else:
                    self._log("WARNING", "部分模板变量可能未正确恢复，请检查优化后的提示词")
                    
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
__all__ = ['AutomaticPromptOptimizer']