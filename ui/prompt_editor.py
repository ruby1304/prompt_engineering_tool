# ui/prompt_editor.py
import streamlit as st
from datetime import datetime
from config import save_template, load_template, get_template_list
from models.token_counter import count_tokens
from ui.components.layout import page_header, sidebar_section
from ui.components.cards import template_card, info_card
from ui.components.forms import template_form

def render_prompt_editor():
    """提示词编辑器页面"""
    # 使用布局组件显示页面标题
    page_header("提示词编辑器", "创建和管理提示词模板", "📝")
    
    # 定义侧边栏模板列表渲染函数
    def render_template_list():
        """渲染模板列表到侧边栏"""
        template_list = get_template_list()
        
        if st.button("➕ 新建模板", use_container_width=True):
            # 创建新模板
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
            # 在侧边栏中添加状态标记，表示我们正在编辑一个新模板
            st.session_state.editing_new_template = True
        
        # 显示现有模板列表
        if template_list:
            st.markdown("### 现有模板")
            
            for template_name in template_list:
                if st.button(f"📄 {template_name}", key=f"sel_{template_name}", use_container_width=True):
                    # 加载选中的模板
                    st.session_state.current_prompt_template = load_template(template_name)
                    st.session_state.editing_new_template = False
        else:
            st.info("暂无模板，请创建新模板")
    
    # 使用布局组件显示侧边栏
    sidebar_section("提示词模板", render_template_list)
    
    # 主内容区：模板编辑
    if "current_prompt_template" in st.session_state:
        template = st.session_state.current_prompt_template

        # 检查模板是否有效
        if template is None:
            st.error("无效的模板数据。创建一个新模板...")
            # 创建默认模板
            template = {
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
            st.session_state.current_prompt_template = template
            st.session_state.editing_new_template = True

        # 添加额外的安全检查，确保template不是None且是字典类型
        if not isinstance(template, dict):
            st.error(f"模板数据格式错误: {type(template)}。创建一个新模板...")
            template = {
                "name": f"新模板_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
                "description": "",
                "template": "",
                "variables": {}
            }
            st.session_state.current_prompt_template = template
            st.session_state.editing_new_template = True

        # 显示当前编辑的模板信息 - 修复此处
        editing_status = "新模板" if st.session_state.get("editing_new_template", False) else "现有模板"
        template_name = template.get('name', '未命名模板') if template else '未命名模板'
        st.markdown(f"### 当前编辑: {template_name} ({editing_status})")
        
        # 定义保存模板的回调函数
        def on_template_save(updated_template):
            try:
                # 检查模板名称
                template_name = updated_template.get("name")
                if not template_name:
                    st.error("模板名称不能为空")
                    return False
                
                # 保存模板到配置
                save_template(template_name, updated_template)  # 添加模板名称作为第一个参数
                
                # 更新会话状态
                st.session_state.current_prompt_template = updated_template
                st.session_state.editing_new_template = False
                return True
            except Exception as e:
                st.error(f"保存模板时出错: {str(e)}")
                return False

        
        # 使用表单组件编辑模板
        col1, col2 = st.columns([3, 2])
        
        with col1:
            # 使用模板表单组件
            updated = template_form(template, on_save=on_template_save, key_prefix="editor")
        
        with col2:
            # 模板预览
            if template.get("template"):
                st.markdown("### 模板预览")
                
                # 计算tokens
                token_count = count_tokens(template.get("template", ""))
                st.caption(f"估计Token数量: {token_count}")
                
                # 使用模板卡片组件显示预览
                template_card(template, show_variables=True, key_prefix="preview")
                
                # 显示变量使用提示
                info_card(
                    "变量用法提示", 
                    """
                    **变量格式**: 在模板中使用 `{{变量名}}` 格式插入变量。
                    
                    **示例**:
                    ```
                    你是一个{{角色}}。
                    任务：{{任务}}
                    ```
                    
                    变量会在测试和使用时替换为实际值。
                    """
                )
            else:
                st.info("请在左侧编辑模板内容以查看预览")
    else:
        # 如果没有选择模板，显示使用提示
        st.info("👈 请从侧边栏选择一个现有模板或创建新模板")
        
        info_card(
            "提示词模板说明", 
            """
            **提示词模板**是用于生成AI提示词的可复用结构。通过使用模板和变量，您可以：
            
            1. **标准化**提示词结构
            2. **快速生成**不同场景的提示词
            3. **批量测试**不同变量取值的效果
            4. **优化迭代**核心提示词结构
            
            点击左侧的"新建模板"按钮开始创建您的第一个模板！
            """
        )
