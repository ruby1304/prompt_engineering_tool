# ui/components/layout.py
import streamlit as st

def page_header(title, description=None, icon=None):
    """页面标题组件
    
    Args:
        title: 页面标题
        description: 页面描述
        icon: 图标代码
    """
    title_text = f"{icon} {title}" if icon else title
    st.title(title_text)
    
    if description:
        st.markdown(description)
    
    st.divider()

def sidebar_section(title, content_func):
    """侧边栏分组
    
    Args:
        title: 分组标题
        content_func: 渲染内容的函数
    """
    with st.sidebar:
        st.markdown(f"## {title}")
        content_func()
        st.divider()

def tabs_section(tabs_config):
    """标签页组件
    
    Args:
        tabs_config: 标签页配置列表，每项为 {"title": 标签标题, "content": 内容渲染函数}
    """
    tab_titles = [tab["title"] for tab in tabs_config]
    tabs = st.tabs(tab_titles)
    
    for i, tab in enumerate(tabs):
        with tab:
            tabs_config[i]["content"]()
