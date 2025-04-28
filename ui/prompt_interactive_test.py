import streamlit as st
import json
import time
from typing import Dict, Any, List, Optional
import asyncio

from config import load_template, get_template_list, load_test_set, get_test_set_list, save_test_set
from utils.test_set_manager import generate_unique_id, add_test_case
from utils.common import render_prompt_template
from models.api_clients import get_provider_from_model, get_client
from ui.components import select_single_model
from utils.parallel_executor import execute_models_sync


def render_prompt_interactive_test():
    """渲染提示词交互测试页面"""
    st.title("🧪 提示词交互测试")
    
    st.markdown("""
    <div style="background-color: #f8f9fa; padding: 20px; border-radius: 10px; margin-bottom: 20px;">
    <h3 style="color: #4b778d;">在这里交互式测试提示词模板</h3>
    <p>选择提示词模板和模型，输入自定义内容，查看模型回复，将满意的测试案例保存到测试集中。</p>
    </div>
    """, unsafe_allow_html=True)
    
    # 分成两列：左侧选择区域，右侧结果显示
    col1, col2 = st.columns([3, 5])
    
    with col1:
        st.subheader("选择提示词模板")
        # 获取模板列表
        template_list = get_template_list()
        if not template_list:
            st.warning("未找到提示词模板，请先创建模板")
            return
            
        # 选择模板
        selected_template_name = st.selectbox(
            "选择模板",
            options=template_list,
            help="选择要测试的提示词模板"
        )
        
        # 加载模板
        if selected_template_name:
            template = load_template(selected_template_name)
            if template:
                st.success(f"已加载模板: {selected_template_name}")
                st.write(f"**描述:** {template.get('description', '无描述')}")
                
                # 展示模板内容预览
                with st.expander("查看模板内容", expanded=False):
                    st.code(template.get("template", ""))
            else:
                st.error(f"无法加载模板 {selected_template_name}")
                return
        
        st.subheader("选择模型")
        # 使用组件选择单个模型
        model, provider = select_single_model(key_prefix="interactive_test", help_text="选择用于测试的模型")
        
        if not model:
            st.warning("请选择一个模型")
            return
            
        st.subheader("测试参数")
        temperature = st.slider("Temperature", 0.0, 2.0, 0.7, 0.1, 
                              help="控制生成文本的随机性。较高的值会产生更多样化但可能不一致的输出")
        
        # 添加测试次数选择
        test_count = st.number_input(
            "测试次数", 
            min_value=1, 
            max_value=10, 
            value=1, 
            step=1,
            help="选择要执行的测试次数，可以使用并行调用进行多次测试"
        )
        
        # 添加是否使用并行调用的选项
        use_parallel = st.checkbox("使用并行调用", value=True, help="并行执行多次测试以提高效率")
        
        # 添加用户输入区域
        st.subheader("用户输入")
        user_input = st.text_area(
            "在这里输入您的测试内容",
            height=200,
            help="输入您想要测试的内容"
        )
        
        # 目标测试集选择
        st.subheader("目标测试集")
        test_set_list = get_test_set_list()
        if not test_set_list:
            st.warning("未找到测试集，请先创建测试集")
            selected_test_set = None
        else:
            selected_test_set = st.selectbox(
                "选择测试集",
                options=test_set_list,
                help="选择要将成功案例添加到的测试集"
            )
            
            if selected_test_set:
                test_set = load_test_set(selected_test_set)
                if test_set:
                    st.success(f"已加载测试集: {selected_test_set}")
                    with st.expander("测试集信息", expanded=False):
                        st.write(f"**描述:** {test_set.get('description', '无描述')}")
                        st.write(f"**案例数量:** {len(test_set.get('cases', []))}")
                else:
                    st.error(f"无法加载测试集 {selected_test_set}")
                    return
        
        # 运行测试按钮
        run_btn = st.button("▶️ 运行测试", type="primary")
    
    with col2:
        st.subheader("测试结果")
        
        # 第一次访问页面时初始化会话状态
        if "test_results" not in st.session_state:
            st.session_state.test_results = []
        if "user_input" not in st.session_state:
            st.session_state.user_input = ""
        
        if run_btn:
            if not user_input:
                st.error("请输入测试内容")
                return
                
            if not selected_template_name or not template:
                st.error("请选择提示词模板")
                return
                
            if not model:
                st.error("请选择模型")
                return
                
            with st.spinner(f"正在使用 {model} 进行 {test_count} 次测试" + ("（并行执行）" if use_parallel else "")):
                try:
                    # 渲染提示词模板
                    prompt_template = render_prompt_template(template, {"variables": {}}, {"variables": {}})
                    
                    # 设置参数
                    params = {"temperature": temperature, "max_tokens": 1000}
                    
                    if test_count == 1 or not use_parallel:
                        # 单次测试或串行执行多次测试
                        results = []
                        for i in range(test_count):
                            # 创建事件循环
                            loop = asyncio.new_event_loop()
                            asyncio.set_event_loop(loop)
                            
                            # 获取API客户端
                            client = get_client(provider)
                            
                            # 调用模型
                            if provider in ["openai", "xai"]:
                                messages = [
                                    {"role": "system", "content": prompt_template},
                                    {"role": "user", "content": user_input}
                                ]
                                response = loop.run_until_complete(client.generate_with_messages(
                                    messages,
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
                            
                            # 保存结果
                            if "error" in response and response["error"]:
                                results.append({
                                    "error": response["error"],
                                    "model_response": f"错误：{response['error']}"
                                })
                            else:
                                results.append({
                                    "model_response": response.get("text", ""),
                                    "usage": response.get("usage", {})
                                })
                    else:
                        # 并行执行多次测试
                        # 准备多个请求
                        requests = []
                        for i in range(test_count):
                            if provider in ["openai", "xai"]:
                                messages = [
                                    {"role": "system", "content": prompt_template},
                                    {"role": "user", "content": user_input}
                                ]
                                requests.append({
                                    "model": model,
                                    "messages": messages,
                                    "provider": provider,
                                    "params": params
                                })
                            else:
                                combined_prompt = f"System: {prompt_template}\n\nUser: {user_input}"
                                requests.append({
                                    "model": model,
                                    "prompt": combined_prompt,
                                    "provider": provider,
                                    "params": params
                                })
                        
                        # 使用并行执行器执行请求
                        responses = execute_models_sync(requests)
                        
                        # 处理所有响应
                        results = []
                        for response in responses:
                            if "error" in response and response["error"]:
                                results.append({
                                    "error": response["error"],
                                    "model_response": f"错误：{response['error']}"
                                })
                            else:
                                results.append({
                                    "model_response": response.get("text", ""),
                                    "usage": response.get("usage", {})
                                })
                    
                    # 保存结果到会话状态
                    st.session_state.test_results = [
                        {
                            "template": template,
                            "model": model,
                            "user_input": user_input,
                            "model_response": result.get("model_response", ""),
                            "usage": result.get("usage", {})
                        }
                        for result in results
                    ]
                    st.session_state.user_input = user_input
                    
                except Exception as e:
                    st.error(f"测试失败: {str(e)}")
                    return
        
        # 显示测试结果
        if st.session_state.test_results:
            user_input = st.session_state.user_input
            
            st.write("### 用户输入:")
            st.code(user_input)
            
            # 平铺显示所有结果，而不是使用选项卡
            for i, result in enumerate(st.session_state.test_results):
                st.write(f"### 模型回复 {i+1}:")
                st.code(result["model_response"])
                
                # 使用率信息
                usage = result.get("usage", {})
                if usage:
                    with st.expander(f"Token 使用情况 - 结果 {i+1}", expanded=False):
                        st.json(usage)
                
                # 为每个结果添加保存到测试集的选项
                col1, col2 = st.columns([3, 1])
                with col1:
                    case_description = st.text_input(f"测试用例描述", value=f"{selected_template_name}交互测试 {i+1}", key=f"desc_{i}")
                
                with col2:
                    if st.button(f"💾 保存此结果", key=f"save_{i}", use_container_width=True):
                        if not selected_test_set:
                            st.error("请选择目标测试集")
                            continue
                            
                        # 加载测试集
                        test_set = load_test_set(selected_test_set)
                        if not test_set:
                            st.error(f"无法加载测试集 {selected_test_set}")
                            continue
                        
                        # 创建新的测试用例
                        new_case = {
                            "id": generate_unique_id(),
                            "description": case_description,
                            "user_input": user_input,
                            "expected_output": result["model_response"],  # 使用模型响应作为期望输出
                            "evaluation_criteria": {
                                "accuracy": "评估回答的准确性",
                                "completeness": "评估回答的完整性",
                                "relevance": "评估回答的相关性",
                                "clarity": "评估回答的清晰度"
                            },
                            "variables": {},
                            "timestamp": int(time.time())
                        }
                        
                        # 添加到测试集
                        test_set = add_test_case(test_set, new_case)
                        
                        # 保存更新的测试集
                        save_test_set(selected_test_set, test_set)
                        
                        st.success(f"测试用例已成功添加到测试集 '{selected_test_set}'")
                
                # 添加分隔线（除了最后一个结果）
                if i < len(st.session_state.test_results) - 1:
                    st.markdown("---")
            
            # 清除所有结果的按钮
            if len(st.session_state.test_results) > 1:
                if st.button("🔄 清除并继续测试", use_container_width=True):
                    # 清空测试结果
                    st.session_state.test_results = []
                    st.session_state.user_input = ""
                    st.experimental_rerun()
        else:
            st.info("运行测试以查看模型回复")