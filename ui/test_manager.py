# ui/test_manager.py
import streamlit as st
import json
import pandas as pd
from datetime import datetime
from config import save_test_set, load_test_set, get_test_set_list
from ui.components.layout import page_header, sidebar_section, tabs_section
from ui.components.cards import info_card, display_test_case_details
from ui.components.tables import results_table
from ui.components.forms import test_set_form, test_case_form

def render_test_manager():
    """测试集管理页面"""
    # 添加重置按钮
    if st.sidebar.button("🔄 重置编辑状态", key="reset_test_edit"):
        # 清除测试集相关的会话状态
        if "current_test_set" in st.session_state:
            del st.session_state.current_test_set
        if "editing_test_case" in st.session_state:
            del st.session_state.editing_test_case
        st.sidebar.success("编辑状态已重置!")
        st.experimental_rerun()
    
    # 使用布局组件显示页面标题
    page_header("测试集管理", "创建和管理测试用例集", "📊")
    
    # 定义侧边栏测试集列表渲染函数
    def render_test_set_list():
        """渲染测试集列表到侧边栏"""
        test_set_list = get_test_set_list()
        
        if st.button("➕ 新建测试集", use_container_width=True):
            # 创建新测试集
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
            st.session_state.editing_new_test_set = True
        
        # 显示现有测试集列表
        if test_set_list:
            st.markdown("### 现有测试集")
            
            for test_set_name in test_set_list:
                if st.button(f"📋 {test_set_name}", key=f"sel_{test_set_name}", use_container_width=True):
                    try:
                        # 加载选中的测试集
                        loaded_test_set = load_test_set(test_set_name)
                        if loaded_test_set is None:
                            st.error(f"无法加载测试集: {test_set_name}")
                        else:
                            st.session_state.current_test_set = loaded_test_set
                            st.session_state.editing_new_test_set = False
                    except Exception as e:
                        st.error(f"加载测试集时出错: {str(e)}")
        else:
            st.info("暂无测试集，请创建新测试集")
    
    # 使用布局组件显示侧边栏
    sidebar_section("测试集", render_test_set_list)
    
    # 主内容区：测试集编辑
    if "current_test_set" in st.session_state:
        test_set = st.session_state.current_test_set
        
        # 检查测试集是否有效
        if test_set is None:
            st.error("无效的测试集数据。创建一个新测试集...")
            # 创建默认测试集
            test_set = {
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
            st.session_state.current_test_set = test_set
            st.session_state.editing_new_test_set = True
        
        # 显示当前编辑的测试集信息
        editing_status = "新测试集" if st.session_state.get("editing_new_test_set", False) else "现有测试集"
        st.markdown(f"### 当前编辑: {test_set.get('name', '未命名测试集')} ({editing_status})")
        
        # 定义测试集基本信息和测试用例管理的标签页
        def render_test_set_info():
            """渲染测试集基本信息标签页"""
            
            # 定义保存测试集的回调函数
            def on_test_set_save(updated_test_set):
                try:
                    # 保存测试集到配置
                    save_test_set(updated_test_set)
                    # 更新会话状态
                    st.session_state.current_test_set = updated_test_set
                    st.session_state.editing_new_test_set = False
                    return True
                except Exception as e:
                    st.error(f"保存测试集时出错: {str(e)}")
                    return False
            
            # 使用测试集表单组件
            test_set_form(test_set, on_save=on_test_set_save, key_prefix="test_set")
        
        def render_test_cases():
            """渲染测试用例管理标签页"""
            st.markdown("## 测试用例管理")
            
            # 显示现有测试用例
            cases = test_set.get("cases", [])
            if not cases:
                st.info("当前测试集没有测试用例，请添加新用例")
            else:
                st.markdown(f"### 现有测试用例 ({len(cases)}个)")
                
                # 创建测试用例摘要表格
                case_summaries = []
                for case in cases:
                    case_summaries.append({
                        "ID": case.get("id", ""),
                        "描述": case.get("description", ""),
                        "输入长度": len(case.get("user_input", "")),
                        "期望输出长度": len(case.get("expected_output", "")),
                        "评估标准数": len(case.get("evaluation_criteria", {}))
                    })
                
                if case_summaries:
                    df = pd.DataFrame(case_summaries)
                    st.dataframe(df, use_container_width=True)
            
            # 添加新测试用例按钮
            if st.button("➕ 添加新测试用例", key="add_new_case"):
                # 生成唯一ID
                case_id = f"case_{len(cases) + 1}"
                # 检查ID是否已存在
                existing_ids = [case.get("id") for case in cases]
                while case_id in existing_ids:
                    # 如果ID已存在，增加数字
                    case_num = int(case_id.split("_")[1]) + 1
                    case_id = f"case_{case_num}"
                
                # 创建新测试用例
                new_case = {
                    "id": case_id,
                    "description": f"测试用例{len(cases) + 1}",
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
                
                # 添加到测试集
                cases.append(new_case)
                st.session_state.current_test_set["cases"] = cases
                # 设置为当前编辑的测试用例
                st.session_state.editing_test_case = new_case
                st.experimental_rerun()
            
            # 编辑选定的测试用例
            st.markdown("---")
            
            # 如果有测试用例，显示选择器
            if cases:
                case_options = [f"{case.get('id', '')} - {case.get('description', '')}" for case in cases]
                selected_case_option = st.selectbox(
                    "选择要编辑的测试用例",
                    case_options,
                    key="select_case_to_edit"
                )
                
                # 获取选中的测试用例
                selected_case_id = selected_case_option.split(" - ")[0] if selected_case_option else None
                selected_case = next((case for case in cases if case.get("id") == selected_case_id), None)
                
                if selected_case:
                    st.session_state.editing_test_case = selected_case
            
            # 如果正在编辑测试用例，显示编辑表单
            if "editing_test_case" in st.session_state and st.session_state.editing_test_case:
                edit_case = st.session_state.editing_test_case
                
                st.markdown(f"### 编辑测试用例: {edit_case.get('id', '')} - {edit_case.get('description', '')}")
                
                # 定义保存测试用例的回调函数
                def on_case_save(updated_case):
                    # 更新测试集中的用例
                    for i, case in enumerate(cases):
                        if case.get("id") == updated_case.get("id"):
                            cases[i] = updated_case
                            break
                    
                    # 如果是新用例（不在列表中），则添加
                    if not any(case.get("id") == updated_case.get("id") for case in cases):
                        cases.append(updated_case)
                    
                    # 更新会话状态
                    st.session_state.current_test_set["cases"] = cases
                    st.session_state.editing_test_case = updated_case
                    return True
                
                # 定义删除测试用例的回调函数
                def on_case_delete(case_id):
                    # 从测试集中删除用例
                    for i, case in enumerate(cases):
                        if case.get("id") == case_id:
                            del cases[i]
                            break
                    
                    # 更新会话状态
                    st.session_state.current_test_set["cases"] = cases
                    if "editing_test_case" in st.session_state:
                        del st.session_state.editing_test_case
                    return True
                
                # 使用测试用例表单组件
                test_case_form(edit_case, on_save=on_case_save, on_delete=on_case_delete, key_prefix="edit_case")
            else:
                if cases:
                    st.info("请从上方选择一个测试用例进行编辑")
                else:
                    st.info("请先添加一个测试用例")
        
        def render_test_preview():
            """渲染测试集预览标签页"""
            st.markdown("## 测试集预览")
            
            # 显示测试集基本信息
            info_card(
                "测试集信息",
                f"""
                **名称**: {test_set.get('name', '未命名')}
                
                **描述**: {test_set.get('description', '无描述')}
                
                **测试用例数**: {len(test_set.get('cases', []))}
                """
            )
            
            # 显示测试用例列表
            st.markdown("### 测试用例列表")
            cases = test_set.get("cases", [])
            
            if not cases:
                st.info("当前测试集没有测试用例")
            else:
                for i, case in enumerate(cases):
                    with st.expander(f"{case.get('id', '')} - {case.get('description', '')}", expanded=i==0):
                        display_test_case_details(case, key_prefix=f"preview_case_{i}")
        
        # 设置标签页
        tabs_config = [
            {"title": "基本信息", "content": render_test_set_info},
            {"title": "测试用例管理", "content": render_test_cases},
            {"title": "预览", "content": render_test_preview}
        ]
        
        tabs_section(tabs_config)
    else:
        # 如果没有选择测试集，显示使用提示
        st.info("👈 请从侧边栏选择一个现有测试集或创建新测试集")
        
        info_card(
            "测试集说明", 
            """
            **测试集**是用于评估提示词效果的一组测试用例。通过创建测试集，您可以：
            
            1. **系统化**测试不同场景下的提示词效果
            2. **标准化**评估标准和期望输出
            3. **批量评估**多个模型或提示词的性能
            4. **量化比较**优化前后的效果变化
            
            点击左侧的"新建测试集"按钮开始创建您的第一个测试集！
            """
        )
