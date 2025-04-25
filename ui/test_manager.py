import streamlit as st
import json
import pandas as pd
import time
import uuid
from datetime import datetime
# 修改导入方式
from config import save_test_set, load_test_set, get_test_set_list, get_available_models, get_api_key, load_config, delete_test_set
from utils.common import generate_evaluation_criteria
from models.api_clients import get_provider_from_model
from utils.evaluator import PromptEvaluator

def generate_unique_id(prefix="case"):
    """生成唯一的测试用例ID，确保不会重复"""
    timestamp = int(time.time())
    unique_part = str(uuid.uuid4())[:8]  # 使用UUID的一部分，避免ID太长
    return f"{prefix}_{timestamp}_{unique_part}"

def render_test_manager():
    st.title("📊 测试集管理")
    
    # 使用选项卡而不是列布局，使页面更高效
    tab_list, tab_edit = st.tabs(["📁 测试集列表", "✏️ 测试集编辑"])
    
    with tab_list:
        test_set_list = get_test_set_list()

        # ======= 操作区（批量/新建） =======
        st.markdown("#### 测试集操作")
        op_col1, op_col2, op_col3 = st.columns([2,2,2])
        with op_col1:
            selected_for_merge = st.multiselect(
                "批量合并（多选）",
                options=test_set_list,
                key="merge_test_sets_select"
            )
            if st.button("🔗 合并", disabled=len(selected_for_merge)<2, use_container_width=True):
                merged_cases = []
                seen_ids = set()
                merged_variables = {}
                for name in selected_for_merge:
                    ts = load_test_set(name)
                    if isinstance(ts.get("variables"), dict):
                        merged_variables.update(ts["variables"])
                    for case in ts.get("cases", []):
                        cid = case.get("id")
                        if cid in seen_ids:
                            case = dict(case)
                            case["id"] = generate_unique_id()
                        seen_ids.add(case["id"])
                        merged_cases.append(case)
                st.session_state.merged_test_set = {
                    "name": f"合并集_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
                    "description": f"由{', '.join(selected_for_merge)}合并而成",
                    "variables": merged_variables,
                    "cases": merged_cases
                }
                st.session_state.page = "test_manager"
                st.session_state.current_test_set = st.session_state.merged_test_set
                st.success(f"已合并{len(selected_for_merge)}个测试集，可在编辑页进一步修改后保存")
                st.rerun()
        with op_col2:
            del_name = st.selectbox("删除测试集", options=test_set_list, key="delete_test_set_select")

            # Use session state to track pending deletion
            confirm_key = f"confirm_del_{del_name}"
            pending_deletion_key = "test_set_pending_deletion"

            # Button to initiate deletion confirmation
            if st.button("🗑️ 删除", use_container_width=True):
                if del_name:
                    st.session_state[pending_deletion_key] = del_name
                    # Force rerun to show confirmation checkbox immediately
                    st.rerun()

            # Display confirmation checkbox if a test set is pending deletion
            if pending_deletion_key in st.session_state and st.session_state[pending_deletion_key] == del_name:
                st.warning(f"你确定要删除测试集 '{del_name}' 吗？此操作无法撤销。")
                confirm = st.checkbox("是的，确认删除", key=confirm_key)

                if confirm:
                    # Perform deletion if confirmed
                    if delete_test_set(del_name):
                        st.success(f"测试集 '{del_name}' 已删除")
                        # Clean up session state if the deleted set was the current one
                        current_set = st.session_state.get("current_test_set")
                        if current_set is not None and current_set.get("name") == del_name:
                             if "current_test_set" in st.session_state:
                                 del st.session_state.current_test_set
                             if "current_case" in st.session_state:
                                 del st.session_state.current_case
                             if "current_case_index" in st.session_state:
                                 del st.session_state.current_case_index

                        del st.session_state[pending_deletion_key] # Clear pending state
                        st.rerun() # Rerun to refresh the list and remove confirmation UI
                    else:
                        st.error("删除测试集时出错，可能文件不存在或权限不足。")
                        del st.session_state[pending_deletion_key] # Clear pending state even on error
                        st.rerun() # Rerun to remove confirmation UI
            # If the selected test set changes while confirmation is pending, clear the pending state
            elif pending_deletion_key in st.session_state and st.session_state[pending_deletion_key] != del_name:
                 del st.session_state[pending_deletion_key]
        with op_col3:
            if st.button("➕ 新建测试集", use_container_width=True):
                st.session_state.current_test_set = {
                    "name": f"新测试集_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
                    "description": "",
                    "variables": {},
                    "cases": [
                        {
                            "id": generate_unique_id(),
                            "description": "测试用例1",
                            "variables": {},
                            "user_input": "这里填写用户的输入内容。",
                            "expected_output": "这里填写期望的模型输出内容。评估将基于此内容判断模型响应的质量。",
                            "evaluation_criteria": {
                                "accuracy": "评估响应与期望输出的匹配程度",
                                "completeness": "评估响应是否包含所有必要信息",
                                "relevance": "评估响应与提示词的相关性",
                                "clarity": "评估响应的清晰度和可理解性"
                            }
                        }
                    ]
                }
                if "selected_case_index" in st.session_state:
                    del st.session_state.selected_case_index
                st.rerun()
        st.divider()

        # ======= 测试集列表区 =======
        st.markdown("#### 测试集列表")
        if test_set_list:
            for test_set_name in test_set_list:
                row_col1, row_col2, row_col3 = st.columns([6,1,1])
                with row_col1:
                    st.write(f"**{test_set_name}**")
                with row_col2:
                    if st.button("编辑", key=f"edit_{test_set_name}", use_container_width=True):
                        st.session_state.current_test_set = load_test_set(test_set_name)
                        # 兼容旧版本：检查并确保所有测试用例都有唯一ID
                        if "current_test_set" in st.session_state:
                            cases = st.session_state.current_test_set.get("cases", [])
                            ids_seen = set()
                            for i, case in enumerate(cases):
                                if "id" not in case or not case["id"] or case["id"] in ids_seen:
                                    case["id"] = generate_unique_id()
                                ids_seen.add(case["id"])
                        if "selected_case_index" in st.session_state:
                            del st.session_state.selected_case_index
                        st.rerun()
                with row_col3:
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

        # ======= 导入/示例区 =======
        st.markdown("#### 导入/示例")
        with st.expander("导入测试集"):
            upload_file = st.file_uploader("上传JSON测试集文件", type=["json"])
            if upload_file is not None:
                try:
                    uploaded_test_set = json.load(upload_file)
                    if st.button("确认导入"):
                        if "cases" in uploaded_test_set:
                            ids_seen = set()
                            for case in uploaded_test_set["cases"]:
                                if "id" not in case or not case["id"] or case["id"] in ids_seen:
                                    case["id"] = generate_unique_id()
                                ids_seen.add(case["id"])
                        st.session_state.current_test_set = uploaded_test_set
                        if "selected_case_index" in st.session_state:
                            del st.session_state.selected_case_index
                        st.success("测试集导入成功")
                        st.rerun()
                except json.JSONDecodeError:
                    st.error("文件格式错误，请上传有效的JSON文件")
        with st.expander("测试集示例结构"):
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
    
    with tab_edit:
        # 没有选择测试集时显示的内容
        if "current_test_set" not in st.session_state or not st.session_state.current_test_set:
            st.info("👈 请从'测试集列表'选项卡中创建新测试集或选择现有测试集")
            return
        
        # 显示当前测试集编辑器
        test_set = st.session_state.current_test_set
        
        # 重构：使用更紧凑的布局来展示测试集基本信息和操作按钮
        with st.container():
            col1, col2 = st.columns([3, 2])
            
            with col1:
                # 测试集基本信息
                test_set["name"] = st.text_input("测试集名称", value=test_set["name"])
                test_set["description"] = st.text_input("测试集描述", value=test_set["description"])
            
            with col2:
                # 操作按钮区（保存、导出、刷新）
                st.write("")  # 添加一些垂直空间以对齐
                button_cols = st.columns(3)
                
                with button_cols[0]:
                    if st.button("💾 保存", type="primary", use_container_width=True):
                        save_test_set(test_set["name"], test_set)
                        st.success(f"测试集 '{test_set['name']}' 已保存")
                
                with button_cols[1]:
                    if st.download_button(
                        label="📤 导出",
                        data=json.dumps(test_set, ensure_ascii=False, indent=2),
                        file_name=f"{test_set['name']}.json",
                        mime="application/json",
                        use_container_width=True
                    ):
                        st.success("测试集已导出")
                
                with button_cols[2]:
                    if st.button("🔄 刷新", use_container_width=True):
                        st.rerun()
        
        # 测试集全局变量
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
                        new_value = st.text_input(
                            f"值", 
                            value=var_value,
                            key=f"glob_var_{var_name}"
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
        
        # ===================== 重构的测试用例管理 =====================
        st.subheader("📋 测试用例管理")
        
        # 初始化用例列表
        if "cases" not in test_set or not isinstance(test_set["cases"], list):
            test_set["cases"] = []
            
        # 创建左右布局: 左侧列表，右侧详情
        list_col, detail_col = st.columns([2, 3])
        
        # 左侧：测试用例列表区域 - 添加固定高度和独立滚动区
        with list_col:
            # 新布局：测试用例添加按钮并排放置
            col1, col2 = st.columns(2)
            with col1:
                if st.button("➕ 添加测试用例", use_container_width=True):
                    new_case = {
                        "id": generate_unique_id(),
                        "description": f"测试用例 {len(test_set['cases']) + 1}",
                        "variables": {},
                        "user_input": "用户输入内容",
                        "expected_output": "期望输出内容",
                        "evaluation_criteria": {
                            "accuracy": "评估准确性的标准",
                            "completeness": "评估完整性的标准",
                            "relevance": "评估相关性的标准",
                            "clarity": "评估清晰度的标准"
                        }
                    }
                    test_set["cases"].append(new_case)
                    st.session_state.current_case = new_case
                    st.session_state.current_case_index = len(test_set["cases"]) - 1
                    st.success("已添加新测试用例")
                    st.rerun()
            
            with col2:
                gen_count = st.number_input("生成数量", min_value=1, max_value=1000, value=3, step=1, key="ai_gen_case_count") # Changed max_value to 1000
                if st.button("✨ AI生成测试用例", use_container_width=True):
                    with st.spinner("AI正在生成测试用例..."):
                        test_set = st.session_state.current_test_set
                        test_set_name = test_set.get("name", "")
                        test_set_desc = test_set.get("description", "")
                        example_case = test_set["cases"][0] if test_set.get("cases") else {
                            "id": "example_case",
                            "description": test_set_desc or test_set_name,
                            "user_input": "示例输入",
                            "expected_output": "示例输出",
                            "evaluation": {}
                        }
                        config = load_config()
                        evaluator_model = config.get("evaluator_model", "gpt-4")
                        # 修复正则表达式，去除乱码字符，改为非贪婪匹配
                        import re
                        base_purpose = test_set_desc or test_set_name
                        base_purpose = re.sub(r"请生成\d+个.*?测试用例.*?", "", base_purpose)
                        test_purpose = f"{base_purpose}。请生成{gen_count}个高质量测试用例，覆盖不同场景和边界。"
                        try:
                            evaluator = PromptEvaluator()
                            result = evaluator.generate_test_cases(
                                evaluator_model,
                                test_purpose,
                                example_case,
                                target_count=gen_count
                            )
                            if "error" in result:
                                st.error(f"生成测试用例失败: {result['error']}")
                                if "raw_response" in result:
                                    st.text_area("原始AI响应", value=result["raw_response"], height=200)
                            else:
                                test_cases = result.get("test_cases", [])
                                added_count = 0
                                for tc in test_cases:
                                    if "id" not in tc or not tc["id"]:
                                        tc["id"] = generate_unique_id()
                                    test_set["cases"].append(tc)
                                    added_count += 1
                                save_test_set(test_set["name"], test_set)
                                st.success(f"成功生成并添加 {added_count} 个测试用例到测试集 '{test_set['name']}' (目标: {gen_count})")
                                st.rerun()
                        except Exception as e:
                            st.error(f"生成测试用例时发生异常: {e}")
            
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
                sort_options = {
                    "ID (升序)": lambda cases: sorted(cases, key=lambda x: x.get("id", "")),
                    "ID (降序)": lambda cases: sorted(cases, key=lambda x: x.get("id", ""), reverse=True),
                    "描述 (升序)": lambda cases: sorted(cases, key=lambda x: x.get("description", "")),
                    "描述 (降序)": lambda cases: sorted(cases, key=lambda x: x.get("description", ""), reverse=True),
                }
                
                sort_by = st.selectbox(
                    "排序方式",
                    options=list(sort_options.keys()),
                    index=0
                )
            
            # 应用过滤和排序
            filtered_cases = test_set["cases"]
            
            # 应用搜索过滤
            if search_query:
                filtered_cases = [
                    case for case in filtered_cases if (
                        search_query.lower() in case.get("id", "").lower() or
                        search_query.lower() in case.get("description", "").lower() or
                        search_query.lower() in case.get("user_input", "").lower() or
                        search_query.lower() in case.get("expected_output", "").lower()
                    )
                ]
            
            # 应用排序
            filtered_cases = sort_options[sort_by](filtered_cases)
            
            # 计算总页数
            total_pages = max(1, (len(filtered_cases) + page_size - 1) // page_size)
            
            # 确保页码在有效范围内
            st.session_state.page_number = min(st.session_state.page_number, total_pages - 1)
            
            # 计算当前页的用例
            start_idx = st.session_state.page_number * page_size
            end_idx = min(start_idx + page_size, len(filtered_cases))
            current_page_cases = filtered_cases[start_idx:end_idx]
            
            # 显示用例表格
            if filtered_cases:
                st.markdown("### 选择测试用例")
                
                # 使用Streamlit原生组件而不是HTML代码来展示测试用例列表
                for i, case in enumerate(current_page_cases):
                    # 获取真实的索引
                    real_index = start_idx + i
                    
                    # 计算截断的用户输入文本作为预览
                    input_preview = case.get("user_input", "")[:50] + "..." if len(case.get("user_input", "")) > 50 else case.get("user_input", "")
                    
                    case_id = case.get("id", "未知ID")
                    case_desc = case.get("description", "未命名")
                    
                    # 创建带边框的卡片
                    with st.container():
                        st.markdown(f"""
                        <div style="padding:10px; border:1px solid #f0f2f6; border-radius:5px; margin-bottom:10px; border-left:4px solid {'#FF4B4B' if 'current_case_index' in st.session_state and st.session_state.current_case_index == real_index else 'transparent'}">
                            <h4 style="margin:0; font-size:0.95em">{case_id}</h4>
                            <p style="margin:4px 0; font-size:0.95em">{case_desc}</p>
                            <p style="margin:4px 0; font-size:0.85em; color:#777; white-space:nowrap; overflow:hidden; text-overflow:ellipsis">{input_preview}</p>
                        </div>
                        """, unsafe_allow_html=True)
                        
                        # 添加查看按钮
                        if st.button("查看", key=f"view_btn_{real_index}"):
                            st.session_state.current_case = case
                            st.session_state.current_case_index = real_index
                            st.rerun()
                
                # 分页控件
                col1, col2, col3 = st.columns([1, 1, 2])
                
                with col1:
                    if st.button("◀️ 上一页", disabled=st.session_state.page_number <= 0, use_container_width=True):
                        st.session_state.page_number -= 1
                        st.rerun()
                
                with col2:
                    if st.button("▶️ 下一页", disabled=st.session_state.page_number >= total_pages - 1, use_container_width=True):
                        st.session_state.page_number += 1
                        st.rerun()
                
                with col3:
                    st.caption(f"第 {st.session_state.page_number + 1} 页，共 {total_pages} 页")
                    st.caption(f"显示 {start_idx + 1} 到 {end_idx}，共 {len(filtered_cases)} 个测试用例")
            
            else:
                st.info("暂无测试用例，请点击添加按钮创建，或修改搜索条件")
                
        # 右侧：测试用例详情区域
        with detail_col:
            # 显示详情或提示选择用例
            if "current_case" in st.session_state and "current_case_index" in st.session_state:
                case = st.session_state.current_case
                case_index = st.session_state.current_case_index
                
                st.markdown(f"### ✏️ {case.get('description', '未命名测试用例')}")
                
                # 基本信息编辑区
                col1, col2 = st.columns([3, 1])
                with col1:
                    # IMPORTANT: Assign keys to ensure widgets update correctly
                    new_id = st.text_input("用例ID", value=case.get("id", ""), key=f"edit_id_{case_index}")
                    new_desc = st.text_input("描述", value=case.get("description", ""), key=f"edit_desc_{case_index}")
                    new_user_input = st.text_area("用户输入", value=case.get("user_input", ""), height=80, key=f"edit_input_{case_index}")
                    new_expected_output = st.text_area("期望输出", value=case.get("expected_output", ""), height=80, key=f"edit_output_{case_index}")

                with col2:
                    st.write("")
                    st.write("")
                    if st.button("🗑️ 删除", key="delete_case_btn", use_container_width=True):
                        # 直接删除此用例
                        test_set["cases"].pop(case_index)
                        if "current_case" in st.session_state:
                            del st.session_state.current_case
                        if "current_case_index" in st.session_state:
                            del st.session_state.current_case_index
                        st.success("测试用例已删除")
                        st.rerun()
                
                # 使用选项卡来组织详情区域
                tab1, tab2, tab3 = st.tabs(["📝 输入与输出", "🔧 变量", "📊 评估标准"])
                
                with tab1:
                    # 用通用组件展示用例详情、响应和评估结果
                    from ui.components import display_test_case_details
                    display_test_case_details(case, show_system_prompt=True, inside_expander=True)
                
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
                                new_value = st.text_input(
                                    "变量值", 
                                    value=var_value,
                                    key=f"var_{var_name}"
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
                            result = generate_evaluation_criteria(
                                case["description"], 
                                case["user_input"], 
                                case["expected_output"]
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
                    # Get the index and the test_set from session state
                    case_index = st.session_state.current_case_index
                    test_set = st.session_state.current_test_set

                    # Validate index
                    if 0 <= case_index < len(test_set["cases"]):
                        # Get a direct reference to the case dictionary in the list
                        case_to_update = test_set["cases"][case_index]

                        # Update the dictionary directly using values from the input widgets
                        case_to_update["id"] = new_id
                        case_to_update["description"] = new_desc
                        case_to_update["user_input"] = new_user_input
                        case_to_update["expected_output"] = new_expected_output
                        # Variables and criteria are modified via widgets bound to st.session_state.current_case
                        # Ensure these changes are saved by updating from the potentially modified session state case
                        current_edited_case = st.session_state.current_case
                        case_to_update["variables"] = current_edited_case.get("variables", {})
                        case_to_update["evaluation_criteria"] = current_edited_case.get("evaluation_criteria", {})

                        # Update the session state's current_case to reflect the saved state
                        st.session_state.current_case = case_to_update

                        st.success("测试用例已保存")
                        # Rerun to refresh the UI, especially the list view
                        st.rerun()
                    else:
                        st.error(f"保存失败：无效的测试用例索引 {case_index}")

            else:
                # 显示提示
                st.info("👈 请从左侧列表选择一个测试用例进行查看和编辑")