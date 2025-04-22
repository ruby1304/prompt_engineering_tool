# ui/components/cards.py
import streamlit as st

def info_card(title, content, key_prefix=""):
    """信息卡片组件
    
    Args:
        title: 卡片标题
        content: 卡片内容（可以是文本或HTML）
        key_prefix: 组件键前缀
    """
    with st.container(border=True):
        st.subheader(title)
        st.markdown(content)

def result_card(label, value, description=None, delta=None, key_prefix=""):
    """结果卡片组件，用于展示单一指标
    
    Args:
        label: 指标名称
        value: 指标值
        description: 额外描述信息
        delta: 变化值，用于st.metric的delta参数
        key_prefix: 组件键前缀（目前不使用）
    """
    # 移除 key 参数
    st.metric(label=label, value=value, delta=delta)
    if description:
        st.caption(description)

def template_card(template, show_variables=True, key_prefix=""):
    """模板卡片组件
    
    Args:
        template: 模板数据字典
        show_variables: 是否显示变量
        key_prefix: 组件键前缀
    """
    with st.container(border=True):
        st.subheader(template.get("name", "未命名模板"))
        st.markdown(f"**描述**: {template.get('description', '无描述')}")
        
        st.markdown("**模板内容**:")
        st.code(template.get("template", ""), language="markdown")
        
        if show_variables and template.get("variables"):
            st.markdown("**变量列表**:")
            for var_name, var_config in template.get("variables", {}).items():
                st.markdown(f"- **{var_name}**: {var_config.get('description', '')}")

def display_test_summary(test_results, key_prefix=""):
    """测试结果摘要卡片
    
    Args:
        test_results: 测试结果数据
        key_prefix: 组件键前缀
    """
    if not test_results:
        st.info("无测试结果数据")
        return
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.metric("测试用例数", len(test_results.get("test_cases", [])))
    
    with col2:
        avg_score = 0
        case_count = 0
        for case in test_results.get("test_cases", []):
            if case.get("evaluation") and "overall_score" in case["evaluation"]:
                avg_score += case["evaluation"]["overall_score"]
                case_count += 1
        
        if case_count > 0:
            avg_score /= case_count
            st.metric("平均得分", f"{avg_score:.2f}")
        else:
            st.metric("平均得分", "N/A")
    
    with col3:
        total_responses = 0
        for case in test_results.get("test_cases", []):
            total_responses += len(case.get("responses", []))
        
        st.metric("响应数", total_responses)

def display_evaluation_results(evaluation, key_prefix=""):
    """展示评估结果
    
    Args:
        evaluation: 评估结果字典
        key_prefix: 组件键前缀
    """
    if not evaluation:
        st.info("无评估结果")
        return
    
    col1, col2 = st.columns(2)
    with col1:
        st.subheader("总体评分")
        st.metric("整体得分", f"{evaluation.get('overall_score', 0):.2f}")
    
    with col2:
        st.subheader("维度评分")
        scores = evaluation.get("scores", {})
        for score_name, score_value in scores.items():
            st.metric(score_name, f"{score_value:.2f}")
    
    # 显示评估反馈
    st.subheader("评估反馈")
    st.markdown(evaluation.get("feedback", "无评估反馈"))

def display_test_case_details(test_case, key_prefix=""):
    """展示测试用例详情
    
    Args:
        test_case: 测试用例数据
        key_prefix: 组件键前缀
    """
    if not test_case:
        st.info("无测试用例数据")
        return
    
    st.subheader(f"测试用例: {test_case.get('description', '未命名用例')}")
    
    # 显示用例描述
    st.markdown(f"**ID**: {test_case.get('id', 'unknown')}")
    st.markdown(f"**描述**: {test_case.get('description', '无描述')}")
    
    # 显示用户输入
    if "user_input" in test_case:
        st.markdown("**用户输入**:")
        st.code(test_case["user_input"], language="markdown")
    
    # 显示期望输出
    if "expected_output" in test_case:
        st.markdown("**期望输出**:")
        st.code(test_case["expected_output"], language="markdown")
    
    # 显示评估标准
    if "evaluation_criteria" in test_case:
        st.markdown("**评估标准**:")
        for criterion, description in test_case["evaluation_criteria"].items():
            st.markdown(f"- **{criterion}**: {description}")

def display_response_tabs(responses, key_prefix=""):
    """展示响应标签页
    
    Args:
        responses: 响应数据列表
        key_prefix: 组件键前缀
    """
    if not responses:
        st.info("无响应数据")
        return
    
    # 创建响应选项卡
    tab_names = []
    for i, resp in enumerate(responses):
        model_name = resp.get("model", "unknown")
        run_index = resp.get("run_index", None)
        if run_index is not None:
            tab_name = f"响应 {i+1} ({model_name}, 运行 {run_index})"
        else:
            tab_name = f"响应 {i+1} ({model_name})"
        tab_names.append(tab_name)
    
    tabs = st.tabs(tab_names)
    
    # 在每个选项卡中显示响应内容
    for i, (tab, response) in enumerate(zip(tabs, responses)):
        with tab:
            st.markdown(f"**模型**: {response.get('model', '未知')}")
            st.markdown(f"**模板**: {response.get('template', '未知')}")
            
            # 显示运行次数（如果有）
            if "run_index" in response:
                st.markdown(f"**运行**: {response.get('run_index')}")
            
            st.markdown(f"**时间**: {response.get('timestamp', '未知')}")
            
            # 显示响应内容
            st.markdown("**响应内容**:")
            st.code(response.get("content", ""), language="markdown")
            
            # 显示token计数
            if "tokens" in response:
                col1, col2, col3 = st.columns(3)
                with col1:
                    st.metric("输入Token", response["tokens"].get("prompt", 0))
                with col2:
                    st.metric("输出Token", response["tokens"].get("completion", 0))
                with col3:
                    st.metric("总Token", response["tokens"].get("total", 0))
            
            # 显示评估结果
            if "evaluation" in response:
                st.markdown("---")
                st.subheader("评估结果")
                display_evaluation_results(response["evaluation"], f"{key_prefix}_resp_{i}")

