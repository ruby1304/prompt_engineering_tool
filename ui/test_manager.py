import streamlit as st
import json
import pandas as pd
from datetime import datetime
# 修改导入方式
from config import save_test_set, load_test_set, get_test_set_list

def render_test_manager():
    st.title("📊 测试集管理")
    
    # 侧边栏: 测试集列表
    with st.sidebar:
        st.subheader("测试集列表")
        
        test_set_list = get_test_set_list()
        
        if st.button("➕ 新建测试集"):
            st.session_state.current_test_set = {
                "name": f"新测试集_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
                "description": "",
                "variables": {},
                "cases": [
                    {
                        "id": "case_1",
                        "description": "测试用例1",
                        "variables": {},
                        "user_input": "这里填写用户的输入内容。",  # 新增用户输入字段
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
        
        if test_set_list:
            st.write("选择现有测试集:")
            for test_set_name in test_set_list:
                if st.button(f"📄 {test_set_name}", key=f"sel_{test_set_name}"):
                    st.session_state.current_test_set = load_test_set(test_set_name)
    
    # 主内容: 编辑区
    if not st.session_state.current_test_set:
        st.info("请从侧边栏创建新测试集或选择现有测试集")
        
        st.subheader("测试集示例")
        
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
    },
    {
      "id": "negative_1",
      "description": "强烈负面情感",
      "variables": {
        "text": "这是我经历过的最糟糕的服务，简直太可怕了。"
      },
      "expected_output": {
        "sentiment": "negative",
        "score": 0.85
      },
      "evaluation_criteria": {
        "accuracy": "情感判断必须是negative，分数在0.7-1.0之间",
        "completeness": "必须包含sentiment、score和analysis三个字段"
      }
    }
  ]
}
        """, language="json")
        
        return
    
    # 显示当前测试集编辑器
    test_set = st.session_state.current_test_set
    
    # 基本信息编辑
    col1, col2 = st.columns([2, 1])
    
    with col1:
        test_set["name"] = st.text_input("测试集名称", value=test_set["name"])
        test_set["description"] = st.text_area("测试集描述", value=test_set["description"], height=80)
    
    # 测试集全局变量
    st.subheader("测试集全局变量")
    st.caption("这些变量将应用于所有测试用例")
    
    # 初始化变量字典
    if "variables" not in test_set or not isinstance(test_set["variables"], dict):
        test_set["variables"] = {}
    
    # 显示现有全局变量
    global_vars_to_remove = []
    
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
    
    # 移除标记为删除的全局变量
    for var_name in global_vars_to_remove:
        if var_name in test_set["variables"]:
            del test_set["variables"][var_name]
    
    # 添加新全局变量
    with st.expander("添加新全局变量"):
        new_var_name = st.text_input("变量名称", key="new_global_var_name")
        new_var_value = st.text_input("变量值", key="new_global_var_value")
        
        if st.button("添加全局变量") and new_var_name:
            test_set["variables"][new_var_name] = new_var_value
            st.success(f"已添加全局变量: {new_var_name}")
            st.experimental_rerun()
    
    # 测试用例列表
    st.subheader("测试用例")
    
    # 初始化用例列表
    if "cases" not in test_set or not isinstance(test_set["cases"], list):
        test_set["cases"] = []
    
    # 显示用例表格概览
    case_data = []
    for case in test_set["cases"]:
        case_data.append({
            "ID": case.get("id", ""),
            "描述": case.get("description", ""),
            "变量数": len(case.get("variables", {})),
            "评估标准数": len(case.get("evaluation_criteria", {}))
        })
    
    if case_data:
        st.dataframe(pd.DataFrame(case_data), use_container_width=True)
    
    # 用例编辑区域
    for i, case in enumerate(test_set["cases"]):
        with st.expander(f"测试用例 {i+1}: {case.get('description', f'用例{i+1}')}"):
            col1, col2 = st.columns([1, 3])
            
            with col1:
                case["id"] = st.text_input("用例ID", value=case.get("id", f"case_{i+1}"), key=f"id_{i}")
            
            with col2:
                case["description"] = st.text_input(
                    "用例描述", 
                    value=case.get("description", ""), 
                    key=f"desc_{i}"
                )
            
            # 用例变量
            st.subheader("用例变量", anchor=f"vars_{i}")
            st.caption("这些变量仅适用于当前测试用例")
            
            # 初始化变量字典
            if "variables" not in case or not isinstance(case["variables"], dict):
                case["variables"] = {}
            
            # 显示现有变量
            vars_to_remove = []
            
            for var_name, var_value in case["variables"].items():
                col1, col2, col3 = st.columns([1, 2, 0.5])
                
                with col1:
                    st.text(var_name)
                
                with col2:
                    new_value = st.text_input(
                        f"值", 
                        value=var_value,
                        key=f"var_{i}_{var_name}"
                    )
                    case["variables"][var_name] = new_value
                
                with col3:
                    if st.button("🗑️", key=f"del_{i}_{var_name}"):
                        vars_to_remove.append(var_name)
            
            # 移除标记为删除的变量
            for var_name in vars_to_remove:
                if var_name in case["variables"]:
                    del case["variables"][var_name]
            
            # 添加新变量
            new_var_name = st.text_input("新变量名", key=f"new_var_name_{i}")
            new_var_value = st.text_input("新变量值", key=f"new_var_value_{i}")
            
            if st.button("添加变量", key=f"add_var_{i}") and new_var_name:
                case["variables"][new_var_name] = new_var_value
                st.success(f"已添加变量: {new_var_name}")
                st.experimental_rerun()
            
            # 在期望输出前添加用户输入
            st.subheader("用户输入", anchor=f"user_input_{i}")
            case["user_input"] = st.text_area(
                "用户输入内容", 
                value=case.get("user_input", ""), 
                height=100,
                key=f"user_input_{i}",
                help="这是发送给模型的用户消息内容"
            )
            
            # 期望输出
            st.subheader("期望输出", anchor=f"expected_{i}")
            
            case["expected_output"] = st.text_area(
                "期望输出内容", 
                value=case.get("expected_output", ""), 
                height=150,
                key=f"exp_{i}"
            )
            
            # 评估标准
            st.subheader("评估标准", anchor=f"criteria_{i}")
            
            # 初始化评估标准字典
            if "evaluation_criteria" not in case or not isinstance(case["evaluation_criteria"], dict):
                case["evaluation_criteria"] = {
                    "accuracy": "评估准确性的标准",
                    "completeness": "评估完整性的标准",
                    "relevance": "评估相关性的标准",
                    "clarity": "评估清晰度的标准"
                }
            
            # 显示现有评估标准
            criteria_to_remove = []
            
            for crit_name, crit_value in case["evaluation_criteria"].items():
                col1, col2, col3 = st.columns([1, 2, 0.5])
                
                with col1:
                    st.text(crit_name)
                
                with col2:
                    new_value = st.text_area(
                        f"标准描述", 
                        value=crit_value,
                        height=80,
                        key=f"crit_{i}_{crit_name}"
                    )
                    case["evaluation_criteria"][crit_name] = new_value
                
                with col3:
                    if st.button("🗑️", key=f"del_crit_{i}_{crit_name}"):
                        criteria_to_remove.append(crit_name)
            
            # 移除标记为删除的评估标准
            for crit_name in criteria_to_remove:
                if crit_name in case["evaluation_criteria"]:
                    del case["evaluation_criteria"][crit_name]
            
            # 添加新评估标准
            new_crit_name = st.text_input("新标准名称", key=f"new_crit_name_{i}")
            new_crit_value = st.text_area("新标准描述", height=80, key=f"new_crit_value_{i}")
            
            if st.button("添加评估标准", key=f"add_crit_{i}") and new_crit_name:
                case["evaluation_criteria"][new_crit_name] = new_crit_value
                st.success(f"已添加评估标准: {new_crit_name}")
                st.experimental_rerun()
            
            # 删除用例按钮
            if st.button("🗑️ 删除此测试用例", key=f"del_case_{i}"):
                test_set["cases"].pop(i)
                st.success(f"已删除测试用例")
                st.experimental_rerun()
    
    # 添加新测试用例
    if st.button("➕ 添加新测试用例"):
        new_case = {
            "id": f"case_{len(test_set['cases']) + 1}",
            "description": f"测试用例 {len(test_set['cases']) + 1}",
            "variables": {},
            "expected_output": "",
            "evaluation_criteria": {
                "accuracy": "评估准确性的标准",
                "completeness": "评估完整性的标准",
                "relevance": "评估相关性的标准",
                "clarity": "评估清晰度的标准"
            }
        }
        test_set["cases"].append(new_case)
        st.success("已添加新测试用例")
        st.experimental_rerun()
    
    # 导入导出功能
    st.divider()
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("导入测试集")
        
        upload_file = st.file_uploader("上传JSON测试集文件", type=["json"])
        if upload_file is not None:
            try:
                uploaded_test_set = json.load(upload_file)
                if st.button("确认导入"):
                    st.session_state.current_test_set = uploaded_test_set
                    st.success("测试集导入成功")
                    st.experimental_rerun()
            except json.JSONDecodeError:
                st.error("文件格式错误，请上传有效的JSON文件")
    
    with col2:
        st.subheader("导出测试集")
        
        if st.download_button(
            label="导出为JSON",
            data=json.dumps(test_set, ensure_ascii=False, indent=2),
            file_name=f"{test_set['name']}.json",
            mime="application/json"
        ):
            st.success("测试集已导出")
    
    # 保存按钮
    if st.button("💾 保存测试集", type="primary"):
        save_test_set(test_set["name"], test_set)
        st.success(f"测试集 '{test_set['name']}' 已保存")