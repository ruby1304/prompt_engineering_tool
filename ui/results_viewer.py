import streamlit as st
import json
import pandas as pd
from pathlib import Path
from datetime import datetime
from config import get_result_list, load_result
from utils.visualizer import (
    create_score_comparison_chart, 
    create_token_comparison_chart,
    create_radar_chart,
    generate_report,
    display_report
)
from utils.optimizer import PromptOptimizer

def render_results_viewer():
    st.title("📈 测试结果查看")
    
    # 选择要查看的测试结果
    result_list = get_result_list()
    
    if not result_list:
        st.warning("未找到测试结果，请先运行测试")
        return
    
    # 如果有上次测试的结果，默认选择它
    default_result = st.session_state.get("last_result", result_list[0]) if result_list else None
    
    selected_result = st.selectbox(
        "选择测试结果",
        result_list,
        index=result_list.index(default_result) if default_result in result_list else 0
    )
    
    if not selected_result:
        return
    
    # 加载选择的结果
    results = load_result(selected_result)
    
    # 展示结果概览
    st.subheader("测试概览")
    
    # 提取概览信息
    overview = {}
    for prompt_name, prompt_data in results.items():
        overview[prompt_name] = {
            "测试集": prompt_data.get("test_set", ""),
            "模型": ", ".join(prompt_data.get("models", [])),
            "测试用例数": len(prompt_data.get("test_cases", [])),
            "平均分数": calculate_average_score(prompt_data)
        }
    
    # 显示概览表格
    st.dataframe(pd.DataFrame.from_dict(overview, orient='index'))
    
    # 可视化结果
    st.subheader("结果可视化")
    
    tab1, tab2, tab3 = st.tabs(["评分对比", "Token分析", "多维度分析"])
    
    with tab1:
        st.plotly_chart(create_score_comparison_chart(results), use_container_width=True)
    
    with tab2:
        st.plotly_chart(create_token_comparison_chart(results), use_container_width=True)
    
    with tab3:
        st.plotly_chart(create_radar_chart(results), use_container_width=True)
    
    # 生成并显示报告
    report = generate_report(results)
    display_report(report)
    
    # 显示详细测试结果
    st.subheader("详细测试结果")
    from ui.components import display_test_case_details
    for prompt_name, prompt_data in results.items():
        with st.expander(f"提示词: {prompt_name}"):
            st.markdown(f"**模板描述**: {prompt_data.get('template', {}).get('description', '无描述')}")
            st.markdown(f"**测试集**: {prompt_data.get('test_set', '未知')}")
            st.markdown(f"**测试模型**: {', '.join(prompt_data.get('models', []))}")
            # 用通用组件展示每个用例详情
            for i, case in enumerate(prompt_data.get("test_cases", [])):
                st.markdown(f"### 测试用例 {i+1}: {case.get('case_description', case.get('case_id', ''))}")
                display_test_case_details(case, show_system_prompt=True, inside_expander=True)
    
    # 提示词优化功能
    st.divider()
    st.subheader("📝 提示词优化")
    
    # 找出最好和最差的提示词
    avg_scores = {name: calculate_average_score(data) for name, data in results.items()}
    
    if avg_scores:
        best_prompt = max(avg_scores.items(), key=lambda x: x[1])
        worst_prompt = min(avg_scores.items(), key=lambda x: x[1])
        
        st.write(f"最佳提示词: **{best_prompt[0]}** (平均分: {best_prompt[1]:.1f})")
        st.write(f"最差提示词: **{worst_prompt[0]}** (平均分: {worst_prompt[1]:.1f})")

    st.divider()
    st.subheader("📝 评估日志")

    # 获取所有日志文件
    log_dir = Path("data/logs")
    if log_dir.exists():
        log_files = list(log_dir.glob("evaluator_log_*.txt"))
        if log_files:
            log_files.sort(key=lambda x: x.stat().st_mtime, reverse=True)
            
            # 显示最新的几个日志文件
            selected_log = st.selectbox(
                "选择评估日志文件",
                options=log_files,
                format_func=lambda x: f"{x.name} ({datetime.fromtimestamp(x.stat().st_mtime).strftime('%Y-%m-%d %H:%M:%S')})"
            )
            
            if selected_log:
                with open(selected_log, "r", encoding="utf-8") as f:
                    log_content = f.read()
                
                st.code(log_content)
                
                if st.button("删除选中的日志文件"):
                    try:
                        selected_log.unlink()
                        st.success("日志文件已删除")
                        st.rerun()
                    except Exception as e:
                        st.error(f"删除日志文件时出错: {str(e)}")
        else:
            st.info("暂无评估日志文件")
    else:
        st.info("日志目录不存在")

    # 分享和导出功能
    st.divider()
    st.subheader("📤 分享和导出")
    
    # 导出为JSON
    if st.download_button(
        label="导出结果为JSON",
        data=json.dumps(results, ensure_ascii=False, indent=2),
        file_name=f"{selected_result}.json",
        mime="application/json"
    ):
        st.success("结果已导出")

def calculate_average_score(prompt_data):
    """计算提示词平均分"""
    total_score = 0
    count = 0

    for case in prompt_data.get("test_cases", []):
        # 从 responses[0] 获取 evaluation
        response_list = case.get("responses", [])
        if not response_list:
            continue
        evaluation = response_list[0].get("evaluation") # Get evaluation from the first response

        # 检查evaluation是否存在且不为None
        if evaluation is not None and "overall_score" in evaluation:
            total_score += evaluation["overall_score"]
            count += 1

    return total_score / count if count > 0 else 0