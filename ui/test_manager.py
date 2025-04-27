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

def get_shortened_id(case_id):
    """从完整ID中提取缩短版用于显示
    
    Args:
        case_id (str): 完整的测试用例ID
        
    Returns:
        str: 缩短的ID，适合显示
    """
    if not case_id:
        return "未知ID"
        
    # 如果是自定义ID（不包含下划线），则直接返回
    if "_" not in case_id:
        return case_id
        
    # 如果是系统生成的ID (case_timestamp_uuid)，只返回uuid部分或截取部分
    parts = case_id.split("_")
    if len(parts) >= 3:
        return parts[-1][:6]  # 只显示UUID的前6位
    
    return case_id  # 无法解析时返回原始ID

def ensure_unique_id(case, existing_ids=None):
    """确保测试用例有唯一ID，如果重复或不存在则生成新ID
    
    Args:
        case (dict): 测试用例字典
        existing_ids (set): 已存在的ID集合
        
    Returns:
        str: 唯一的ID
    """
    if existing_ids is None:
        existing_ids = set()
        
    # 如果ID不存在或在现有ID集合中，生成新ID
    if not case.get("id") or case.get("id") in existing_ids:
        new_id = generate_unique_id()
        case["id"] = new_id
    
    # 返回唯一ID
    return case["id"]

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
                                ensure_unique_id(case, ids_seen)
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
                    if "cases" in uploaded_test_set:
                        ids_seen = set()
                        for case in uploaded_test_set["cases"]:
                            # 确保ID唯一
                            ensure_unique_id(case, ids_seen)
                            ids_seen.add(case["id"])
                            
                            # 确保基本字段存在
                            if "description" not in case:
                                case["description"] = "未命名测试用例"
                                
                            if "variables" not in case or not isinstance(case["variables"], dict):
                                case["variables"] = {}
                            
                            if "user_input" not in case:
                                case["user_input"] = ""
                                
                            if "expected_output" not in case:
                                case["expected_output"] = ""
                            
                            # 确保评估标准字段存在
                            if "evaluation_criteria" not in case or not isinstance(case["evaluation_criteria"], dict):
                                case["evaluation_criteria"] = {
                                    "accuracy": "评估准确性的标准",
                                    "completeness": "评估完整性的标准",
                                    "relevance": "评估相关性的标准",
                                    "clarity": "评估清晰度的标准"
                                }
                                
                    # 确保全局变量字段存在
                    if "variables" not in uploaded_test_set or not isinstance(uploaded_test_set["variables"], dict):
                        uploaded_test_set["variables"] = {}
                        
                    # 确保名称和描述字段存在
                    if "name" not in uploaded_test_set or not uploaded_test_set["name"]:
                        uploaded_test_set["name"] = f"导入测试集_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
                        
                    if "description" not in uploaded_test_set:
                        uploaded_test_set["description"] = "导入的测试集"
                        
                    if st.button("确认导入"):
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
        
        # 批量操作功能区
        with st.expander("🔄 批量操作", expanded=False):
            st.caption("对测试集中的多个测试用例执行批量操作")

            # 统一参数选择
            param_col1, param_col2, param_col3 = st.columns(3)
            with param_col1:
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
                from config import get_template_list, load_template
                template_list = get_template_list()
                selected_template_name = st.selectbox(
                    "选择提示词模板",
                    options=template_list,
                    key="batch_template"
                )
                template = load_template(selected_template_name) if selected_template_name else None
            with param_col3:
                temperature = st.slider("温度", 0.0, 1.0, 0.3, 0.1, key="batch_temp")

            # 四个批量操作按钮
            btn_col1, btn_col2, btn_col3, btn_col4 = st.columns(4)
            with btn_col1:
                gen_inputs_count = st.number_input("生成输入数量", min_value=1, max_value=1000, value=5, step=1, key="batch_gen_inputs_count")
                if st.button("💡 AI生成用户输入", use_container_width=True):
                    with st.spinner("AI正在生成用户输入..."):
                        test_set_desc = test_set.get("description", "通用测试") or "通用测试"
                        try:
                            evaluator = PromptEvaluator()
                            result = evaluator.generate_user_inputs(
                                test_set_desc,
                                gen_inputs_count
                            )
                            if "error" in result:
                                st.error(f"生成用户输入失败: {result['error']}")
                            else:
                                user_inputs = result.get("user_inputs", [])
                                added_count = 0
                                ids_seen = set(case.get("id", "") for case in test_set["cases"])
                                for user_input in user_inputs:
                                    if user_input:
                                        new_case = {
                                            "id": generate_unique_id(),
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
                                        ensure_unique_id(new_case, ids_seen)
                                        ids_seen.add(new_case["id"])
                                        test_set["cases"].append(new_case)
                                        added_count += 1
                                if added_count > 0:
                                    save_test_set(test_set["name"], test_set)
                                    st.success(f"成功生成并添加 {added_count} 个仅包含用户输入的测试用例到 '{test_set['name']}'")
                                    st.rerun()
                                else:
                                    st.warning("AI未能生成有效的用户输入。")
                        except Exception as e:
                            st.error(f"生成用户输入时发生异常: {e}")
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
                                ids_seen = set(case.get("id", "") for case in test_set["cases"])
                                for tc in test_cases:
                                    ensure_unique_id(tc, ids_seen)
                                    ids_seen.add(tc["id"])
                                    if "description" not in tc or not tc["description"]:
                                        tc["description"] = f"AI生成测试用例 {added_count + 1}"
                                    if "variables" not in tc:
                                        tc["variables"] = {}
                                    if "evaluation_criteria" not in tc:
                                        tc["evaluation_criteria"] = {
                                            "accuracy": "评估准确性的标准",
                                            "completeness": "评估完整性的标准",
                                            "relevance": "评估相关性的标准",
                                            "clarity": "评估清晰度的标准"
                                        }
                                    test_set["cases"].append(tc)
                                    added_count += 1
                                save_test_set(test_set["name"], test_set)
                                st.success(f"成功生成并添加 {added_count} 个测试用例到测试集 '{test_set['name']}' (目标: {gen_case_count})")
                                st.rerun()
                        except Exception as e:
                            st.error(f"生成测试用例时发生异常: {e}")
            with btn_col3:
                if st.button("✨ 批量生成优质输出", use_container_width=True):
                    if not selected_model or not template:
                        st.error("请选择模型和提示词模板")
                    else:
                        cases_to_fill = [case for case in test_set["cases"] if case.get("user_input") and not case.get("expected_output")]
                        if not cases_to_fill:
                            st.warning("没有找到需要生成预期输出的测试用例，所有测试用例已有预期输出或缺少用户输入")
                        else:
                            with st.spinner(f"正在为 {len(cases_to_fill)} 个测试用例生成预期输出..."):
                                from models.api_clients import get_client
                                import asyncio
                                client = get_client(selected_provider)
                                progress_bar = st.progress(0)
                                status_text = st.empty()
                                from utils.common import render_prompt_template
                                for i, case in enumerate(cases_to_fill):
                                    status_text.text(f"正在处理测试用例 {i+1}/{len(cases_to_fill)}: {case.get('description', 'Case '+str(i+1))}")
                                    prompt_template = render_prompt_template(template, test_set, case)
                                    user_input = case.get("user_input", "")
                                    try:
                                        loop = asyncio.new_event_loop()
                                        asyncio.set_event_loop(loop)
                                        if selected_provider in ["openai", "xai"]:
                                            response = loop.run_until_complete(client.generate_with_messages(
                                                [
                                                    {"role": "system", "content": prompt_template},
                                                    {"role": "user", "content": user_input}
                                                ],
                                                selected_model,
                                                {"temperature": temperature, "max_tokens": 1000}
                                            ))
                                        else:
                                            combined_prompt = f"System: {prompt_template}\n\nUser: {user_input}"
                                            response = loop.run_until_complete(client.generate(
                                                combined_prompt,
                                                selected_model,
                                                {"temperature": temperature, "max_tokens": 1000}
                                            ))
                                        loop.close()
                                        model_output = response.get("text", "")
                                        if model_output:
                                            for test_case in test_set["cases"]:
                                                if test_case.get("id") == case.get("id"):
                                                    test_case["expected_output"] = model_output
                                                    break
                                    except Exception as e:
                                        st.error(f"生成预期输出时出错: {str(e)}")
                                    progress_bar.progress((i + 1) / len(cases_to_fill))
                                status_text.text("✅ 批量生成预期输出完成!")
                                save_test_set(test_set["name"], test_set)
                                st.success(f"成功为 {len(cases_to_fill)} 个测试用例生成预期输出")
                                st.rerun()
            with btn_col4:
                if st.button("✨ 批量填充评估标准", use_container_width=True):
                    cases_to_fill = [case for case in test_set["cases"] if case.get("description") and case.get("user_input") and case.get("expected_output") and (not case.get("evaluation_criteria") or len(case.get("evaluation_criteria", {})) == 0)]
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
                            st.success(f"成功为 {len(cases_to_fill)} 个测试用例生成评估标准")
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
                        <div style="padding:10px; border:1px solid #f0f2f6; border-radius:5px; margin-bottom:10px; border-left:4px solid {'#FF4B4B' if 'current_case_id' in st.session_state and st.session_state.current_case_id == case.get('id', '') else 'transparent'}">
                            <h4 style="margin:0; font-size:0.95em">{get_shortened_id(case_id)}</h4>
                            <p style="margin:4px 0; font-size:0.95em">{case_desc}</p>
                            <p style="margin:4px 0; font-size:0.85em; color:#777; white-space:nowrap; overflow:hidden; text-overflow:ellipsis">{input_preview}</p>
                        </div>
                        """, unsafe_allow_html=True)
                        
                        # 添加查看按钮
                        # 在选择用例时保存case ID，不只是索引
                        if st.button("查看", key=f"view_btn_{real_index}"):
                            # 直接使用filtered_cases的索引而不是原始数组索引
                            selected_case = filtered_cases[real_index]
                            
                            # 找到这个用例在原始test_set中的索引，以支持编辑功能
                            original_index = -1
                            for i, original_case in enumerate(test_set["cases"]):
                                if original_case.get("id") == selected_case.get("id"):
                                    original_index = i
                                    break
                            
                            # 保存到会话状态
                            st.session_state.current_case = dict(selected_case)  # 使用深拷贝
                            st.session_state.current_case_index = original_index  # 保存原始索引
                            st.session_state.current_case_id = selected_case.get("id", "")  # 保存case ID用于高亮显示
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
                case_index = st.session_state.current_case_index
                
                # 修复：从测试集重新获取最新的用例数据，而不是使用会话状态中的旧数据
                if 0 <= case_index < len(test_set["cases"]):
                    # 使用索引从测试集中获取最新的用例数据
                    case = test_set["cases"][case_index]
                    # 更新会话状态中的当前用例
                    st.session_state.current_case = dict(case)
                else:
                    # 如果索引无效，使用会话状态中的用例数据
                    case = st.session_state.current_case
                
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
                        
                        # 清理会话状态
                        if "current_case" in st.session_state:
                            del st.session_state.current_case
                        if "current_case_index" in st.session_state:
                            del st.session_state.current_case_index
                            
                        # 重新应用过滤和排序
                        filtered_cases = test_set["cases"]
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
                        if sort_by in sort_options:
                            filtered_cases = sort_options[sort_by](filtered_cases)
                        
                        # 更新总页数
                        total_pages = max(1, (len(filtered_cases) + page_size - 1) // page_size)
                        
                        # 更新页码，如果当前页为空则回到上一页
                        if st.session_state.page_number >= total_pages:
                            st.session_state.page_number = max(0, total_pages - 1)
                            
                        # 自动保存测试集，确保删除操作被持久化
                        try:
                            save_test_set(test_set["name"], test_set)
                            st.success("测试用例已删除并保存")
                        except Exception as e:
                            st.error(f"删除测试用例后保存失败: {str(e)}")
                            
                        st.rerun()
                
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
                        from config import get_template_list, load_template
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
                                # 调用重新生成函数
                                from utils.common import regenerate_expected_output
                                result = regenerate_expected_output(
                                    case=case,
                                    template=template,
                                    model=selected_model,
                                    provider=selected_provider,
                                    temperature=temperature
                                )
                                
                                if "error" in result:
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
                                        st.text_area("", value=generated_text, height=200, key=f"new_output_{case_index}", disabled=True)
                                        
                                        if st.button("✅ 确认使用此输出", key=f"confirm_new_output_{case_index}"):
                                            # 将生成的输出设置为测试用例的期望输出
                                            for test_case in test_set["cases"]:
                                                if test_case.get("id") == case.get("id"):
                                                    test_case["expected_output"] = generated_text
                                                    break
                                            
                                            # 更新会话状态和UI显示
                                            st.session_state.current_case["expected_output"] = generated_text
                                            # 更新编辑表单中的字段值，这样UI会立即反映新值
                                            st.session_state[f"edit_output_{case_index}"] = generated_text
                                            
                                            # 自动保存测试集
                                            save_test_set(test_set["name"], test_set)
                                            st.success("✅ 已更新期望输出并保存")
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
                    # Get the index and the test_set from session state
                    case_index = st.session_state.current_case_index
                    test_set = st.session_state.current_test_set

                    # 验证索引有效性
                    if 0 <= case_index < len(test_set["cases"]):
                        # 检查ID是否唯一
                        current_id = test_set["cases"][case_index].get("id", "")
                        ids_seen = set()
                        for i, other_case in enumerate(test_set["cases"]):
                            if i != case_index:  # 除了当前用例
                                ids_seen.add(other_case.get("id", ""))
                        
                        # 如果ID为空或冲突，生成新ID
                        if not new_id or new_id in ids_seen:
                            new_id = generate_unique_id()
                            st.warning(f"检测到ID冲突或为空，已自动生成新ID: {new_id}")
                        
                        # 获取直接引用以更新用例
                        case_to_update = test_set["cases"][case_index]

                        # 使用输入小部件的值更新字典
                        case_to_update["id"] = new_id
                        case_to_update["description"] = new_desc or "未命名测试用例"
                        case_to_update["user_input"] = new_user_input
                        case_to_update["expected_output"] = new_expected_output
                        
                        # 更新会话状态中的当前用例以反映最新编辑
                        st.session_state.current_case = dict(case_to_update)
                        
                        # 从会话状态中可能修改的其他部分更新变量和评估标准
                        # 首先确保字段存在
                        if "variables" not in case_to_update:
                            case_to_update["variables"] = {}
                        if "evaluation_criteria" not in case_to_update:
                            case_to_update["evaluation_criteria"] = {}
                            
                        # 确保当前编辑的用例保持同步
                        current_edited_case = st.session_state.current_case
                        for var_name, var_value in current_edited_case.get("variables", {}).items():
                            case_to_update["variables"][var_name] = var_value
                            
                        for crit_name, crit_value in current_edited_case.get("evaluation_criteria", {}).items():
                            case_to_update["evaluation_criteria"][crit_name] = crit_value
                        
                        # 自动保存测试集
                        try:
                            save_test_set(test_set["name"], test_set)
                            st.success("✅ 测试用例已保存")
                        except Exception as e:
                            st.error(f"保存测试用例失败: {str(e)}")
                        
                        # 重新运行以刷新UI
                        st.rerun()
                    else:
                        st.error(f"保存失败：无效的测试用例索引 {case_index}")

            else:
                # 显示提示
                st.info("👈 请从左侧列表选择一个测试用例进行查看和编辑")