import asyncio
from typing import Dict, Any, Callable, Optional

from models.api_clients import get_client
from utils.common import render_prompt_template, regenerate_expected_output
from utils.evaluator import PromptEvaluator
# Import new utility functions and constants
from utils.constants import DEFAULT_GENERATION_PARAMS
from utils.helpers import parse_json_response, ensure_test_case_fields, ProgressTracker


def generate_ai_expected_output(
    case: Dict[str, Any], 
    model: str, 
    provider: str, 
    template: Dict[str, Any], 
    temperature: float = 0.7, 
    batch_mode: bool = False, 
    progress_callback: Optional[Callable] = None
) -> Dict[str, Any]:
    """统一处理AI生成期望输出的函数，支持单个和批量模式
    
    Args:
        case: 测试用例字典
        model: 模型名称
        provider: 提供商名称
        template: 提示词模板
        temperature: 温度参数，默认为0.7
        batch_mode: 是否为批量模式，默认为False
        progress_callback: 进度回调函数，默认为None
        
    Returns:
        包含生成结果的字典
    """
    # 检查用例是否有用户输入
    user_input = case.get("user_input", "")
    if not user_input:
        return {"error": "测试用例必须有用户输入才能生成期望输出"}
    
    if batch_mode:
        # 批量模式使用异步API直接调用
        try:
            # 创建一个新的事件循环
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
            # 获取客户端
            client = get_client(provider)
            
            # 渲染模板
            test_set = {"variables": {}}  # 创建一个空的测试集，用于提供变量结构
            prompt_template = render_prompt_template(template, test_set, case)
            
            # 使用默认参数，但覆盖温度
            params = dict(DEFAULT_GENERATION_PARAMS)
            params["temperature"] = temperature
            
            # 调用模型
            if provider in ["openai", "xai"]:
                response = loop.run_until_complete(client.generate_with_messages(
                    [
                        {"role": "system", "content": prompt_template},
                        {"role": "user", "content": user_input}
                    ],
                    model,
                    params
                ))
            else:
                combined_prompt = f"System: {prompt_template}\n\nUser: {user_input}"
                response = loop.run_until_complete(client.generate(
                    combined_prompt,
                    model,
                    params
                ))
            
            # 关闭循环
            loop.close()
            
            # 获取生成的文本
            model_output = response.get("text", "")
            
            # 返回结果
            return {
                "text": model_output,
                "usage": response.get("usage", {}),
                "error": None if model_output else "模型返回的输出为空"
            }
            
        except Exception as e:
            return {"error": f"生成期望输出时出错: {str(e)}"}
    else:
        # 单个模式使用现有的regenerate_expected_output函数
        return regenerate_expected_output(
            case=case,
            template=template,
            model=model,
            provider=provider,
            temperature=temperature
        )


async def generate_user_inputs(test_purpose: str, count: int = 5) -> Dict[str, Any]:
    """根据测试目的生成多个用户输入
    
    Args:
        test_purpose: 测试的目的或主题
        count: 要生成的输入数量
        
    Returns:
        包含生成的用户输入列表的字典
    """
    try:
        evaluator = PromptEvaluator()
        
        # 构建系统提示词
        system_prompt = f"""你是一个测试输入生成器。请为以下测试目的生成{count}个不同的、高质量的用户输入测试案例。
测试目的: {test_purpose}

生成的输入应该:
1. 多样化，覆盖不同场景
2. 包括一些极端或边界情况
3. 每个输入长度适中，不超过100字
4. 仅提供用户输入，不要包含期望输出

请以JSON格式返回，格式如下:
{{
  "user_inputs": [
    "用户输入1",
    "用户输入2",
    ...
  ]
}}"""

        # 调用evaluator模型生成输入
        result = await evaluator.client.generate_with_messages(
            [{"role": "system", "content": system_prompt}],
            evaluator.evaluator_model,
            {"temperature": 0.7, "max_tokens": 1000}
        )
        
        response_text = result.get("text", "")
        
        # 使用通用JSON解析函数解析响应
        parsed_data, error = parse_json_response(response_text)
        
        if error:
            return {
                "error": f"无法解析生成的JSON响应: {error}",
                "raw_response": response_text
            }
            
        # 提取user_inputs字段
        if isinstance(parsed_data, dict) and "user_inputs" in parsed_data:
            return {"user_inputs": parsed_data["user_inputs"]}
        elif isinstance(parsed_data, list):
            return {"user_inputs": parsed_data}
        else:
            return {"error": "响应格式不正确，无法提取用户输入"}
                
    except Exception as e:
        return {"error": f"生成用户输入时出错: {str(e)}"}


