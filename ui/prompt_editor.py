import streamlit as st
import json
from datetime import datetime
# 修改导入方式
from config import save_template, load_template, get_template_list
from models.token_counter import count_tokens

def render_prompt_editor():
    st.title("📝 提示词编辑器")
    
    # 侧边栏: 模板列表
    with st.sidebar:
        st.subheader("提示词模板")
        
        template_list = get_template_list()
        
        if st.button("➕ 新建模板"):
            st.session_state.current_prompt_template = {
                "name": f"新模板_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
                "description": "",
                "template": "你是一个{{角色}}。\n\n任务：{{任务}}",
                "variables": {
                    "角色": {
                        "description": "助手的角色",
                        "default": "helpful assistant"
                    },
                    "任务": {
                        "description": "需要完成的任务",
                        "default": "请回答用户的问题"
                    }
                }
            }
        
        if template_list:
            st.write("选择现有模板:")
            for template_name in template_list:
                if st.button(f"📄 {template_name}", key=f"sel_{template_name}"):
                    st.session_state.current_prompt_template = load_template(template_name)
    
    # 主内容: 编辑区
    if not st.session_state.current_prompt_template:
        st.info("请从侧边栏创建新模板或选择现有模板")
        
        st.subheader("提示词模板示例")
        
        st.code("""
{
  "name": "情感分析模板",
  "description": "用于情感分析的提示词模板",
  "template": "你是一个情感分析专家。\n\n请分析以下文本的情感:\n\n{{文本}}\n\n请以JSON格式返回结果，包含以下字段:\n- sentiment: 情感(positive/negative/neutral)\n- score: 情感强度(0-1)\n- analysis: 简要分析",
  "variables": {
    "文本": {
      "description": "需要分析的文本内容",
      "default": "我今天感觉特别开心，一切都很顺利！"
    }
  }
}
        """, language="json")
        
        return
    
    # 显示当前模板编辑器
    template = st.session_state.current_prompt_template
    
    col1, col2 = st.columns([3, 1])
    
    with col1:
        template["name"] = st.text_input("模板名称", value=template["name"])
        template["description"] = st.text_area("模板描述", value=template["description"], height=80)
    
    with col2:
        token_count = count_tokens(template["template"])
        st.metric("Token数量", token_count)
        
        for model in ["gpt-3.5-turbo", "gpt-4"]:
            cost = format(count_tokens(template["template"]) / 1000 * 0.01, '.4f')
            st.write(f"{model}: 约${cost}美元/次")
    
    st.subheader("提示词模板")
    template["template"] = st.text_area(
        "编辑模板内容", 
        value=template["template"],
        height=300,
        help="使用{{变量名}}格式插入变量"
    )
    
    st.subheader("变量设置")
    
    # 提取模板中的变量
    import re
    variables_in_template = re.findall(r'\{\{(\w+)\}\}', template["template"])
    
    # 初始化变量字典
    if "variables" not in template or not isinstance(template["variables"], dict):
        template["variables"] = {}
    
    # 自动添加新发现的变量
    for var in variables_in_template:
        if var not in template["variables"]:
            template["variables"][var] = {
                "description": "",
                "default": ""
            }
    
    # 显示变量编辑器
    variables_to_remove = []
    
    for var_name, var_info in template["variables"].items():
        col1, col2, col3 = st.columns([1, 2, 0.5])
        
        with col1:
            st.text(var_name)
            if var_name not in variables_in_template:
                st.caption("⚠️ 未在模板中使用")
        
        with col2:
            var_info["description"] = st.text_input(
                f"描述", 
                value=var_info["description"],
                key=f"desc_{var_name}"
            )
            var_info["default"] = st.text_input(
                f"默认值", 
                value=var_info["default"],
                key=f"def_{var_name}"
            )
        
        with col3:
            if st.button("🗑️", key=f"del_{var_name}"):
                variables_to_remove.append(var_name)
    
    # 移除标记为删除的变量
    for var_name in variables_to_remove:
        if var_name in template["variables"]:
            del template["variables"][var_name]
    
    # 添加新变量
    st.divider()
    
    with st.expander("添加新变量"):
        new_var_name = st.text_input("变量名称")
        new_var_desc = st.text_input("变量描述")
        new_var_default = st.text_input("变量默认值")
        
        if st.button("添加变量") and new_var_name:
            template["variables"][new_var_name] = {
                "description": new_var_desc,
                "default": new_var_default
            }
            st.success(f"已添加变量: {new_var_name}")
            st.experimental_rerun()
    
    # 预览
    st.subheader("预览")
    
    preview_template = template["template"]
    for var_name, var_info in template["variables"].items():
        preview_template = preview_template.replace(f"{{{{{var_name}}}}}", var_info["default"])
    
    st.code(preview_template)
    
    # 保存按钮
    if st.button("💾 保存模板", type="primary"):
        save_template(template["name"], template)
        st.success(f"模板 '{template['name']}' 已保存")