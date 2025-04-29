import streamlit as st
import json
import pandas as pd
import time
from datetime import datetime
# 从utils导入测试集相关功能
from utils.test_set_manager import (
    create_new_test_set, merge_test_sets, import_test_set_from_json,
    import_test_set_from_csv, add_test_case, update_test_case, delete_test_case, 
    generate_unique_id, filter_test_cases, sort_test_cases, ensure_unique_id
)
from utils.test_case_generator import batch_generate_expected_outputs
from utils.evaluator import PromptEvaluator
from ui.test_case_view import (
    display_test_case_list, display_test_case_editor,
    display_test_set_info_editor, display_global_variables_editor
)
from config import save_test_set, load_test_set, get_test_set_list, delete_test_set, get_template_list, load_template


def render_test_manager():
    """渲染测试集管理页面"""
    st.title("📊 测试集管理")
    
    # 使用选项卡布局
    tab_list, tab_edit = st.tabs(["📁 测试集列表", "✏️ 测试集编辑"])
    
    with tab_list:
        render_test_set_list_tab()
    
    with tab_edit:
        render_test_set_edit_tab()


def render_test_set_list_tab():
    """渲染测试集列表选项卡"""
    test_set_list = get_test_set_list()

    # 操作区（批量/新建）
    st.markdown("#### 测试集操作")
    op_col1, op_col2, op_col3 = st.columns([2, 2, 2])
    
    with op_col1:
        # 批量合并测试集
        selected_for_merge = st.multiselect(
            "批量合并（多选）",
            options=test_set_list,
            key="merge_test_sets_select"
        )
        if st.button("🔗 合并", disabled=len(selected_for_merge) < 2, use_container_width=True):
            merged_test_set = merge_test_sets(selected_for_merge)
            st.session_state.current_test_set = merged_test_set
            st.success(f"已合并{len(selected_for_merge)}个测试集，可在编辑页进一步修改后保存")
            st.rerun()
    
    with op_col2:
        # 删除测试集
        del_name = st.selectbox("删除测试集", options=test_set_list, key="delete_test_set_select")
        
        # 使用session state跟踪待删除的测试集
        confirm_key = f"confirm_del_{del_name}"
        pending_deletion_key = "test_set_pending_deletion"
        
        if st.button("🗑️ 删除", use_container_width=True):
            if del_name:
                st.session_state[pending_deletion_key] = del_name
                st.rerun()
        
        # 显示删除确认UI
        if pending_deletion_key in st.session_state and st.session_state[pending_deletion_key] == del_name:
            st.warning(f"你确定要删除测试集 '{del_name}' 吗？此操作无法撤销。")
            confirm = st.checkbox("是的，确认删除", key=confirm_key)
            
            if confirm:
                if delete_test_set(del_name):
                    st.success(f"测试集 '{del_name}' 已删除")
                    # 清理会话状态
                    current_set = st.session_state.get("current_test_set")
                    if current_set is not None and current_set.get("name") == del_name:
                        if "current_test_set" in st.session_state:
                            del st.session_state.current_test_set
                        if "current_case" in st.session_state:
                            del st.session_state.current_case
                        if "current_case_index" in st.session_state:
                            del st.session_state.current_case_index
                    
                    # 清除待删除状态
                    del st.session_state[pending_deletion_key]
                    st.rerun()
                else:
                    st.error("删除测试集时出错，可能文件不存在或权限不足。")
                    del st.session_state[pending_deletion_key]
                    st.rerun()
        # 如果选择的测试集发生变化，清除待删除状态
        elif pending_deletion_key in st.session_state and st.session_state[pending_deletion_key] != del_name:
            del st.session_state[pending_deletion_key]
    
    with op_col3:
        # 创建新测试集
        if st.button("➕ 新建测试集", use_container_width=True):
            st.session_state.current_test_set = create_new_test_set()
            if "selected_case_index" in st.session_state:
                del st.session_state.selected_case_index
            st.rerun()
    
    st.divider()

    # 测试集列表区
    st.markdown("#### 测试集列表")
    if test_set_list:
        for test_set_name in test_set_list:
            row_col1, row_col2, row_col3 = st.columns([6, 1, 1])
            with row_col1:
                st.write(f"**{test_set_name}**")
            with row_col2:
                if st.button("编辑", key=f"edit_{test_set_name}", use_container_width=True):
                    test_set = load_test_set(test_set_name)
                    # 确保所有测试用例都有唯一ID
                    ids_seen = set()
                    for case in test_set.get("cases", []):
                        ensure_unique_id(case, ids_seen)
                        ids_seen.add(case.get("id", ""))
                    
                    st.session_state.current_test_set = test_set
                    if "selected_case_index" in st.session_state:
                        del st.session_state.selected_case_index
                    st.rerun()
            with row_col3:
                from pathlib import Path
                from config import TEST_SETS_DIR
                file_path = TEST_SETS_DIR / f"{test_set_name}.json"
                with open(file_path, "r", encoding="utf-8") as f:
                    test_set_data = f.read()
                st.download_button(
                    label="导出",
                    data=test_set_data,
                    file_name=f"{test_set_name}.json",
                    mime="application/json",
                    use_container_width=True,
                    key=f"export_{test_set_name}"
                )
    else:
        st.info("暂无测试集，请新建或导入")
    
    st.divider()

    # 导入/示例区
    st.markdown("#### 导入/示例")
    with st.expander("导入测试集"):
        # 选择导入类型
        import_type = st.radio(
            "选择导入格式",
            ["JSON", "CSV"],
            horizontal=True
        )
        
        if import_type == "JSON":
            upload_file = st.file_uploader("上传测试集文件", type=["json"], key="json_uploader")
            if upload_file is not None:
                try:
                    uploaded_test_set = json.load(upload_file)
                    processed_test_set = import_test_set_from_json(uploaded_test_set)
                    
                    if st.button("确认导入 JSON"):
                        st.session_state.current_test_set = processed_test_set
                        if "selected_case_index" in st.session_state:
                            del st.session_state.selected_case_index
                        st.success("测试集导入成功")
                        st.rerun()
                except json.JSONDecodeError:
                    st.error("文件格式错误，请上传有效的JSON文件")
        else:  # CSV
            upload_file = st.file_uploader("上传测试集文件", type=["csv"], key="csv_uploader")
            if upload_file is not None:
                csv_data = upload_file.getvalue().decode('utf-8-sig')
                # 提供测试集名称选项
                test_set_name = st.text_input("测试集名称", placeholder="如不指定，则自动生成")
                if st.button("确认导入 CSV"):
                    try:
                        processed_test_set = import_test_set_from_csv(csv_data, test_set_name)
                        st.session_state.current_test_set = processed_test_set
                        if "selected_case_index" in st.session_state:
                            del st.session_state.selected_case_index
                        st.success(f"测试集 '{processed_test_set['name']}' 导入成功")
                        st.rerun()
                    except Exception as e:
                        st.error(f"CSV导入失败: {str(e)}")
                        st.info("请确保CSV文件具有正确的标题行，参考CSV文件示例结构")
    
    # 添加CSV示例结构信息
    with st.expander("JSON测试集示例结构"):
        st.code("""
{
  "name": "情感分析测试集",
  "description": "用于测试情感分析模型的一组测试用例",
  "variables": {
    "language": "中文"
  },
  "cases": [
    {
      "id": "positive_1",
      "description": "强烈正面情感",
      "variables": {
        "text": "今天是我人生中最美好的一天，一切都太完美了！"
      },
      "expected_output": {
        "sentiment": "positive",
        "score": 0.9
      },
      "evaluation_criteria": {
        "accuracy": "情感判断必须是positive，分数在0.8-1.0之间",
        "completeness": "必须包含sentiment、score和analysis三个字段"
      }
    }
  ]
}
        """, language="json")
        
    with st.expander("CSV测试集示例结构"):
        st.caption("""CSV文件应包含以下列：
- id: 测试用例ID
- description: 测试用例描述
- user_input: 用户输入
- expected_output: 期望输出
- accuracy: 准确性评估标准
- completeness: 完整性评估标准
- relevance: 相关性评估标准
- clarity: 清晰度评估标准
- global_*: 全局变量 (例如：global_language)
- var_*: 测试用例变量 (例如：var_text)
        """)
        
        st.code("""
id,description,user_input,expected_output,accuracy,completeness,relevance,clarity,global_language,var_text
positive_1,强烈正面情感,今天是我人生中最美好的一天，一切都太完美了！,{"sentiment": "positive","score": 0.9},情感判断必须是positive，分数在0.8-1.0之间,必须包含sentiment和score两个字段,响应必须与输入文本的情感相关,输出应清晰易懂,中文,今天是我人生中最美好的一天
negative_1,强烈负面情感,今天是我最糟糕的一天，所有事情都出错了！,{"sentiment": "negative","score": 0.9},情感判断必须是negative，分数在0.8-1.0之间,必须包含sentiment和score两个字段,响应必须与输入文本的情感相关,输出应清晰易懂,,
        """, language="text")


