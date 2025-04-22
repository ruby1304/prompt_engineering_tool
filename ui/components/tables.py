# ui/components/tables.py
import streamlit as st
import pandas as pd

def results_table(results, key_prefix=""):
    """通用结果表格组件
    
    Args:
        results: 结果数据字典或列表
        key_prefix: 组件键前缀，用于唯一标识
    """
    if not results:
        st.info("暂无数据")
        return
    
    # 转换为DataFrame
    if isinstance(results, dict):
        df = pd.DataFrame(results.items(), columns=["指标", "值"])
    else:
        df = pd.DataFrame(results)
    
    # 显示表格
    st.dataframe(df, use_container_width=True, key=f"{key_prefix}_table")

def evaluation_metrics_table(evaluation, key_prefix=""):
    """评估指标表格
    
    Args:
        evaluation: 评估结果字典
        key_prefix: 组件键前缀
    """
    if not evaluation:
        st.info("无评估数据")
        return
    
    # 准备数据
    scores = evaluation.get("scores", {})
    metrics = [
        {"指标": score_name, "分数": f"{score_value:.2f}"} 
        for score_name, score_value in scores.items()
    ]
    metrics.append({"指标": "总分", "分数": f"{evaluation.get('overall_score', 0):.2f}"})
    
    # 创建DataFrame
    df = pd.DataFrame(metrics)
    
    # 显示表格
    st.dataframe(df, use_container_width=True, key=f"{key_prefix}_eval_table")
