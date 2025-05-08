import asyncio
from typing import List, Dict, Any, Optional, Union, Callable, Tuple
import time
import sys
from tqdm import tqdm  # 添加tqdm进度条支持

from models.api_clients import get_client, get_provider_from_model
from config import get_concurrency_limit, load_config

class ParallelModelExecutor:
    """
    并行模型执行器，用于处理多个模型API请求的并发执行
    支持批量请求、自动限制并发、错误处理和结果汇总
    """
    
    def __init__(self, concurrency_limit: Optional[int] = None, show_progress: bool = True):
        """
        初始化并行执行器
        
        Args:
            concurrency_limit: 可选的全局并发限制，如果不提供则根据模型和提供商动态确定
            show_progress: 是否在控制台显示进度条
        """
        self.global_concurrency_limit = concurrency_limit
        # 缓存客户端实例以避免重复创建
        self._client_cache = {}
        # 默认超时时间（秒）
        self.default_timeout = 180
        # 控制台进度显示选项
        self.show_progress = show_progress
        # 进度计数器
        self.completed_count = 0
        self.total_count = 0
        self.progress_bar = None
    
    def _get_client(self, provider: str):
        """获取缓存的API客户端实例"""
        if provider not in self._client_cache:
            self._client_cache[provider] = get_client(provider)
        return self._client_cache[provider]
    
    def _get_concurrency_limit(self, provider: str, model: str) -> int:
        """获取指定提供商和模型的并发限制"""
        if self.global_concurrency_limit is not None:
            return self.global_concurrency_limit
        return get_concurrency_limit(provider, model)
    
    async def execute_single(self, 
                            model: str, 
                            prompt: str = None, 
                            messages: List[Dict] = None, 
                            provider: str = None, 
                            params: Dict = None,
                            timeout: int = None) -> Dict:
        """
        执行单个模型请求
        
        Args:
            model: 模型名称
            prompt: 文本提示词（与messages二选一）
            messages: 消息格式的提示词（与prompt二选一）
            provider: 提供商名称，如果为None则自动从模型名称推断
            params: 调用参数，如temperature、max_tokens等
            timeout: 超时时间（秒）
            
        Returns:
            模型响应结果字典
        """
        if prompt is None and messages is None:
            raise ValueError("必须提供prompt或messages参数")
        
        if prompt is not None and messages is not None:
            raise ValueError("不能同时提供prompt和messages参数")
            
        # 默认参数
        if params is None:
            params = {"temperature": 0.7, "max_tokens": 1000}
            
        # 确定提供商
        if provider is None:
            provider = get_provider_from_model(model)
            
        # 获取API客户端
        client = self._get_client(provider)
        
        # 设置超时
        timeout = timeout or self.default_timeout
        
        try:
            # 创建任务并设置超时
            if messages is not None:
                task = asyncio.create_task(client.generate_with_messages(messages, model, params))
            else:
                task = asyncio.create_task(client.generate(prompt, model, params))
            
            # 等待任务完成，或超时
            response = await asyncio.wait_for(task, timeout=timeout)
            return response
            
        except asyncio.TimeoutError:
            return {
                "error": f"请求超时 (>{timeout}秒)",
                "model": model
            }
        except Exception as e:
            return {
                "error": str(e),
                "model": model
            }
    
    async def execute_batch(self, 
                          requests: List[Dict], 
                          semaphore_by_provider: bool = True,
                          progress_callback: Optional[Callable[[int, int], None]] = None) -> List[Dict]:
        """
        批量执行多个请求
        
        Args:
            requests: 请求列表，每个请求是包含model、prompt/messages等参数的字典
            semaphore_by_provider: 是否按提供商分别限制并发
            progress_callback: 进度回调函数，参数为(当前完成数, 总数)
            
        Returns:
            响应结果列表，顺序与请求列表对应
        """
        # 设置总请求数
        self.total_count = len(requests)
        self.completed_count = 0
        
        # 如果需要显示进度，创建进度条
        if self.show_progress:
            self.progress_bar = tqdm(total=self.total_count, desc="执行并行请求", file=sys.stdout)
        
        # 分组请求以便按提供商限制并发
        if semaphore_by_provider:
            # 按提供商和模型分组，为每组创建信号量
            provider_groups = {}
            
            for req in requests:
                model = req.get("model")
                provider = req.get("provider") or get_provider_from_model(model)
                
                if provider not in provider_groups:
                    provider_groups[provider] = {
                        "semaphore": {},  # 按模型分别创建信号量
                        "requests": []
                    }
                
                provider_groups[provider]["requests"].append(req)
                
                # 确保每个模型都有对应的信号量
                if model not in provider_groups[provider]["semaphore"]:
                    concurrency = self._get_concurrency_limit(provider, model)
                    provider_groups[provider]["semaphore"][model] = asyncio.Semaphore(concurrency)
            
            # 创建任务
            tasks = []
            for provider, group in provider_groups.items():
                for req in group["requests"]:
                    model = req.get("model")
                    semaphore = group["semaphore"].get(model)
                    tasks.append(self._execute_with_semaphore(semaphore, req, progress_callback))
                    
            # 执行所有任务
            results = await asyncio.gather(*tasks)
            
            # 关闭进度条
            if self.progress_bar:
                self.progress_bar.close()
                
            return results
        else:
            # 使用单一全局信号量
            concurrency = self.global_concurrency_limit or 5  # 默认全局并发为5
            semaphore = asyncio.Semaphore(concurrency)
            
            tasks = [self._execute_with_semaphore(semaphore, req, progress_callback) for req in requests]
            results = await asyncio.gather(*tasks)
            
            # 关闭进度条
            if self.progress_bar:
                self.progress_bar.close()
                
            return results
    
    async def _execute_with_semaphore(self, 
                                    semaphore: asyncio.Semaphore, 
                                    request: Dict, 
                                    progress_callback: Optional[Callable] = None) -> Dict:
        """使用信号量执行请求"""
        # 提取请求参数
        model = request.get("model")
        prompt = request.get("prompt")
        messages = request.get("messages")
        provider = request.get("provider")
        params = request.get("params", {})
        timeout = request.get("timeout", self.default_timeout)
        
        # 记录请求的上下文信息，以便返回
        context = request.get("context", {})
        
        async with semaphore:
            # 记录开始时间
            start_time = time.time()
            
            # 执行请求
            response = await self.execute_single(
                model=model,
                prompt=prompt,
                messages=messages,
                provider=provider,
                params=params,
                timeout=timeout
            )
            
            # 记录完成时间
            end_time = time.time()
            
            # 添加上下文信息和执行时间
            response["execution_time"] = end_time - start_time
            if context:
                response["context"] = context
            
            # 更新进度
            self.completed_count += 1
            
            # 更新控制台进度条
            if self.progress_bar:
                self.progress_bar.update(1)
                self.progress_bar.set_description(f"执行并行请求 [{self.completed_count}/{self.total_count}]")
            
            # 调用进度回调
            if progress_callback:
                progress_callback(self.completed_count, self.total_count)
                
            return response
    
    def execute_batch_sync(self, 
                         requests: List[Dict], 
                         semaphore_by_provider: bool = True,
                         progress_callback: Optional[Callable] = None) -> List[Dict]:
        """
        同步版本的批量执行方法，适用于在无法使用异步的环境中
        
        Args:
            requests: 请求列表，每个请求是包含model、prompt/messages等参数的字典
            semaphore_by_provider: 是否按提供商分别限制并发
            progress_callback: 进度回调函数
            
        Returns:
            响应结果列表，顺序与请求列表对应
        """
        # 创建新的事件循环
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        try:
            # 执行异步方法并等待完成
            results = loop.run_until_complete(
                self.execute_batch(requests, semaphore_by_provider, progress_callback)
            )
            return results
        finally:
            # 关闭事件循环
            loop.close()

    def execute_single_sync(self, 
                          model: str, 
                          prompt: str = None, 
                          messages: List[Dict] = None, 
                          provider: str = None, 
                          params: Dict = None,
                          timeout: int = None) -> Dict:
        """
        同步版本的单个执行方法
        
        Args:
            与execute_single参数相同
            
        Returns:
            模型响应结果字典
        """
        # 创建新的事件循环
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        try:
            # 执行异步方法并等待完成
            result = loop.run_until_complete(
                self.execute_single(model, prompt, messages, provider, params, timeout)
            )
            return result
        finally:
            # 关闭事件循环
            loop.close()

# 创建默认执行器实例，方便直接导入使用
default_executor = ParallelModelExecutor()

# 方便的函数封装，使调用更简单
async def execute_model(model: str, 
                       prompt: str = None, 
                       messages: List[Dict] = None, 
                       provider: str = None, 
                       params: Dict = None) -> Dict:
    """异步执行单个模型请求的便捷函数"""
    return await default_executor.execute_single(model, prompt, messages, provider, params)

def execute_model_sync(model: str, 
                     prompt: str = None, 
                     messages: List[Dict] = None, 
                     provider: str = None, 
                     params: Dict = None) -> Dict:
    """同步执行单个模型请求的便捷函数"""
    return default_executor.execute_single_sync(model, prompt, messages, provider, params)

async def execute_models(requests: List[Dict], 
                      progress_callback: Optional[Callable] = None) -> List[Dict]:
    """异步执行多个模型请求的便捷函数"""
    return await default_executor.execute_batch(requests, progress_callback=progress_callback)

def execute_models_sync(requests: List[Dict], 
                      progress_callback: Optional[Callable] = None) -> List[Dict]:
    """同步执行多个模型请求的便捷函数"""
    return default_executor.execute_batch_sync(requests, progress_callback=progress_callback)