def batch_generate_expected_outputs(
    test_set: Dict[str, Any],
    model: str, 
    provider: str,
    template: Dict[str, Any],
    temperature: float = 0.7,
    progress_callback: Optional[Callable] = None
) -> Dict[str, Any]:
    """批量为测试集中的测试用例生成期望输出
    
    Args:
        test_set: 测试集字典
        model: 模型名称
        provider: 提供商名称
        template: 提示词模板
        temperature: 温度参数，默认为0.7
        progress_callback: 进度回调函数，默认为None
        
    Returns:
        包含操作结果的字典
    """
    # 找出所有需要生成期望输出的测试用例（有用户输入但没有期望输出）
    cases_to_fill = [
        case for case in test_set.get("cases", []) 
        if case.get("user_input") and not case.get("expected_output")
    ]
    
    if not cases_to_fill:
        return {"status": "warning", "message": "没有找到需要生成预期输出的测试用例"}
    
    # 使用统一的进度跟踪器来管理进度
    if progress_callback:
        progress_tracker = ProgressTracker(
            total_steps=len(cases_to_fill),
            callback=lambda current, total, desc: progress_callback(current, total),
            description="生成期望输出"
        )
    else:
        progress_tracker = None
    
    processed_count = 0
    success_count = 0
    errors = []
    
    # 处理每个测试用例
    for i, case in enumerate(cases_to_fill):
        # 使用统一的AI生成函数
        result = generate_ai_expected_output(
            case=case,
            model=model,
            provider=provider,
            template=template,
            temperature=temperature,
            batch_mode=True
        )
        
        processed_count += 1
        
        # 更新进度
        if progress_tracker:
            progress_tracker.update(1)
        
        if "error" in result and result["error"]:
            errors.append({
                "case_id": case.get("id"),
                "error": result["error"]
            })
            continue
        
        model_output = result.get("text", "")
        if model_output:
            # 更新测试用例
            for test_case in test_set["cases"]:
                if test_case.get("id") == case.get("id"):
                    test_case["expected_output"] = model_output
                    success_count += 1
                    break
    
    # 确保最终进度为100%
    if progress_tracker:
        progress_tracker.complete()
    
    return {
        "status": "success" if success_count > 0 else "error",
        "message": f"成功为 {success_count} 个测试用例生成预期输出",
        "total": len(cases_to_fill),
        "success": success_count,
        "errors": errors if errors else None
    }


def generate_test_cases_for_prompt(
    template: Dict[str, Any],
    test_purpose: str, 
    model: str, 
    provider: str,
    count: int = 5,
    progress_callback: Optional[Callable] = None
) -> Dict[str, Any]:
    """为特定提示词模板生成完整的测试用例（包括用户输入和预期输出）
    
    Args:
        template: 提示词模板
        test_purpose: 测试目的
        model: 模型名称
        provider: 提供商名称
        count: 要生成的测试用例数量
        progress_callback: 进度回调函数
    
    Returns:
        包含生成的测试用例的字典
    """
    try:
        # 创建进度跟踪器
        total_steps = 2  # 两个主要步骤：生成输入和生成输出
        
        if progress_callback:
            progress_tracker = ProgressTracker(
                total_steps=total_steps,
                callback=lambda current, total, desc: progress_callback(
                    int((current / total) * 100),  # 转换为百分比
                    desc
                ),
                description="初始化"
            )
        else:
            progress_tracker = None
            
        # 步骤1：生成用户输入
        if progress_tracker:
            progress_tracker.update(0, "正在生成用户输入...")
            
        # 创建一个新的事件循环
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        # 生成用户输入
        inputs_result = loop.run_until_complete(generate_user_inputs(test_purpose, count))
        
        if "error" in inputs_result:
            if progress_tracker:
                progress_tracker.complete("生成失败")
            return {
                "status": "error",
                "message": f"生成用户输入失败: {inputs_result.get('error')}",
                "test_cases": []
            }
            
        user_inputs = inputs_result.get("user_inputs", [])
        if not user_inputs:
            if progress_tracker:
                progress_tracker.complete("生成失败")
            return {
                "status": "error",
                "message": "未能生成任何用户输入",
                "test_cases": []
            }
            
        # 步骤2：为每个用户输入生成测试用例并生成预期输出
        if progress_tracker:
            progress_tracker.update(1, "正在生成预期输出...")
            
        # 创建测试用例
        test_cases = []
        for idx, user_input in enumerate(user_inputs[:count]):  # 确保不超过请求的数量
            # 创建基础测试用例
            test_case = {
                "description": f"测试用例 {idx+1}: {test_purpose[:30]}...",
                "user_input": user_input,
            }
            
            # 使用辅助函数确保所有必要字段
            test_case = ensure_test_case_fields(test_case)
            test_cases.append(test_case)
        
        # 创建临时测试集
        temp_test_set = {
            "name": f"自动生成的测试集: {test_purpose}",
            "description": f"基于测试目的 '{test_purpose}' 自动生成的测试集",
            "variables": {},
            "cases": test_cases
        }
        
        # 生成预期输出
        output_result = batch_generate_expected_outputs(
            test_set=temp_test_set,
            model=model,
            provider=provider,
            template=template,
            progress_callback=None  # 我们在最外层已经有了进度跟踪
        )
        
        # 更新进度
        if progress_tracker:
            progress_tracker.complete("生成完成")
            
        # 返回结果
        return {
            "status": "success" if output_result.get("success", 0) > 0 else "error",
            "message": f"成功生成了 {output_result.get('success', 0)} 个完整测试用例",
            "test_cases": temp_test_set.get("cases", []),
            "errors": output_result.get("errors", [])
        }
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        
        # 确保进度完成
        if progress_tracker:
            progress_tracker.complete("生成失败")
            
        return {
            "status": "error",
            "message": f"生成测试用例时发生错误: {str(e)}",
            "test_cases": []
        }