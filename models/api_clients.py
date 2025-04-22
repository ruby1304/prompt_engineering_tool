import os
import openai
import anthropic
import google.generativeai as genai
import requests
import json
import asyncio
from typing import Dict, List, Optional, Any

from config import get_api_key, load_provider_config, load_config

class BaseAPIClient:
    """API客户端基类"""
    def __init__(self):
        self.setup_credentials()
    
    def setup_credentials(self):
        pass
    
    async def generate(self, prompt: str, model: str, params: Dict) -> Dict:
        raise NotImplementedError("API客户端必须实现generate方法")
    
    async def generate_with_messages(self, messages: List[Dict], model: str, params: Dict) -> Dict:
        """使用消息格式生成内容"""
        # 默认实现是将消息转换为单一提示词并调用generate方法
        combined_prompt = ""
        for message in messages:
            role = message.get("role", "")
            content = message.get("content", "")
            combined_prompt += f"{role.capitalize()}: {content}\n\n"
        
        return await self.generate(combined_prompt.strip(), model, params)

class OpenAIClient(BaseAPIClient):
    """OpenAI API客户端"""
    def setup_credentials(self):
        openai.api_key = get_api_key("openai")
    
    async def generate(self, prompt: str, model: str, params: Dict) -> Dict:
        try:
            response = await openai.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": "You are a helpful assistant."},
                    {"role": "user", "content": prompt}
                ],
                temperature=params.get("temperature", 0.7),
                max_tokens=params.get("max_tokens", 1000),
                top_p=params.get("top_p", 1.0)
            )
            
            return {
                "text": response.choices[0].message.content,
                "model": model,
                "usage": {
                    "prompt_tokens": response.usage.prompt_tokens,
                    "completion_tokens": response.usage.completion_tokens,
                    "total_tokens": response.usage.total_tokens
                }
            }
        except Exception as e:
            return {
                "error": str(e),
                "model": model
            }

    async def generate_with_messages(self, messages: List[Dict], model: str, params: Dict) -> Dict:
        try:
            response = await openai.chat.completions.create(
                model=model,
                messages=messages,
                temperature=params.get("temperature", 0.7),
                max_tokens=params.get("max_tokens", 1000),
                top_p=params.get("top_p", 1.0)
            )
            
            return {
                "text": response.choices[0].message.content,
                "model": model,
                "usage": {
                    "prompt_tokens": response.usage.prompt_tokens,
                    "completion_tokens": response.usage.completion_tokens,
                    "total_tokens": response.usage.total_tokens
                }
            }
        except Exception as e:
            return {
                "error": str(e),
                "model": model
            }

class AnthropicClient(BaseAPIClient):
    """Anthropic API客户端"""
    def setup_credentials(self):
        self.client = anthropic.Anthropic(api_key=get_api_key("anthropic"))
    
    async def generate(self, prompt: str, model: str, params: Dict) -> Dict:
        try:
            response = await self.client.messages.create(
                model=model,
                messages=[
                    {"role": "user", "content": prompt}
                ],
                max_tokens=params.get("max_tokens", 1000),
                temperature=params.get("temperature", 0.7),
            )
            
            return {
                "text": response.content[0].text,
                "model": model,
                "usage": {
                    "input_tokens": response.usage.input_tokens,
                    "output_tokens": response.usage.output_tokens,
                    "total_tokens": response.usage.input_tokens + response.usage.output_tokens
                }
            }
        except Exception as e:
            return {
                "error": str(e),
                "model": model
            }

class GoogleClient(BaseAPIClient):
    """Google Gemini API客户端"""
    def setup_credentials(self):
        genai.configure(api_key=get_api_key("google"))
    
    async def generate(self, prompt: str, model: str, params: Dict) -> Dict:
        try:
            gemini_model = genai.GenerativeModel(
                model_name=model,
                generation_config={
                    "temperature": params.get("temperature", 0.7),
                    "top_p": params.get("top_p", 1.0),
                    "max_output_tokens": params.get("max_tokens", 1000),
                }
            )
            
            response = await gemini_model.generate_content_async(prompt)
            
            # Google API不直接提供token使用量，我们估计一下
            from ..models.token_counter import count_tokens
            prompt_tokens = count_tokens(prompt, model)
            completion_tokens = count_tokens(response.text, model)
            
            return {
                "text": response.text,
                "model": model,
                "usage": {
                    "prompt_tokens": prompt_tokens,
                    "completion_tokens": completion_tokens,
                    "total_tokens": prompt_tokens + completion_tokens
                }
            }
        except Exception as e:
            return {
                "error": str(e),
                "model": model
            }

