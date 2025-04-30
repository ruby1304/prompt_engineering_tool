"""
常量和默认值定义模块，用于消除代码中的重复定义
"""

# 默认评估标准
DEFAULT_EVALUATION_CRITERIA = {
    "accuracy": "评估响应与期望输出的匹配程度",
    "completeness": "评估响应是否包含所有必要信息",
    "relevance": "评估响应与提示词的相关性",
    "clarity": "评估响应的清晰度和可理解性"
}

# 默认无样本评估标准
DEFAULT_NO_SAMPLE_EVALUATION_CRITERIA = {
    "relevance": "模型响应与用户提问的相关性(0-100分)",
    "helpfulness": "模型响应对解决用户问题的帮助程度(0-100分)",
    "coherence": "模型回复的连贯性和逻辑性(0-100分)",
    "prompt_following": "模型遵循提示词指令的程度(0-100分)"
}

# 默认有样本评估标准
DEFAULT_WITH_SAMPLE_EVALUATION_CRITERIA = {
    "relevance": "模型响应与用户提问的相关性(0-100分)",
    "helpfulness": "模型响应对解决用户问题的帮助程度(0-100分)",
    "accuracy": "模型响应中信息的准确性(0-100分)",
    "prompt_following": "模型遵循提示词指令的程度(0-100分)",
    "consistency": "模型回复与之前对话的一致性(0-100分)",
    "coherence": "模型回复的连贯性和逻辑性(0-100分)"
}

# 默认模型参数
DEFAULT_GENERATION_PARAMS = {
    "temperature": 0.7,
    "max_tokens": 8000
}

DEFAULT_EVALUATION_PARAMS = {
    "temperature": 0.2,
    "max_tokens": 1500
}

# JSON处理常量
JSON_CODE_BLOCK_PATTERNS = [
    ("```json", "```"),
    ("```", "```")
]