import streamlit as st
import json
from datetime import datetime
# 修改导入方式
from config import (
    save_template, 
    load_template, 
    get_template_list, 
    get_system_template_list,
    get_system_template,
    DEFAULT_SYSTEM_TEMPLATES
)
from models.token_counter import count_tokens

def render_prompt_editor():
    st.title("📝 提示词编辑器")
    
    # 添加一个选项卡，分离普通模板和系统模板
    tab_user, tab_system = st.tabs(["用户提示词模板", "系统提示词模板"])
    
    with tab_user:
        render_user_templates()
        
    with tab_system:
        render_system_templates()

def render_user_templates():
    """渲染普通用户提示词模板编辑器"""
    
    # 侧边栏: 模板列表
    col_left, col_right = st.columns([1, 3])
    
    with col_left:
        st.subheader("提示词模板")
        
        template_list = get_template_list()
        
        if st.button("➕ 新建模板", key="new_user_template"):
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
            st.session_state.editing_system_template = False
        
        if template_list:
            st.write("选择现有模板:")
            for template_name in template_list:
                if st.button(f"📄 {template_name}", key=f"sel_{template_name}"):
                    st.session_state.current_prompt_template = load_template(template_name)
                    st.session_state.editing_system_template = False
    
    with col_right:
        # 主内容: 编辑区
        if not st.session_state.get("current_prompt_template") or st.session_state.get("editing_system_template", False):
            st.info("请从左侧创建新模板或选择现有模板")
            
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
        render_template_editor(st.session_state.current_prompt_template)

def render_system_templates():
    """渲染系统提示词模板编辑器"""
    
    st.info("""
    ⚠️ **这些是系统内部使用的提示词模板** ⚠️
    
    修改这些模板将影响系统的评估、优化和标准生成过程。谨慎编辑，确保保留必要的变量。
    优化这些提示词可以提高工具自身的性能和评估质量。
    """)
    
    # 创建选择器和说明
    system_template_list = get_system_template_list()
    template_types = {
        "evaluator_template": "评估模型响应的提示词模板",
        "optimizer_template": "优化提示词的提示词模板",
        "criteria_generator_template": "生成评估标准的提示词模板"
    }
    
    # 分列布局
    col_left, col_right = st.columns([1, 3])
    
    with col_left:
        st.subheader("系统提示词")
        
        for template_name in system_template_list:
            description = template_types.get(template_name, "系统提示词模板")
            if st.button(f"⚙️ {template_name}", key=f"sys_{template_name}", help=description):
                try:
                    st.session_state.current_prompt_template = load_template(template_name)
                    st.session_state.editing_system_template = True
                    st.session_state.system_template_type = template_name
                except FileNotFoundError:
                    # 如果文件不存在，使用默认模板
                    st.session_state.current_prompt_template = DEFAULT_SYSTEM_TEMPLATES[template_name]
                    st.session_state.editing_system_template = True
                    st.session_state.system_template_type = template_name
        
        # 添加重置按钮
        st.divider()
        if st.button("🔄 重置为默认值", key="reset_system_templates"):
            for template_name, template_data in DEFAULT_SYSTEM_TEMPLATES.items():
                save_template(template_name, template_data)
            st.success("已重置所有系统提示词模板为默认值")
            # 如果正在编辑系统模板，重新加载
            if st.session_state.get("editing_system_template", False) and st.session_state.get("system_template_type"):
                st.session_state.current_prompt_template = DEFAULT_SYSTEM_TEMPLATES[st.session_state.system_template_type]
    
    with col_right:
        # 编辑当前选择的系统模板
        if st.session_state.get("editing_system_template", False) and st.session_state.get("current_prompt_template"):
            template = st.session_state.current_prompt_template
            st.subheader(f"编辑 {template['name']} - 系统提示词")
            st.caption(template_types.get(template['name'], "系统提示词模板"))
            
            render_template_editor(template)
        else:
            st.info("请从左侧选择一个系统提示词模板进行编辑")

def render_template_editor(template):
    """渲染提示词模板编辑器 - 共同部分"""
    col1, col2 = st.columns([3, 1])
    
    with col1:
        template["name"] = st.text_input("模板名称", value=template["name"], disabled=template.get("is_system", False))
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
                key=f"desc_{var_name}_{template['name']}"
            )
            var_info["default"] = st.text_input(
                f"默认值", 
                value=var_info["default"],
                key=f"def_{var_name}_{template['name']}"
            )
        
        with col3:
            if st.button("🗑️", key=f"del_{var_name}_{template['name']}"):
                variables_to_remove.append(var_name)
    
    # 移除标记为删除的变量
    for var_name in variables_to_remove:
        if var_name in template["variables"]:
            del template["variables"][var_name]
    
    # 添加新变量
    st.divider()
    
    with st.expander("添加新变量"):
        new_var_name = st.text_input("变量名称", key=f"new_var_name_{template['name']}")
        new_var_desc = st.text_input("变量描述", key=f"new_var_desc_{template['name']}")
        new_var_default = st.text_input("变量默认值", key=f"new_var_default_{template['name']}")
        
        if st.button("添加变量", key=f"add_var_{template['name']}") and new_var_name:
            template["variables"][new_var_name] = {
                "description": new_var_desc,
                "default": new_var_default
            }
            st.success(f"已添加变量: {new_var_name}")
            st.rerun()
    
    # 预览
    st.subheader("预览")
    
    preview_template = template["template"]
    for var_name, var_info in template["variables"].items():
        preview_template = preview_template.replace(f"{{{{{var_name}}}}}", var_info["default"])
    
    st.code(preview_template)
    
    # 保存按钮
    if st.button("💾 保存模板", key=f"save_{template['name']}", type="primary"):
        # 如果是系统模板，确保设置is_system标志
        if st.session_state.get("editing_system_template", False):
            template["is_system"] = True
        
        save_template(template["name"], template)
        st.success(f"模板 '{template['name']}' 已保存")