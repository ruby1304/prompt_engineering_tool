# ui/components/charts.py
import streamlit as st
import plotly.express as px
import plotly.graph_objects as go
import pandas as pd

def score_radar_chart(scores, title="评分雷达图", key_prefix=""):
    """分数雷达图
    
    Args:
        scores: 评分字典 {维度名称: 分数值}
        title: 图表标题
        key_prefix: 组件键前缀
    """
    # 准备数据
    categories = list(scores.keys())
    values = list(scores.values())
    
    # 确保数据闭环
    categories.append(categories[0])
    values.append(values[0])
    
    # 创建雷达图
    fig = go.Figure()
    
    fig.add_trace(go.Scatterpolar(
        r=values,
        theta=categories,
        fill='toself',
        name='得分'
    ))
    
    fig.update_layout(
        polar=dict(
            radialaxis=dict(
                visible=True,
                range=[0, 10]
            )
        ),
        title=title
    )
    
    # 显示图表
    st.plotly_chart(fig, use_container_width=True, key=f"{key_prefix}_radar")

def comparison_bar_chart(data, x_col, y_col, color_col, title="比较图", key_prefix=""):
    """通用比较条形图
    
    Args:
        data: 数据DataFrame或字典列表
        x_col: X轴列名
        y_col: Y轴列名
        color_col: 颜色分组列名
        title: 图表标题
        key_prefix: 组件键前缀
    """
    # 确保数据是DataFrame
    if not isinstance(data, pd.DataFrame):
        data = pd.DataFrame(data)
    
    # 创建条形图
    fig = px.bar(
        data, 
        x=x_col, 
        y=y_col, 
        color=color_col,
        title=title,
        barmode='group'
    )
    
    # 显示图表
    st.plotly_chart(fig, use_container_width=True, key=f"{key_prefix}_bar")
