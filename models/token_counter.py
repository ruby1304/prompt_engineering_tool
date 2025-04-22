import tiktoken
from typing import Dict, List, Optional, Any

def count_tokens(text: str, model: str = "gpt-4") -> int:
    """计算文本的token数量"""
    model_map = {
        # OpenAI models
        "gpt-3.5-turbo": "cl100k_base",
        "gpt-4": "cl100k_base",
        "gpt-4o": "cl100k_base",
        
        # Anthropic models (approximation)
        "claude-3-opus-20240229": "cl100k_base",
        "claude-3-sonnet-20240229": "cl100k_base",
        "claude-3-haiku-20240307": "cl100k_base",
        
        # Google models (approximation)
        "gemini-1.0-pro": "cl100k_base",
        "gemini-1.5-pro": "cl100k_base",


        "grok-3": "cl100k_base",
    }
    
    # 默认使用cl100k_base编码器
    encoder_name = model_map.get(model, "cl100k_base")
    encoder = tiktoken.get_encoding(encoder_name)
    
    # 编码并计数
    token_count = len(encoder.encode(text))
    return token_count

def estimate_cost(token_count: int, model: str) -> float:
    """估算API调用成本（美元）"""
    # 价格表（每1000个token的价格，分输入和输出）
    # 数据来源: https://openai.com/pricing 等官方价格，可能需要更新
    price_map = {
        # OpenAI models - [input_price, output_price] per 1K tokens
        "gpt-3.5-turbo": [0.0005, 0.0015],
        "gpt-4": [0.03, 0.06],
        "gpt-4o": [0.01, 0.03],
        
        # Anthropic models
        "claude-3-opus-20240229": [0.015, 0.075],
        "claude-3-sonnet-20240229": [0.003, 0.015],
        "claude-3-haiku-20240307": [0.00025, 0.00125],
        
        # Google models (approximation)
        "gemini-1.0-pro": [0.0025, 0.0025],  # 单一价格
        "gemini-1.5-pro": [0.0025, 0.0025],  # 单一价格


        "grok-3": [0.003, 0.015],  # 单一价格
    }
    
    # 默认使用GPT-3.5价格
    default_price = [0.0005, 0.0015]
    input_price, output_price = price_map.get(model, default_price)
    
    # 简单估算 (假设输入输出token相等)
    input_tokens = token_count // 2
    output_tokens = token_count // 2
    
    total_cost = (input_tokens / 1000 * input_price) + (output_tokens / 1000 * output_price)
    
    return total_cost