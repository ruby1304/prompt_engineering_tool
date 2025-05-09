import streamlit as st
from typing import Dict, Any, List, Optional, Callable
import json

from config import load_template, get_template_list, load_config, get_available_models
from utils.test_set_manager import get_shortened_id, ensure_unique_id
from utils.test_case_generator import generate_ai_expected_output
from utils.common import generate_evaluation_criteria


def display_test_case_card(case: Dict[str, Any], index: int, on_click: Callable) -> None:
    """显示测试用例卡片
    
    Args:
        case: 测试用例字典
        index: 测试用例在当前页的索引
        on_click: 点击查看按钮时的回调函数
    """
    case_id = case.get("id", "未知ID")
    case_desc = case.get("description", "未命名")
    
    # 计算截断的用户输入文本作为预览
    input_preview = case.get("user_input", "")[:50]
    if len(case.get("user_input", "")) > 50:
        input_preview += "..."
    
    # 创建带边框的卡片
    with st.container():
        # 使用Markdown渲染卡片样式
        is_selected = 'current_case_id' in st.session_state and st.session_state.current_case_id == case.get('id', '')
        border_color = '#FF4B4B' if is_selected else 'transparent'
        
        st.markdown(f"""
        <div style="padding:10px; border:1px solid #f0f2f6; border-radius:5px; margin-bottom:10px; border-left:4px solid {border_color}">
            <h4 style="margin:0; font-size:0.95em">{get_shortened_id(case_id)}</h4>
            <p style="margin:4px 0; font-size:0.95em">{case_desc}</p>
            <p style="margin:4px 0; font-size:0.85em; color:#777; white-space:nowrap; overflow:hidden; text-overflow:ellipsis">{input_preview}</p>
        </div>
        """, unsafe_allow_html=True)
        
        # 添加查看按钮
        if st.button("查看", key=f"view_btn_{index}"):
            on_click(case)