class GenericHTTPClient(BaseAPIClient):
    """通用HTTP API客户端，支持自定义API端点和参数"""
    
    def __init__(self, provider_name):
        self.provider_name = provider_name
        super().__init__()
    
    def setup_credentials(self):
        # 加载提供商配置
        self.config = load_provider_config(self.provider_name)
        self.api_key = self.config.get("api_key", "")
        self.base_url = self.config.get("base_url", "")
        self.message_format = self.config.get("message_format", "openai")
        
        # 确保基础URL没有尾部斜杠
        if self.base_url and self.base_url.endswith("/"):
            self.base_url = self.base_url[:-1]
    
    async def generate(self, prompt: str, model: str, params: Dict) -> Dict:
        """使用普通文本形式生成内容"""
        if self.message_format == "openai":
            # 如果提供商使用OpenAI格式，将普通文本转换为消息格式
            messages = [
                {"role": "user", "content": prompt}
            ]
            return await self.generate_with_messages(messages, model, params)
        
        try:
            # 创建请求会话
            session = requests.Session()
            
            # 准备请求数据 - 使用参数映射
            mapping = self.config.get("params_mapping", {})
            data = {}
            
            # 添加模型
            if "model" in mapping:
                data[mapping["model"]] = model
            
            # 添加文本内容
            if "content" in mapping:
                data[mapping["content"]] = prompt
            elif "prompt" in mapping:
                data[mapping["prompt"]] = prompt
            else:
                # 默认使用prompt字段
                data["prompt"] = prompt
            
            # 添加其他参数
            for param_name, param_value in params.items():
                if param_name in mapping:
                    data[mapping[param_name]] = param_value
            
            # 准备请求头
            headers = dict(self.config.get("headers", {}))
            # 替换API密钥占位符
            for key, value in headers.items():
                if isinstance(value, str) and "{api_key}" in value:
                    headers[key] = value.replace("{api_key}", self.api_key)
            
            # 获取聊天完成端点
            endpoint = self.config.get("endpoints", {}).get("chat", "/completions")
            url = f"{self.base_url}{endpoint}"
            
            # 使用线程池执行同步请求
            loop = asyncio.get_running_loop()
            response = await loop.run_in_executor(
                None,
                lambda: session.post(
                    url,
                    json=data,
                    headers=headers
                )
            )
            
            # 检查响应
            response.raise_for_status()
            result = response.json()
            
            # 解析响应 - 尝试遵循通用格式
            response_text = ""
            if "choices" in result and len(result["choices"]) > 0:
                if "text" in result["choices"][0]:
                    response_text = result["choices"][0]["text"]
                elif "message" in result["choices"][0]:
                    if "content" in result["choices"][0]["message"]:
                        response_text = result["choices"][0]["message"]["content"]
            elif "output" in result:
                response_text = result["output"]
            elif "response" in result:
                response_text = result["response"]
            elif "text" in result:
                response_text = result["text"]
            
            # 提取使用量信息
            usage = result.get("usage", {})
            if not usage:
                # 尝试估算token数
                from models.token_counter import count_tokens
                prompt_tokens = count_tokens(prompt)
                completion_tokens = count_tokens(response_text)
                usage = {
                    "prompt_tokens": prompt_tokens,
                    "completion_tokens": completion_tokens,
                    "total_tokens": prompt_tokens + completion_tokens
                }
            
            # 构造结果格式
            return {
                "text": response_text,
                "model": model,
                "usage": usage
            }
        except Exception as e:
            return {
                "error": str(e),
                "model": model
            }
    
    async def generate_with_messages(self, messages: List[Dict], model: str, params: Dict) -> Dict:
        """使用消息格式生成内容"""
        if self.message_format != "openai":
            # 如果提供商不使用OpenAI格式，将消息转换为文本
            combined_text = ""
            for message in messages:
                role = message.get("role", "")
                content = message.get("content", "")
                combined_text += f"{role.capitalize()}: {content}\n\n"
            
            return await self.generate(combined_text.strip(), model, params)
        
        try:
            # 创建请求会话
            session = requests.Session()
            
            # 准备请求数据 - 使用参数映射
            mapping = self.config.get("params_mapping", {})
            data = {}
            
            # 添加模型
            if "model" in mapping:
                data[mapping["model"]] = model
            
            # 添加消息
            if "messages" in mapping:
                data[mapping["messages"]] = messages
            
            # 添加其他参数
            for param_name, param_value in params.items():
                if param_name in mapping:
                    data[mapping[param_name]] = param_value
            
            # 准备请求头
            headers = dict(self.config.get("headers", {}))
            # 替换API密钥占位符
            for key, value in headers.items():
                if isinstance(value, str) and "{api_key}" in value:
                    headers[key] = value.replace("{api_key}", self.api_key)
            
            # 获取聊天完成端点
            endpoint = self.config.get("endpoints", {}).get("chat", "/completions")
            url = f"{self.base_url}{endpoint}"
            
            # 使用线程池执行同步请求
            loop = asyncio.get_running_loop()
            response = await loop.run_in_executor(
                None,
                lambda: session.post(
                    url,
                    json=data,
                    headers=headers
                )
            )
            
            # 检查响应
            response.raise_for_status()
            result = response.json()
            
            # 解析响应 - 尝试遵循OpenAI格式
            response_text = ""
            if "choices" in result and len(result["choices"]) > 0:
                if "message" in result["choices"][0]:
                    if "content" in result["choices"][0]["message"]:
                        response_text = result["choices"][0]["message"]["content"]
            
            # 提取使用量信息
            usage = result.get("usage", {})
            if not usage:
                # 尝试估算token数
                from models.token_counter import count_tokens
                
                # 计算输入token
                prompt_tokens = 0
                for message in messages:
                    prompt_tokens += count_tokens(message.get("content", ""))
                
                # 计算输出token
                completion_tokens = count_tokens(response_text)
                
                usage = {
                    "prompt_tokens": prompt_tokens,
                    "completion_tokens": completion_tokens,
                    "total_tokens": prompt_tokens + completion_tokens
                }
            
            # 构造结果格式
            return {
                "text": response_text,
                "model": model,
                "usage": usage
            }
        except Exception as e:
            return {
                "error": str(e),
                "model": model
            }