def render_test_set_edit_tab():
    """渲染测试集编辑选项卡"""
    # 没有选择测试集时显示的内容
    if "current_test_set" not in st.session_state or not st.session_state.current_test_set:
        st.info("👈 请从'测试集列表'选项卡中创建新测试集或选择现有测试集")
        return
    
    # 获取当前的测试集
    test_set = st.session_state.current_test_set
    
    # 测试集基本信息和操作
    def on_test_set_save(updated_test_set):
        save_test_set(updated_test_set["name"], updated_test_set)
        st.success(f"测试集 '{updated_test_set['name']}' 已保存")
    
    display_test_set_info_editor(test_set, on_save=on_test_set_save)
    
    # 测试集全局变量
    display_global_variables_editor(test_set)
    
    # 批量操作功能区
    render_batch_operations()
    
    # 测试用例管理
    st.subheader("📋 测试用例管理")
    
    # 初始化用例列表
    if "cases" not in test_set or not isinstance(test_set["cases"], list):
        test_set["cases"] = []
    
    # 创建左右布局: 左侧列表，右侧详情
    list_col, detail_col = st.columns([2, 3])
    
    # 左侧：测试用例列表区域
    with list_col:
        render_test_case_list(test_set)
    
    # 右侧：测试用例详情区域
    with detail_col:
        render_test_case_detail(test_set)