def display_test_case_list(
    cases: List[Dict[str, Any]], 
    page_number: int, 
    page_size: int, 
    on_case_selected: Callable
) -> None:
    """显示分页的测试用例列表
    
    Args:
        cases: 测试用例列表
        page_number: 当前页码（从0开始）
        page_size: 每页显示的测试用例数量
        on_case_selected: 选择测试用例时的回调函数
    """
    # 计算总页数
    total_pages = max(1, (len(cases) + page_size - 1) // page_size)
    
    # 确保页码在有效范围内
    page_number = min(page_number, total_pages - 1)
    page_number = max(0, page_number)
    
    # 计算当前页的用例
    start_idx = page_number * page_size
    end_idx = min(start_idx + page_size, len(cases))
    current_page_cases = cases[start_idx:end_idx]
    
    # 显示用例
    st.markdown("### 选择测试用例")
    
    if current_page_cases:
        for i, case in enumerate(current_page_cases):
            display_test_case_card(case, i, on_case_selected)
    
        # 分页控件
        col1, col2, col3 = st.columns([1, 1, 2])
        
        with col1:
            if st.button("◀️ 上一页", disabled=page_number <= 0, use_container_width=True):
                st.session_state.page_number = page_number - 1
                st.rerun()
        
        with col2:
            if st.button("▶️ 下一页", disabled=page_number >= total_pages - 1, use_container_width=True):
                st.session_state.page_number = page_number + 1
                st.rerun()
        
        with col3:
            st.caption(f"第 {page_number + 1} 页，共 {total_pages} 页")
            st.caption(f"显示 {start_idx + 1} 到 {end_idx}，共 {len(cases)} 个测试用例")
    else:
        st.info("暂无测试用例，请点击添加按钮创建，或修改搜索条件")


def display_test_case_editor(
    case: Dict[str, Any], 
    case_index: int, 
    on_save: Callable,
    on_delete: Callable
) -> Dict[str, Any]:
    """显示测试用例编辑器
    
    Args:
        case: 测试用例字典
        case_index: 测试用例在测试集中的索引
        on_save: 保存测试用例时的回调函数
        on_delete: 删除测试用例时的回调函数
        
    Returns:
        更新后的测试用例字典
    """
    st.markdown(f"### ✏️ {case.get('description', '未命名测试用例')}")
    
    # 基本信息编辑区
    col1, col2 = st.columns([3, 1])
    with col1:
        new_id = st.text_input("用例ID", value=case.get("id", ""), key=f"edit_id_{case_index}")
        new_desc = st.text_input("描述", value=case.get("description", ""), key=f"edit_desc_{case_index}")
        new_user_input = st.text_area("用户输入", value=case.get("user_input", ""), height=150, key=f"edit_input_{case_index}", placeholder="按 Shift+Enter 换行")
        
        # 优先使用 session_state 中的值，保证AI生成后能立即刷新
        output_key = f"edit_output_{case_index}"
        output_value = st.session_state.get(output_key, case.get("expected_output", ""))
        new_expected_output = st.text_area("期望输出", value=output_value, height=150, key=output_key, placeholder="按 Shift+Enter 换行")

    with col2:
        st.write("")
        st.write("")
        if st.button("🗑️ 删除", key="delete_case_btn", use_container_width=True):
            on_delete(case)
            return case
    
    # 使用选项卡来组织详情区域
    tab1, tab2, tab3 = st.tabs(["📝 输入与输出", "🔧 变量", "📊 评估标准"])
    
    with tab1:
        # 用通用组件展示用例详情、响应和评估结果
        from ui.components import display_test_case_details
        display_test_case_details(case, show_system_prompt=True, inside_expander=True)
        
        # 添加AI重新生成期望输出功能
        st.divider()
        st.subheader("🤖 使用AI重新生成期望输出")
        st.caption("使用指定模型和提示词模版重新生成期望输出")
        
        # 检查是否有确认更新的状态变量
        confirm_state_key = f"confirm_state_{case.get('id', '')}"
        if confirm_state_key in st.session_state and st.session_state[confirm_state_key]:
            # 有确认状态，说明用户刚刚点击了确认按钮
            # 从状态中读取要更新的文本
            updated_text = st.session_state[f"output_to_update_{case.get('id', '')}"]
            
            # 更新当前用例对象
            case["expected_output"] = updated_text
            
            # 更新文本区域控件值，确保UI立即更新
            output_key = f"edit_output_{case_index}"
            st.session_state[output_key] = updated_text
            
            # 清除确认状态
            st.session_state[confirm_state_key] = False
            
            # 调用保存回调
            on_save(case)
            
            st.success("✅ 成功更新期望输出")
            st.rerun()
        
        col1, col2, col3 = st.columns(3)
        
        with col1:
            # 模型选择
            config = load_config()
            available_models = get_available_models()
            all_model_options = []
            
            for provider, models in available_models.items():
                for model in models:
                    all_model_options.append(f"{model} ({provider})")
            
            # 默认选择gpt-4或第一个模型
            default_idx = 0
            for i, model_str in enumerate(all_model_options):
                if model_str.startswith("gpt-4"):
                    default_idx = i
                    break
            
            selected_model_str = st.selectbox(
                "选择模型",
                options=all_model_options,
                index=default_idx,
                key=f"regen_model_{case_index}"
            )
        
        with col2:
            # 模板选择
            template_list = get_template_list()
            selected_template_name = st.selectbox(
                "选择提示词模板",
                options=template_list,
                key=f"regen_template_{case_index}"
            )
        
        with col3:
            # 温度设置
            temperature = st.slider(
                "温度", 
                0.0, 1.0, 0.7, 0.1, 
                key=f"regen_temp_{case_index}",
                help="较高的值会使输出更加随机，较低的值会使输出更加确定"
            )
        
        # 执行按钮
        if st.button("✨ 使用AI重新生成期望输出", type="primary", key=f"regen_btn_{case_index}"):
            if not selected_model_str or not selected_template_name:
                st.error("请选择模型和提示词模板")
            elif not case.get("user_input"):
                st.error("测试用例必须有用户输入才能生成期望输出")
            else:
                # 解析模型和提供商
                selected_model = selected_model_str.split(" (")[0]
                selected_provider = selected_model_str.split(" (")[1].rstrip(")")
                
                # 加载模板
                template = load_template(selected_template_name)
                
                with st.spinner("AI正在生成期望输出..."):
                    # 使用统一的AI生成函数
                    result = generate_ai_expected_output(
                        case=case,
                        model=selected_model,
                        provider=selected_provider,
                        template=template,
                        temperature=temperature,
                        batch_mode=False
                    )
                    
                    if "error" in result and result["error"]:
                        st.error(f"生成期望输出失败: {result['error']}")
                    else:
                        generated_text = result.get("text", "")
                        
                        if generated_text:
                            # 显示生成的输出并提供确认选项
                            st.success("✅ 成功生成期望输出")
                            
                            # 计算token使用量
                            usage = result.get("usage", {})
                            if usage:
                                st.caption(f"Token使用: 输入 {usage.get('prompt_tokens', 0)}, 输出 {usage.get('completion_tokens', 0)}, 总计 {usage.get('total_tokens', 0)}")
                            
                            st.write("**新生成的期望输出:**")
                            st.text_area(
                                "新生成的期望输出", 
                                value=generated_text, 
                                height=200, 
                                key=f"new_output_{case_index}", 
                                disabled=True, 
                                label_visibility="collapsed"
                            )
                            
                            # 存储生成的文本，用于确认按钮处理
                            output_update_key = f"output_to_update_{case.get('id', '')}"
                            st.session_state[output_update_key] = generated_text
                            
                            # 使用新的确认按钮处理逻辑
                            if st.button("✅ 确认使用此输出", key=f"confirm_output_{case.get('id', '')}"):
                                # 设置确认状态标志
                                st.session_state[f"confirm_state_{case.get('id', '')}"] = True
                                # 重新运行应用程序以触发状态处理
                                st.rerun()
                        else:
                            st.warning("AI返回了空的输出，请调整温度参数或尝试其他模型/模板")
    
    with tab2:
        # 变量编辑区
        st.caption("这些变量仅适用于当前测试用例")
        
        # 初始化变量字典
        if "variables" not in case or not isinstance(case["variables"], dict):
            case["variables"] = {}
        
        # 显示现有变量
        case_vars_to_remove = []
        
        if case["variables"]:
            st.write("**现有变量:**")
            for var_name, var_value in case["variables"].items():
                col1, col2, col3 = st.columns([1, 2, 0.5])
                
                with col1:
                    st.text(var_name)
                
                with col2:
                    new_value = st.text_area(
                        "变量值", 
                        value=var_value,
                        key=f"var_{var_name}",
                        height=100,
                        placeholder="按 Shift+Enter 换行"
                    )
                    case["variables"][var_name] = new_value
                
                with col3:
                    if st.button("🗑️", key=f"del_var_{var_name}"):
                        case_vars_to_remove.append(var_name)
        else:
            st.info("暂无变量")
        
        # 移除要删除的变量
        for var_name in case_vars_to_remove:
            if var_name in case["variables"]:
                del case["variables"][var_name]
                st.rerun()
        
        # 添加新变量
        st.divider()
        st.subheader("添加新变量")
        col1, col2 = st.columns([1, 2])
        with col1:
            new_var_name = st.text_input("变量名", key="new_var_name")
        with col2:
            new_var_value = st.text_input("变量值", key="new_var_value")
        
        if st.button("添加变量", use_container_width=True) and new_var_name:
            case["variables"][new_var_name] = new_var_value
            st.success(f"已添加变量: {new_var_name}")
            st.rerun()
    
    with tab3:
        # 评估标准编辑区
        st.subheader("评估标准")
        
        # 初始化评估标准
        if "evaluation_criteria" not in case or not isinstance(case["evaluation_criteria"], dict):
            case["evaluation_criteria"] = {}
        
        # AI生成评估标准按钮
        if st.button("✨ AI生成评估标准", type="primary", use_container_width=True):
            with st.spinner("AI正在生成评估标准..."):
                # 调用AI生成评估标准的函数
                # Ensure case has description, user_input, expected_output before calling
                case_desc = case.get("description", "")
                user_input = case.get("user_input", "")
                expected_output = case.get("expected_output", "")

                if not case_desc or not user_input or not expected_output:
                    st.warning("请先填写测试用例的描述、用户输入和期望输出，才能生成评估标准。")
                else:
                    result = generate_evaluation_criteria(
                        case_desc, 
                        user_input, 
                        expected_output
                    )
                    
                    if "error" in result:
                        st.error(f"生成评估标准失败: {result['error']}")
                    else:
                        # 更新测试用例的评估标准
                        case["evaluation_criteria"] = result["criteria"]
                        st.success("✅ 评估标准已自动生成")
                        st.rerun()
        
        # 显示现有评估标准
        criteria_to_remove = []
        
        if case["evaluation_criteria"]:
            for crit_name, crit_value in case["evaluation_criteria"].items():
                st.markdown(f"**{crit_name}**")
                new_value = st.text_area(
                    f"标准描述", 
                    value=crit_value,
                    key=f"criteria_{crit_name}",
                    height=100
                )
                case["evaluation_criteria"][crit_name] = new_value
                
                if st.button("删除此标准", key=f"del_crit_{crit_name}"):
                    criteria_to_remove.append(crit_name)
                    
                st.divider()
        else:
            st.info("暂无评估标准，请使用上方的AI生成功能或手动添加")
        
        # 移除要删除的标准
        for crit_name in criteria_to_remove:
            if crit_name in case["evaluation_criteria"]:
                del case["evaluation_criteria"][crit_name]
                st.rerun()
        
        # 添加新评估标准
        st.subheader("添加新评估标准")
        col1, col2 = st.columns([1, 2])
        with col1:
            new_crit_name = st.text_input("标准名称", key="new_crit_name")
        with col2:
            new_crit_desc = st.text_area("标准描述", key="new_crit_desc", height=100)
        
        if st.button("添加标准", use_container_width=True) and new_crit_name:
            case["evaluation_criteria"][new_crit_name] = new_crit_desc
            st.success(f"已添加评估标准: {new_crit_name}")
            st.rerun()
    
    # 底部保存区域
    st.divider()
    if st.button("💾 保存更改", use_container_width=True, type="primary", key=f"save_changes_{case_index}"):
        # 构建更新后的测试用例数据
        updated_case = dict(case)
        updated_case["id"] = new_id
        updated_case["description"] = new_desc or "未命名测试用例"
        updated_case["user_input"] = new_user_input
        updated_case["expected_output"] = new_expected_output
        
        # 调用保存回调
        on_save(updated_case)
    
    return case


def display_test_set_info_editor(test_set: Dict[str, Any], on_save: Callable) -> None:
    """显示测试集基本信息编辑器
    
    Args:
        test_set: 测试集字典
        on_save: 保存测试集时的回调函数
    """
    with st.container():
        col1, col2 = st.columns([3, 2])
        
        with col1:
            # 测试集基本信息
            new_name = st.text_input("测试集名称", value=test_set.get("name", ""))
            new_description = st.text_input("测试集描述", value=test_set.get("description", ""))
        
        with col2:
            # 操作按钮区（保存、导出、刷新）
            st.write("")  # 添加一些垂直空间以对齐
            button_cols = st.columns(3)
            
            with button_cols[0]:
                if st.button("💾 保存", type="primary", use_container_width=True):
                    # 更新测试集基本信息
                    test_set["name"] = new_name
                    test_set["description"] = new_description
                    on_save(test_set)
            
            with button_cols[1]:
                # 使用下拉菜单提供导出选项
                export_option = st.selectbox(
                    "导出格式",
                    options=["JSON", "CSV"],
                    key="export_format"
                )
                
                if export_option == "JSON":
                    if st.download_button(
                        label="📤 导出JSON",
                        data=json.dumps(test_set, ensure_ascii=False, indent=2),
                        file_name=f"{test_set.get('name', 'test_set')}.json",
                        mime="application/json",
                        use_container_width=True
                    ):
                        st.success("测试集已导出为JSON")
                else:  # CSV
                    from utils.test_set_manager import export_test_set_to_csv
                    if st.download_button(
                        label="📤 导出CSV",
                        data=export_test_set_to_csv(test_set),
                        file_name=f"{test_set.get('name', 'test_set')}.csv",
                        mime="text/csv",
                        use_container_width=True
                    ):
                        st.success("测试集已导出为CSV")
            
            with button_cols[2]:
                if st.button("🔄 刷新", use_container_width=True):
                    st.rerun()


def display_global_variables_editor(test_set: Dict[str, Any]) -> None:
    """显示测试集全局变量编辑器
    
    Args:
        test_set: 测试集字典
    """
    with st.expander("🌐 测试集全局变量", expanded=False):
        st.caption("这些变量将应用于所有测试用例")
        
        # 初始化变量字典
        if "variables" not in test_set or not isinstance(test_set["variables"], dict):
            test_set["variables"] = {}
        
        # 显示现有全局变量
        global_vars_to_remove = []
        
        if test_set["variables"]:
            col1, col2, col3 = st.columns([1, 2, 0.5])
            with col1:
                st.write("**变量名**")
            with col2:
                st.write("**变量值**")
            with col3:
                st.write("**操作**")
            
            for var_name, var_value in test_set["variables"].items():
                col1, col2, col3 = st.columns([1, 2, 0.5])
                
                with col1:
                    st.text(var_name)
                
                with col2:
                    new_value = st.text_area(
                        f"值", 
                        value=var_value,
                        key=f"glob_var_{var_name}",
                        height=100,
                        placeholder="按 Shift+Enter 换行"
                    )
                    test_set["variables"][var_name] = new_value
                
                with col3:
                    if st.button("🗑️", key=f"del_glob_{var_name}"):
                        global_vars_to_remove.append(var_name)
        else:
            st.info("暂无全局变量")
        
        # 移除标记为删除的全局变量
        for var_name in global_vars_to_remove:
            if var_name in test_set["variables"]:
                del test_set["variables"][var_name]
        
        # 添加新全局变量
        st.divider()
        col1, col2, col3 = st.columns([1, 2, 0.8])
        with col1:
            new_var_name = st.text_input("变量名称", key="new_global_var_name")
        with col2:
            new_var_value = st.text_input("变量值", key="new_global_var_value")
        with col3:
            if st.button("添加全局变量", use_container_width=True) and new_var_name:
                test_set["variables"][new_var_name] = new_var_value
                st.success(f"已添加全局变量: {new_var_name}")
                st.rerun()