# ui/state_manager.py
import streamlit as st
from datetime import datetime
from config import save_template, load_template, get_template_list

class StateManager:
    """统一管理Streamlit会话状态"""
    
    @staticmethod
    def initialize():
        """初始化全局状态"""
        if "current_page" not in st.session_state:
            st.session_state.current_page = "home"
    
    @staticmethod
    def navigate_to(page):
        """页面导航"""
        st.session_state.current_page = page
    
    @staticmethod
    def get_current_page():
        """获取当前页面"""
        return st.session_state.current_page
    
    # 模板相关状态管理
    class TemplateState:
        @staticmethod
        def get_current():
            """获取当前模板"""
            return st.session_state.get("current_prompt_template")
        
        @staticmethod
        def set_current(template):
            """设置当前模板"""
            st.session_state.current_prompt_template = template
        
        @staticmethod
        def create_new():
            """创建新模板"""
            new_template = {
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
            st.session_state.current_prompt_template = new_template
            return new_template
        
        @staticmethod
        def save():
            """保存当前模板"""
            if "current_prompt_template" in st.session_state:
                save_template(st.session_state.current_prompt_template)
                return True
            return False
    
    # 测试相关状态管理
    class TestState:
        # 类似的测试状态管理方法...
        pass