def render_batch_operations():
    """渲染批量操作功能区"""
    with st.expander("🔄 批量操作", expanded=False):
        st.caption("对测试集中的多个测试用例执行批量操作")
        
        # 当前测试集
        test_set = st.session_state.current_test_set
        
        # 统一参数选择
        param_col1, param_col2, param_col3 = st.columns(3)
        with param_col1:
            from config import load_config, get_available_models
            config = load_config()
            available_models = get_available_models()
            all_model_options = []
            for provider, models in available_models.items():
                for model in models:
                    all_model_options.append(f"{model} ({provider})")
            selected_model_str = st.selectbox(
                "选择模型",
                options=all_model_options,
                key="batch_model"
            )
            selected_model = selected_model_str.split(" (")[0] if selected_model_str else None
            selected_provider = selected_model_str.split(" (")[1].rstrip(")") if selected_model_str else None
        with param_col2:
            template_list = get_template_list()
            selected_template_name = st.selectbox(
                "选择提示词模板",
                options=template_list,
                key="batch_template"
            )
            template = load_template(selected_template_name) if selected_template_name else None
        with param_col3:
            temperature = st.slider("温度", 0.0, 1.0, 0.3, 0.1, key="batch_temp")
        
        # 批量操作按钮 (增加为五个，包括新增的批量清空评估标准)
        btn_col1, btn_col2, btn_col3, btn_col4, btn_col5 = st.columns(5)
        
        # AI生成用户输入
        with btn_col1:
            gen_inputs_count = st.number_input("生成输入数量", min_value=1, max_value=1000, value=5, step=1, key="batch_gen_inputs_count")
            if st.button("💡 AI生成用户输入", use_container_width=True):
                with st.spinner("AI正在生成用户输入..."):
                    test_set_desc = test_set.get("description", "通用测试") or "通用测试"
                    try:
                        evaluator = PromptEvaluator()
                        
                        # 创建事件循环并运行异步函数
                        import asyncio
                        loop = asyncio.new_event_loop()
                        asyncio.set_event_loop(loop)
                        result = loop.run_until_complete(evaluator.generate_user_inputs(test_set_desc, gen_inputs_count))
                        loop.close()
                        
                        if "error" in result:
                            st.error(f"生成用户输入失败: {result['error']}")
                        else:
                            user_inputs = result.get("user_inputs", [])
                            added_count = 0
                            for user_input in user_inputs:
                                if user_input:
                                    new_case = {
                                        "description": f"AI生成输入 {added_count + 1}",
                                        "variables": {},
                                        "user_input": user_input,
                                        "expected_output": "",
                                        "evaluation_criteria": {
                                            "accuracy": "评估准确性的标准",
                                            "completeness": "评估完整性的标准",
                                            "relevance": "评估相关性的标准",
                                            "clarity": "评估清晰度的标准"
                                        }
                                    }
                                    test_set = add_test_case(test_set, new_case)
                                    added_count += 1
                            
                            if added_count > 0:
                                save_test_set(test_set["name"], test_set)
                                st.session_state.current_test_set = test_set
                                st.success(f"成功生成并添加 {added_count} 个仅包含用户输入的测试用例")
                                st.rerun()
                            else:
                                st.warning("AI未能生成有效的用户输入。")
                    except Exception as e:
                        st.error(f"生成用户输入时发生异常: {str(e)}")
        
        # AI生成测试用例
        with btn_col2:
            gen_case_count = st.number_input("生成用例数量", min_value=1, max_value=1000, value=3, step=1, key="batch_gen_case_count")
            if st.button("✨ AI生成测试用例", use_container_width=True):
                with st.spinner("AI正在生成测试用例..."):
                    test_set_name = test_set.get("name", "")
                    test_set_desc = test_set.get("description", "")
                    example_case = test_set["cases"][0] if test_set.get("cases") else {
                        "id": "example_case",
                        "description": test_set_desc or test_set_name,
                        "user_input": "示例输入",
                        "expected_output": "示例输出",
                        "evaluation": {}
                    }
                    import re
                    base_purpose = test_set_desc or test_set_name
                    base_purpose = re.sub(r"请生成\\d+个.*?测试用例.*?", "", base_purpose)
                    test_purpose = f"{base_purpose}。请生成{gen_case_count}个高质量测试用例，覆盖不同场景和边界。"
                    try:
                        evaluator = PromptEvaluator()
                        result = evaluator.generate_test_cases(
                            selected_model or config.get("evaluator_model", "gpt-4"),
                            test_purpose,
                            example_case,
                            target_count=gen_case_count
                        )
                        if "error" in result:
                            st.error(f"生成测试用例失败: {result['error']}")
                            if "raw_response" in result:
                                st.text_area("原始AI响应", value=result["raw_response"], height=200)
                        else:
                            test_cases = result.get("test_cases", [])
                            added_count = 0
                            for tc in test_cases:
                                if "description" not in tc or not tc["description"]:
                                    tc["description"] = f"AI生成测试用例 {added_count + 1}"
                                test_set = add_test_case(test_set, tc)
                                added_count += 1
                            
                            save_test_set(test_set["name"], test_set)
                            st.session_state.current_test_set = test_set
                            st.success(f"成功生成并添加 {added_count} 个测试用例 (目标: {gen_case_count})")
                            st.rerun()
                    except Exception as e:
                        st.error(f"生成测试用例时发生异常: {str(e)}")
        
        # 批量生成优质输出
        with btn_col3:
            if st.button("✨ 批量生成优质输出", use_container_width=True):
                if not selected_model or not template:
                    st.error("请选择模型和提示词模板")
                else:
                    with st.spinner("正在批量生成预期输出..."):
                        progress_bar = st.progress(0)
                        status_text = st.empty()
                        
                        # 定义进度回调函数
                        def update_progress(current, total):
                            progress = current / total if total > 0 else 0
                            progress_bar.progress(progress)
                            status_text.text(f"正在处理: {current}/{total}")
                        
                        # 调用批量生成函数
                        result = batch_generate_expected_outputs(
                            test_set=test_set,
                            model=selected_model,
                            provider=selected_provider,
                            template=template,
                            temperature=temperature,
                            progress_callback=update_progress
                        )
                        
                        if result["status"] == "warning":
                            st.warning(result["message"])
                        elif result["status"] == "error":
                            st.error(result["message"])
                            if result.get("errors"):
                                for err in result["errors"]:
                                    st.error(f"处理用例 {err['case_id']} 失败: {err['error']}")
                        else:
                            # 保存测试集
                            save_test_set(test_set["name"], test_set)
                            st.session_state.current_test_set = test_set
                            st.success(result["message"])
                            st.rerun()
        
        # 批量填充评估标准
        with btn_col4:
            if st.button("✨ 批量填充评估标准", use_container_width=True):
                cases_to_fill = [
                    case for case in test_set.get("cases", []) 
                    if case.get("description") and case.get("user_input") and case.get("expected_output") 
                    and (not case.get("evaluation_criteria") or len(case.get("evaluation_criteria", {})) == 0)
                ]
                
                if not cases_to_fill:
                    st.warning("没有找到需要生成评估标准的测试用例，所有测试用例已有评估标准或缺少必要信息")
                else:
                    with st.spinner(f"正在为 {len(cases_to_fill)} 个测试用例生成评估标准..."):
                        progress_bar = st.progress(0)
                        status_text = st.empty()
                        
                        for i, case in enumerate(cases_to_fill):
                            status_text.text(f"正在处理测试用例 {i+1}/{len(cases_to_fill)}: {case.get('description', 'Case '+str(i+1))}")
                            try:
                                result = generate_evaluation_criteria(
                                    case.get("description", ""),
                                    case.get("user_input", ""),
                                    case.get("expected_output", "")
                                )
                                
                                if "error" in result:
                                    st.error(f"为测试用例 '{case.get('description', 'Case '+str(i+1))}' 生成评估标准失败: {result['error']}")
                                else:
                                    for test_case in test_set["cases"]:
                                        if test_case.get("id") == case.get("id"):
                                            test_case["evaluation_criteria"] = result["criteria"]
                                            break
                            except Exception as e:
                                st.error(f"生成评估标准时出错: {str(e)}")
                            
                            progress_bar.progress((i + 1) / len(cases_to_fill))
                        
                        status_text.text("✅ 批量生成评估标准完成!")
                        save_test_set(test_set["name"], test_set)
                        st.session_state.current_test_set = test_set
                        st.success(f"成功为 {len(cases_to_fill)} 个测试用例生成评估标准")
                        st.rerun()
                        
        # 批量清空评估标准（新增功能）
        with btn_col5:
            if st.button("🧹 批量清空评估标准", use_container_width=True):
                cases_with_criteria = [
                    case for case in test_set.get("cases", []) 
                    if case.get("evaluation_criteria") and len(case.get("evaluation_criteria", {})) > 0
                ]
                
                if not cases_with_criteria:
                    st.warning("没有找到含有评估标准的测试用例，无需清空")
                else:
                    # 增加确认对话框
                    if "confirm_clear_criteria" not in st.session_state:
                        st.session_state.confirm_clear_criteria = False
                    
                    st.warning(f"确定要清空所有 {len(cases_with_criteria)} 个测试用例的评估标准吗？此操作无法撤销。")
                    confirm = st.checkbox("是的，确认清空所有评估标准", key="confirm_clear_criteria_checkbox")
                    
                    if confirm:
                        with st.spinner(f"正在清空 {len(cases_with_criteria)} 个测试用例的评估标准..."):
                            progress_bar = st.progress(0)
                            status_text = st.empty()
                            
                            # 定义默认的空评估标准模板
                            default_criteria = {
                                "accuracy": "",
                                "completeness": "",
                                "relevance": "",
                                "clarity": ""
                            }
                            
                            for i, case in enumerate(cases_with_criteria):
                                case_desc = case.get("description", f"Case {i+1}")
                                status_text.text(f"正在处理测试用例 {i+1}/{len(cases_with_criteria)}: {case_desc}")
                                
                                # 清空评估标准
                                for test_case in test_set["cases"]:
                                    if test_case.get("id") == case.get("id"):
                                        test_case["evaluation_criteria"] = dict(default_criteria)
                                        break
                                
                                progress_bar.progress((i + 1) / len(cases_with_criteria))
                            
                            status_text.text("✅ 批量清空评估标准完成!")
                            save_test_set(test_set["name"], test_set)
                            st.session_state.current_test_set = test_set
                            st.session_state.confirm_clear_criteria = False
                            st.success(f"成功清空 {len(cases_with_criteria)} 个测试用例的评估标准")
                            st.rerun()


