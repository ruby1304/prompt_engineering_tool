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
from utils.evaluator import PromptEvaluator


def render_prompt_interactive_test():
    """渲染提示词交互测试页面"""
    st.title("🧪 提示词交互测试")
    
    # 检查是否从自动优化页面跳转过来，需要使用临时模板
    coming_from_auto_optimization = "from_auto_optimization" in st.session_state and st.session_state.from_auto_optimization
    has_temp_template = "temp_test_template" in st.session_state and st.session_state.temp_test_template is not None
    
    if coming_from_auto_optimization and has_temp_template:
        # 使用从自动优化页面传递过来的临时模板
        template = st.session_state.temp_test_template
        model = st.session_state.temp_test_model
        provider = st.session_state.temp_test_provider
        
        st.info(f"正在测试自动优化生成的提示词: {template.get('name', '')}")
        
        # 清除这些标记，避免下次刷新页面依然使用临时模板
        st.session_state.from_auto_optimization = False
        
        # 创建返回自动优化页面的按钮
        if st.button("↩️ 返回自动优化页面"):
            st.session_state.page = "prompt_auto_optimization"
            st.rerun()
    else:
        # 正常流程，显示标准介绍
        st.markdown("""
        <div style="background-color: #f8f9fa; padding: 20px; border-radius: 10px; margin-bottom: 20px;">
        <h3 style="color: #4b778d;">在这里交互式测试提示词模板</h3>
        <p>选择提示词模板和模型，输入自定义内容，查看模型回复，将用户输入保存到测试集中。</p>
        </div>
        """, unsafe_allow_html=True)
    
    # 分成两列：左侧选择区域，右侧结果显示
    col1, col2 = st.columns([3, 5])
    
    with col1:
        # 如果不是从自动优化页面跳转过来，显示正常的模板选择界面
        if not (coming_from_auto_optimization and has_temp_template):
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
        else:
            # 如果是从自动优化页面跳转过来，显示临时模板信息
            st.subheader("优化提示词详情")
            st.write(f"**名称:** {template.get('name', '优化提示词')}")
            st.write(f"**描述:** {template.get('description', '自动优化生成的提示词')}")
            
            # 展示模板内容预览
            with st.expander("查看模板内容", expanded=True):
                st.code(template.get("template", ""))
            
            st.subheader("使用的模型")
            st.write(f"**模型:** {model} ({provider})")
        
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
        
        # 只有在普通模式下才显示目标测试集选择
        if not (coming_from_auto_optimization and has_temp_template):
            st.subheader("目标测试集")
            test_set_list = get_test_set_list()
            if not test_set_list:
                st.warning("未找到测试集，请先创建测试集")
                selected_test_set = None
            else:
                selected_test_set = st.selectbox(
                    "选择测试集",
                    options=test_set_list,
                    help="选择要将用户输入添加到的测试集"
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
        else:
            # 从自动优化页面跳转过来时不需要选择测试集
            selected_test_set = None
        
        # 运行测试按钮
        run_btn = st.button("▶️ 运行测试", type="primary")
    
    with col2:
        st.subheader("测试结果")
        
        # 第一次访问页面时初始化会话状态
        if "test_results" not in st.session_state:
            st.session_state.test_results = []
        if "user_input" not in st.session_state:
            st.session_state.user_input = ""
        if "evaluation_results" not in st.session_state:
            st.session_state.evaluation_results = {}
        
        if run_btn:
            if not user_input:
                st.error("请输入测试内容")
                return
                
            if not template:
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
                            messages = [
                                {"role": "system", "content": prompt_template},
                                {"role": "user", "content": user_input}
                            ]
                            response = loop.run_until_complete(client.generate_with_messages(
                                messages,
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
                    
                    # 保存结果到会话状态，不执行评估
                    st.session_state.test_results = [
                        {
                            "id": f"result_{i}_{int(time.time())}",  # 添加唯一ID用于后续评估
                            "template": template,
                            "model": model,
                            "user_input": user_input,
                            "prompt_template": prompt_template,
                            "model_response": result.get("model_response", ""),
                            "usage": result.get("usage", {})
                        }
                        for i, result in enumerate(results)
                    ]
                    st.session_state.user_input = user_input
                    # 清空之前的评估结果
                    st.session_state.evaluation_results = {}
                    
                except Exception as e:
                    st.error(f"测试失败: {str(e)}")
                    return
        
        # 显示测试结果
        if st.session_state.test_results:
            user_input = st.session_state.user_input
            
            # 创建一个顶部操作栏，包含保存和清除按钮
            action_col1, action_col2, action_col3 = st.columns([5, 2, 2])
            
            with action_col1:
                st.write("### 用户输入:")
                st.code(user_input)
            
            # 统一的保存用户输入按钮 - 只有非自动优化临时模板模式才显示
            if not (coming_from_auto_optimization and has_temp_template):
                with action_col2:
                    if st.button("💾 保存用户输入", use_container_width=True):
                        if not selected_test_set:
                            st.error("请选择目标测试集")
                        else:
                            # 加载测试集
                            test_set = load_test_set(selected_test_set)
                            if not test_set:
                                st.error(f"无法加载测试集 {selected_test_set}")
                            else:
                                # 创建新的测试用例，只包含用户输入，不包含模型输出
                                new_case = {
                                    "id": generate_unique_id(),
                                    "description": f"{template.get('name', '')}用户输入",
                                    "user_input": user_input,
                                    "expected_output": "",  # 不设置期望输出
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
                                
                                st.success(f"用户输入已保存到测试集 '{selected_test_set}'")
            
            # 清除结果按钮
            with action_col3:
                if st.button("🔄 清除结果", use_container_width=True):
                    # 清空测试结果
                    st.session_state.test_results = []
                    st.session_state.user_input = ""
                    st.session_state.evaluation_results = {}
                    st.experimental_rerun()
            
            # 使用选项卡展示多个模型回复，提高布局效率
            if len(st.session_state.test_results) > 1:
                tabs = st.tabs([f"回复 {i+1}" for i in range(len(st.session_state.test_results))])
                for i, (tab, result) in enumerate(zip(tabs, st.session_state.test_results)):
                    result_id = result["id"]
                    
                    with tab:
                        # 模型回复
                        st.write("#### 模型回复:")
                        st.code(result["model_response"])
                        
                        # 添加独立的评估按钮
                        if st.button(f"📊 评估此响应", key=f"evaluate_{result_id}"):
                            with st.spinner("正在评估模型响应..."):
                                evaluation = evaluate_model_response(result)
                                st.session_state.evaluation_results[result_id] = evaluation
                                st.experimental_rerun()  # 重新加载以显示评估结果
                        
                        # 如果有评估结果，显示评估结果
                        if result_id in st.session_state.evaluation_results:
                            display_evaluation_result(st.session_state.evaluation_results[result_id])
                        
                        # 显示Token使用情况
                        usage = result.get("usage", {})
                        if usage:
                            with st.expander("Token 使用情况", expanded=False):
                                st.json(usage)
            else:
                # 单个结果直接显示
                result = st.session_state.test_results[0]
                result_id = result["id"]
                
                # 模型回复
                st.write("### 模型回复:")
                st.code(result["model_response"])
                
                # 添加独立的评估按钮
                if st.button(f"📊 评估此响应", key=f"evaluate_{result_id}"):
                    with st.spinner("正在评估模型响应..."):
                        evaluation = evaluate_model_response(result)
                        st.session_state.evaluation_results[result_id] = evaluation
                        st.experimental_rerun()  # 重新加载以显示评估结果
                
                # 如果有评估结果，显示评估结果
                if result_id in st.session_state.evaluation_results:
                    display_evaluation_result(st.session_state.evaluation_results[result_id])
                
                # 显示Token使用情况
                usage = result.get("usage", {})
                if usage:
                    with st.expander("Token 使用情况", expanded=False):
                        st.json(usage)
                
                # 如果是从自动优化页面跳转过来，添加反馈按钮
                if coming_from_auto_optimization and has_temp_template:
                    st.subheader("反馈")
                    user_feedback = st.text_area(
                        "您对这个优化提示词的反馈 (可选)",
                        placeholder="请输入您的反馈，例如：这个提示词效果很好，但可以在...方面改进",
                        height=100
                    )
                    
                    feedback_col1, feedback_col2 = st.columns(2)
                    with feedback_col1:
                        if st.button("👍 很好，继续使用此提示词", type="primary"):
                            st.session_state.auto_optimization_feedback = {"type": "positive", "text": user_feedback}
                            st.session_state.page = "prompt_auto_optimization"
                            st.rerun()
                    
                    with feedback_col2:
                        if st.button("👎 需要改进"):
                            st.session_state.auto_optimization_feedback = {"type": "negative", "text": user_feedback}
                            st.session_state.page = "prompt_auto_optimization"
                            st.rerun()
        else:
            st.info("运行测试以查看模型回复")


def evaluate_model_response(result: Dict) -> Dict:
    """评估模型响应与提示词的匹配程度"""
    evaluator = PromptEvaluator()
    
    # 提取所需数据
    model_response = result.get("model_response", "")
    prompt_template = result.get("prompt_template", "")
    user_input = result.get("user_input", "")
    
    # 评估标准
    evaluation_criteria = {
        "accuracy": "模型响应是否准确满足用户需求",
        "completeness": "模型响应是否完整回答了用户问题",
        "relevance": "模型响应是否与用户问题相关",
        "clarity": "模型响应是否清晰易懂",
        "instruction_following": "模型是否遵循了提示词中的指令"
    }
    
    # 创建一个期望输出，用于评估
    # 在交互式测试中我们没有实际的期望输出，所以使用一个通用说明
    expected_output = "根据提示词要求，给出恰当的回答"
    
    # 执行评估
    return evaluator.evaluate_response_sync(
        model_response,
        expected_output,
        evaluation_criteria,
        prompt_template + "\n用户: " + user_input
    )


def display_evaluation_result(evaluation: Dict):
    """展示评估结果"""
    st.write("#### 响应评估结果:")
    
    # 如果有错误信息，显示错误
    if "error" in evaluation:
        st.warning(f"评估过程遇到问题: {evaluation.get('error')}")
        return
    
    # 显示分数
    if "scores" in evaluation:
        scores = evaluation["scores"]
        
        # 创建两行评分，每行显示三个指标
        row1_cols = st.columns(3)
        with row1_cols[0]:
            st.metric("准确性", f"{scores.get('accuracy', 0)}分")
        with row1_cols[1]:
            st.metric("完整性", f"{scores.get('completeness', 0)}分")
        with row1_cols[2]:
            st.metric("相关性", f"{scores.get('relevance', 0)}分")
        
        row2_cols = st.columns(3)
        with row2_cols[0]:
            st.metric("清晰度", f"{scores.get('clarity', 0)}分")
        with row2_cols[1]:
            st.metric("指令遵循", f"{scores.get('instruction_following', 0)}分")
        with row2_cols[2]:
            st.metric("总体评分", f"{evaluation.get('overall_score', 0)}分")
        
        # 显示评估总结
        if "summary" in evaluation:
            st.write("**评估总结:**")
            st.info(evaluation["summary"])
        
        # 详细分析
        if "analysis" in evaluation:
            with st.expander("查看详细分析", expanded=False):
                st.write(evaluation["analysis"])