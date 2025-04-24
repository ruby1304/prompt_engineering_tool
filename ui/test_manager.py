import streamlit as st
import json
import pandas as pd
from datetime import datetime
# 修改导入方式
from config import save_test_set, load_test_set, get_test_set_list
from utils.common import generate_evaluation_criteria

def render_test_manager():
    st.title("📊 测试集管理")
    
    # 使用选项卡而不是列布局，使页面更高效
    tab_list, tab_edit = st.tabs(["📁 测试集列表", "✏️ 测试集编辑"])
    
    with tab_list:
        test_set_list = get_test_set_list()
        
        if st.button("➕ 新建测试集", use_container_width=True):
            st.session_state.current_test_set = {
                "name": f"新测试集_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
                "description": "",
                "variables": {},
                "cases": [
                    {
                        "id": "case_1",
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
            # 初始化编辑状态
            if "selected_case_index" in st.session_state:
                del st.session_state.selected_case_index
            st.rerun()
        
        if test_set_list:
            st.write("选择现有测试集:")
            for test_set_name in test_set_list:
                if st.button(f"📄 {test_set_name}", key=f"sel_{test_set_name}", use_container_width=True):
                    st.session_state.current_test_set = load_test_set(test_set_name)
                    # 初始化编辑状态
                    if "selected_case_index" in st.session_state:
                        del st.session_state.selected_case_index
                    st.rerun()
        
        # 导入测试集
        with st.expander("导入测试集"):
            upload_file = st.file_uploader("上传JSON测试集文件", type=["json"])
            if upload_file is not None:
                try:
                    uploaded_test_set = json.load(upload_file)
                    if st.button("确认导入"):
                        st.session_state.current_test_set = uploaded_test_set
                        # 初始化编辑状态
                        if "selected_case_index" in st.session_state:
                            del st.session_state.selected_case_index
                        st.success("测试集导入成功")
                        st.rerun()
                except json.JSONDecodeError:
                    st.error("文件格式错误，请上传有效的JSON文件")
        
        # 添加测试集示例展示
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
        
        # 基本信息编辑区
        col1, col2, col3 = st.columns([3, 1, 1])
        
        with col1:
            test_set["name"] = st.text_input("测试集名称", value=test_set["name"])
            test_set["description"] = st.text_area("测试集描述", value=test_set["description"], height=80)
        
        with col2:
            st.write("")
            st.write("")
            if st.button("💾 保存测试集", type="primary", use_container_width=True):
                save_test_set(test_set["name"], test_set)
                st.success(f"测试集 '{test_set['name']}' 已保存")
        
        with col3:
            st.write("")
            st.write("")
            if st.download_button(
                label="📤 导出JSON",
                data=json.dumps(test_set, ensure_ascii=False, indent=2),
                file_name=f"{test_set['name']}.json",
                mime="application/json",
                use_container_width=True
            ):
                st.success("测试集已导出")
        
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
        
        # ===================== 测试用例管理（优化后的部分）=====================
        st.subheader("📋 测试用例管理")
        
        # 初始化用例列表
        if "cases" not in test_set or not isinstance(test_set["cases"], list):
            test_set["cases"] = []
        
        # 批量操作和添加新测试用例按钮
        col1, col2 = st.columns([1, 4])
        with col1:
            if st.button("➕ 添加新测试用例", use_container_width=True):
                new_case = {
                    "id": f"case_{len(test_set['cases']) + 1}",
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
                # 设置新添加的用例为当前编辑的用例
                st.session_state.selected_case_index = len(test_set["cases"]) - 1
                st.success("已添加新测试用例")
                st.rerun()
        
        with col2:
            # 关键词搜索框
            search_query = st.text_input("🔍 搜索测试用例", placeholder="输入关键词搜索")
        
        # 用例过滤器选项
        filter_col1, filter_col2 = st.columns(2)
        
        with filter_col1:
            # 初始化分页状态
            if "page_number" not in st.session_state:
                st.session_state.page_number = 0
            
            # 设置每页显示数量选项
            page_size_options = [10, 20, 50, 100]
            page_size = st.selectbox(
                "每页显示", 
                options=page_size_options,
                index=0,
                key="page_size"
            )
        
        with filter_col2:
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
            # 准备表格数据
            case_data = []
            indices_in_original = []  # 存储过滤后的用例在原始列表中的索引
            
            for case in current_page_cases:
                # 找到用例在原始列表中的索引
                idx = test_set["cases"].index(case)
                indices_in_original.append(idx)
                
                # 添加表格数据
                case_data.append({
                    "用例ID": case.get("id", ""),
                    "描述": case.get("description", ""),
                    "变量数": len(case.get("variables", {})),
                    "评估标准数": len(case.get("evaluation_criteria", {})),
                    "输入长度": len(case.get("user_input", "")),
                    "期望输出长度": len(case.get("expected_output", ""))
                })
            
            # 创建数据框
            df = pd.DataFrame(case_data)
            
            # 添加选择列
            df.insert(0, "选择", False)
            
            # 如果有一个选择的用例，设置选择列的值
            if "selected_case_index" in st.session_state and st.session_state.selected_case_index is not None:
                for i, idx in enumerate(indices_in_original):
                    if idx == st.session_state.selected_case_index:
                        df.at[i, "选择"] = True
            
            # 显示表格，使用编辑器显示选择列
            edited_df = st.data_editor(
                df,
                use_container_width=True,
                hide_index=False,
                key="case_table",
                column_config={
                    "选择": st.column_config.CheckboxColumn("选择", default=False, width="small"),
                    "用例ID": st.column_config.TextColumn("用例ID", width="medium"),
                    "描述": st.column_config.TextColumn("描述", width="large"),
                    "变量数": st.column_config.NumberColumn("变量数", width="small"),
                    "评估标准数": st.column_config.NumberColumn("评估标准数", width="small"),
                    "输入长度": st.column_config.NumberColumn("输入字符数", width="small"),
                    "期望输出长度": st.column_config.NumberColumn("输出字符数", width="small")
                },
                disabled=["用例ID", "描述", "变量数", "评估标准数", "输入长度", "期望输出长度"]
            )
            
            # 检查选择状态变化
            if "case_table" in st.session_state and st.session_state.case_table is not None:
                # 找到被选择的行
                selected_indices = edited_df[edited_df["选择"] == True].index.tolist()
                
                if selected_indices:
                    # 获取最后一个选中的行索引，并转换为原始用例列表中的索引
                    selected_row = selected_indices[-1]  # 获取最新选中的行
                    if 0 <= selected_row < len(indices_in_original):
                        # 如果选择了一个新的行，更新session_state并刷新
                        new_selected_index = indices_in_original[selected_row]
                        if "selected_case_index" not in st.session_state or st.session_state.selected_case_index != new_selected_index:
                            st.session_state.selected_case_index = new_selected_index
                            st.rerun()
            
            # 分页控件
            col1, col2, col3, col4 = st.columns([1, 1, 2, 1])
            
            with col1:
                if st.button("◀️ 上一页", disabled=st.session_state.page_number <= 0):
                    st.session_state.page_number -= 1
                    st.rerun()
            
            with col2:
                if st.button("▶️ 下一页", disabled=st.session_state.page_number >= total_pages - 1):
                    st.session_state.page_number += 1
                    st.rerun()
            
            with col3:
                st.write(f"第 {st.session_state.page_number + 1} 页，共 {total_pages} 页")
                st.caption(f"显示 {start_idx + 1} 到 {end_idx}，共 {len(filtered_cases)} 个测试用例")
            
            with col4:
                # 跳转到指定页
                page_input = st.number_input(
                    "跳到页", 
                    min_value=1, 
                    max_value=total_pages, 
                    value=st.session_state.page_number + 1,
                    step=1,
                    key="goto_page"
                )
                if st.button("跳转", key="goto_page_button"):
                    st.session_state.page_number = page_input - 1
                    st.rerun()
        else:
            st.info("暂无测试用例，请点击上方按钮添加，或修改搜索条件")
        
        # 编辑选定的测试用例
        st.divider()
        
        if "selected_case_index" in st.session_state and st.session_state.selected_case_index is not None:
            i = st.session_state.selected_case_index
            
            if i < len(test_set["cases"]):
                case = test_set["cases"][i]
                
                st.subheader(f"✏️ 编辑测试用例: {case.get('description', f'用例{i+1}')}")
                
                # 基本信息行
                col1, col2, col3 = st.columns([1, 2, 1])
                with col1:
                    case["id"] = st.text_input("用例ID", value=case.get("id", f"case_{i+1}"), key=f"edit_id_{i}")
                with col2:
                    case["description"] = st.text_input(
                        "用例描述", 
                        value=case.get("description", ""), 
                        key=f"edit_desc_{i}"
                    )
                with col3:
                    if st.button("🗑️ 删除此测试用例", key=f"edit_del_case_{i}", use_container_width=True):
                        test_set["cases"].pop(i)
                        if "selected_case_index" in st.session_state:
                            del st.session_state.selected_case_index
                        st.success(f"已删除测试用例")
                        st.rerun()
                
                # 编辑区域的选项卡：变量、输入输出、评估标准
                edit_tab1, edit_tab2, edit_tab3 = st.tabs(["变量", "输入与期望输出", "评估标准"])
                
                with edit_tab1:
                    # 用例变量 - 使用简洁的布局
                    st.caption("这些变量仅适用于当前测试用例")
                    
                    # 初始化变量字典
                    if "variables" not in case or not isinstance(case["variables"], dict):
                        case["variables"] = {}
                    
                    # 显示现有变量
                    vars_to_remove = []
                    
                    if case["variables"]:
                        col1, col2, col3 = st.columns([1, 2, 0.5])
                        with col1:
                            st.write("**变量名**")
                        with col2:
                            st.write("**变量值**")
                        with col3:
                            st.write("**操作**")
                        
                        for var_name, var_value in case["variables"].items():
                            col1, col2, col3 = st.columns([1, 2, 0.5])
                            
                            with col1:
                                st.text(var_name)
                            
                            with col2:
                                new_value = st.text_input(
                                    f"值", 
                                    value=var_value,
                                    key=f"edit_var_{i}_{var_name}"
                                )
                                case["variables"][var_name] = new_value
                            
                            with col3:
                                if st.button("🗑️", key=f"edit_del_{i}_{var_name}"):
                                    vars_to_remove.append(var_name)
                    else:
                        st.info("暂无用例变量")
                    
                    # 移除标记为删除的变量
                    for var_name in vars_to_remove:
                        if var_name in case["variables"]:
                            del case["variables"][var_name]
                    
                    # 添加新变量
                    st.divider()
                    col1, col2, col3 = st.columns([1, 2, 0.8])
                    with col1:
                        new_var_name = st.text_input("新变量名", key=f"edit_new_var_name_{i}")
                    with col2:
                        new_var_value = st.text_input("新变量值", key=f"edit_new_var_value_{i}")
                    with col3:
                        if st.button("添加变量", key=f"edit_add_var_{i}", use_container_width=True) and new_var_name:
                            case["variables"][new_var_name] = new_var_value
                            st.success(f"已添加变量: {new_var_name}")
                            st.rerun()
                
                with edit_tab2:
                    # 用户输入和期望输出 - 并排显示
                    col1, col2 = st.columns(2)
                    
                    with col1:
                        st.subheader("用户输入")
                        case["user_input"] = st.text_area(
                            "用户输入内容", 
                            value=case.get("user_input", ""), 
                            height=300,
                            key=f"edit_user_input_{i}",
                            help="这是发送给模型的用户消息内容"
                        )
                    
                    with col2:
                        st.subheader("期望输出")
                        case["expected_output"] = st.text_area(
                            "期望输出内容", 
                            value=case.get("expected_output", ""), 
                            height=300,
                            key=f"edit_exp_{i}",
                            help="模型应该生成的理想输出"
                        )
                
                with edit_tab3:
                    # 评估标准 - 改进的编辑界面
                    
                    # 初始化评估标准字典
                    if "evaluation_criteria" not in case or not isinstance(case["evaluation_criteria"], dict):
                        case["evaluation_criteria"] = {
                            "accuracy": "评估准确性的标准",
                            "completeness": "评估完整性的标准",
                            "relevance": "评估相关性的标准",
                            "clarity": "评估清晰度的标准"
                        }
                    
                    # 评估标准表格布局
                    criteria_to_remove = []
                    
                    if case["evaluation_criteria"]:
                        criteria_items = list(case["evaluation_criteria"].items())
                        
                        for j, (crit_name, crit_value) in enumerate(criteria_items):
                            col1, col2 = st.columns([4, 1])
                            
                            with col1:
                                st.markdown(f"**{crit_name}**")
                                new_value = st.text_area(
                                    "标准描述", 
                                    value=crit_value,
                                    height=100,
                                    key=f"edit_crit_{i}_{crit_name}"
                                )
                                case["evaluation_criteria"][crit_name] = new_value
                            
                            with col2:
                                st.write("")  # 占位
                                if st.button("🗑️", key=f"edit_del_crit_{i}_{crit_name}", help=f"删除 {crit_name} 标准"):
                                    criteria_to_remove.append(crit_name)
                            
                            if j < len(criteria_items) - 1:
                                st.divider()
                    else:
                        st.info("暂无评估标准")
                    
                    # 移除标记为删除的评估标准
                    for crit_name in criteria_to_remove:
                        if crit_name in case["evaluation_criteria"]:
                            del case["evaluation_criteria"][crit_name]
                    
                    # 添加新评估标准 - 更紧凑的布局
                    st.divider()
                    st.subheader("添加新评估标准")
                    col1, col2, col3 = st.columns([1, 2, 1])
                    with col1:
                        new_crit_name = st.text_input("新标准名称", key=f"edit_new_crit_name_{i}", placeholder="输入标准名称")
                    with col2:
                        new_crit_value = st.text_area("新标准描述", key=f"edit_new_crit_value_{i}", placeholder="输入标准描述", height=100)
                    with col3:
                        st.write("")
                        if st.button("添加标准", key=f"edit_add_crit_{i}", disabled=not new_crit_name, use_container_width=True):
                            case["evaluation_criteria"][new_crit_name] = new_crit_value
                            st.success(f"已添加评估标准: {new_crit_name}")
                            st.rerun()
                    
                    # AI生成评估标准
                    st.divider()
                    ai_col1, ai_col2 = st.columns([1, 3])
                    with ai_col1:
                        if st.button("✨ AI生成评估标准", key=f"edit_ai_generate_criteria_{i}", use_container_width=True):
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
                                    # 强制页面刷新显示新生成的评估标准
                                    st.rerun()
                    
                    with ai_col2:
                        st.caption("说明: 根据用例描述、用户输入和期望输出自动生成标准格式的评估标准。评估分数范围为0-100分。")
            else:
                st.warning("选择的测试用例不存在，可能已被删除")
                if "selected_case_index" in st.session_state:
                    del st.session_state.selected_case_index
        else:
            st.info("👆 请从上方表格中选择一个测试用例进行编辑")