def render_test_case_list(test_set):
    """渲染测试用例列表区域"""
    # 关键词搜索框
    search_query = st.text_input("🔍 搜索测试用例", placeholder="输入关键词搜索")
    
    # 排序和分页控制
    col1, col2 = st.columns(2)
    
    with col1:
        # 初始化分页状态
        if "page_number" not in st.session_state:
            st.session_state.page_number = 0
        
        # 设置每页显示数量选项
        page_size_options = [5, 10, 20, 50]
        page_size = st.selectbox(
            "每页显示", 
            options=page_size_options,
            index=0,
            key="page_size"
        )
    
    with col2:
        # 排序选项
        sort_by = st.selectbox(
            "排序方式",
            options=["ID (升序)", "ID (降序)", "描述 (升序)", "描述 (降序)"],
            index=0
        )
    
    # 应用过滤和排序
    filtered_cases = filter_test_cases(test_set, search_query)
    sorted_cases = sort_test_cases(filtered_cases, sort_by)
    
    # 处理用例选择回调函数
    def on_case_selected(case):
        # 找到这个用例在原始test_set中的索引
        original_index = -1
        for i, original_case in enumerate(test_set["cases"]):
            if original_case.get("id") == case.get("id"):
                original_index = i
                break
        
        # 保存到会话状态
        st.session_state.current_case = dict(case)  # 使用深拷贝
        st.session_state.current_case_index = original_index  # 保存原始索引
        st.session_state.current_case_id = case.get("id", "")  # 保存case ID用于高亮显示
        st.rerun()
    
    # 显示用例列表
    display_test_case_list(
        cases=sorted_cases,
        page_number=st.session_state.get("page_number", 0),
        page_size=page_size,
        on_case_selected=on_case_selected
    )
    
    # 添加新建测试用例的按钮
    if st.button("➕ 添加测试用例", use_container_width=True):
        new_case = {
            "id": generate_unique_id(),
            "description": f"新测试用例 {len(test_set.get('cases', [])) + 1}",
            "variables": {},
            "user_input": "",
            "expected_output": "",
            "evaluation_criteria": {
                "accuracy": "评估响应与期望输出的匹配程度",
                "completeness": "评估响应是否包含所有必要信息",
                "relevance": "评估响应与提示词的相关性",
                "clarity": "评估响应的清晰度和可理解性"
            }
        }
        test_set = add_test_case(test_set, new_case)
        st.session_state.current_test_set = test_set
        
        # 选中新创建的测试用例
        st.session_state.current_case = dict(new_case)
        st.session_state.current_case_index = len(test_set["cases"]) - 1
        st.session_state.current_case_id = new_case["id"]
        
        st.success("已添加新的测试用例")
        st.rerun()