class XAIClient(BaseAPIClient):
    """XAI API客户端，使用requests实现"""
    def setup_credentials(self):
        self.api_key = get_api_key("xai")
        self.base_url = "https://api.x.ai/v1"
    
    async def generate(self, prompt: str, model: str, params: Dict) -> Dict:
        try:
            # 创建请求会话
            session = requests.Session()
            session.proxies = {}  # 禁用代理
            
            # 准备请求数据
            data = {
                "model": model,
                "messages": [
                    {"role": "system", "content": "You are a helpful assistant."},
                    {"role": "user", "content": prompt}
                ],
                "temperature": params.get("temperature", 0.7),
                "max_tokens": params.get("max_tokens", 1000),
                "top_p": params.get("top_p", 1.0)
            }
            
            # 使用线程池执行同步请求
            loop = asyncio.get_running_loop()
            response = await loop.run_in_executor(
                None,
                lambda: session.post(
                    f"{self.base_url}/chat/completions",
                    json=data,
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json"
                    }
                )
            )
            
            # 检查响应
            response.raise_for_status()
            result = response.json()
            
            # 构造结果格式
            return {
                "text": result["choices"][0]["message"]["content"],
                "model": model,
                "usage": result.get("usage", {
                    "prompt_tokens": 0,
                    "completion_tokens": 0,
                    "total_tokens": 0
                })
            }
        except Exception as e:
            return {
                "error": str(e),
                "model": model
            }

    async def generate_with_messages(self, messages: List[Dict], model: str, params: Dict) -> Dict:
        try:
            # 使用线程池执行同步请求
            session = requests.Session()
            session.proxies = {}  # 禁用代理
            
            # 准备请求数据
            data = {
                "model": model,
                "messages": messages,
                "temperature": params.get("temperature", 0.7),
                "max_tokens": params.get("max_tokens", 1000),
                "top_p": params.get("top_p", 1.0)
            }
            
            # 使用线程池执行同步请求
            loop = asyncio.get_running_loop()
            response = await loop.run_in_executor(
                None,
                lambda: session.post(
                    f"{self.base_url}/chat/completions",
                    json=data,
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json"
                    }
                )
            )
            
            # 检查响应
            response.raise_for_status()
            result = response.json()
            
            # 构造结果格式
            return {
                "text": result["choices"][0]["message"]["content"],
                "model": model,
                "usage": result.get("usage", {
                    "prompt_tokens": 0,
                    "completion_tokens": 0,
                    "total_tokens": 0
                })
            }
        except Exception as e:
            return {
                "error": str(e),
                "model": model
            }

def get_client(provider: str) -> BaseAPIClient:
    """获取指定提供商的API客户端"""
    config = load_config()
    
    # 内置提供商
    built_in_clients = {
        "openai": OpenAIClient,
        "anthropic": AnthropicClient,
        "google": GoogleClient,
        "xai": XAIClient,
    }
    
    # 检查是否为内置提供商
    if provider in built_in_clients:
        return built_in_clients[provider]()
    
    # 检查是否为自定义提供商
    if provider in config.get("custom_providers", []):
        return GenericHTTPClient(provider)
    
    raise ValueError(f"不支持的API提供商: {provider}")

def get_provider_from_model(model: str) -> str:
    """根据模型名称获取提供商"""
    config = load_config()
    
    # 检查内置提供商的模型
    for provider, models in config["models"].items():
        if model in models:
            return provider
    
    # 检查自定义提供商的模型
    for provider_name in config.get("custom_providers", []):
        provider_config = load_provider_config(provider_name)
        if model in provider_config.get("models", []):
            return provider_name
    
    # 如果找不到模型，尝试从模型名称推断提供商
    if model.startswith("gpt-"):
        return "openai"
    elif model.startswith("claude-"):
        return "anthropic"
    elif model.startswith("gemini-"):
        return "google"
    elif model.startswith("grok-"):
        return "xai"
    
    raise ValueError(f"无法确定模型的提供商: {model}")