def render_test_case_detail(test_set):
    """渲染测试用例详情区域"""
    # 显示详情或提示选择用例
    if "current_case" in st.session_state and "current_case_index" in st.session_state:
        case_index = st.session_state.current_case_index
        
        # 从测试集中获取最新的用例数据
        if 0 <= case_index < len(test_set["cases"]):
            case = test_set["cases"][case_index]
            # 更新会话状态中的当前用例
            st.session_state.current_case = dict(case)
        else:
            # 如果索引无效，使用会话状态中的用例数据
            case = st.session_state.current_case
        
        # 定义保存和删除回调函数
        def on_case_save(updated_case):
            nonlocal test_set
            # 检查ID是否唯一
            existing_ids = set()
            for i, other_case in enumerate(test_set["cases"]):
                if i != case_index:  # 除了当前用例
                    existing_ids.add(other_case.get("id", ""))
            
            if not updated_case.get("id") or updated_case.get("id") in existing_ids:
                updated_case["id"] = generate_unique_id()
                st.warning(f"检测到ID冲突或为空，已自动生成新ID: {updated_case['id']}")
            
            test_set = update_test_case(test_set, case.get("id"), updated_case)
            st.session_state.current_test_set = test_set
            st.session_state.current_case = dict(updated_case)
            st.session_state.current_case_id = updated_case.get("id", "")
            
            save_test_set(test_set["name"], test_set)
            st.success("✅ 测试用例已保存")
            st.rerun()
        
        def on_case_delete(case_to_delete):
            nonlocal test_set
            test_set = delete_test_case(test_set, case_to_delete.get("id", ""))
            st.session_state.current_test_set = test_set
            
            # 清理会话状态
            if "current_case" in st.session_state:
                del st.session_state.current_case
            if "current_case_index" in st.session_state:
                del st.session_state.current_case_index
            if "current_case_id" in st.session_state:
                del st.session_state.current_case_id
            
            save_test_set(test_set["name"], test_set)
            st.success("测试用例已删除")
            st.rerun()
        
        # 使用测试用例编辑器组件
        display_test_case_editor(
            case=case,
            case_index=case_index,
            on_save=on_case_save,
            on_delete=on_case_delete
        )
    else:
        # 显示提示
        st.info("👈 请从左侧列表选择一个测试用例进行查看和编辑")