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
        
        # 选择要优化的提示词
        prompt_to_optimize = st.selectbox(
            "选择要优化的提示词",
            list(results.keys()),
            index=list(results.keys()).index(worst_prompt[0]) if worst_prompt[0] in results else 0
        )
        
        optimization_strategy = st.selectbox(
            "优化策略",
            ["balanced", "accuracy", "completeness", "conciseness"],
            format_func=lambda x: {
                "balanced": "平衡优化 (准确性、完整性和简洁性)",
                "accuracy": "优化准确性",
                "completeness": "优化完整性",
                "conciseness": "优化简洁性"
            }.get(x, x)
        )
        
        if st.button("生成优化建议", type="primary"):
            prompt_data = results[prompt_to_optimize]
            original_prompt = prompt_data.get("template", {}).get("template", "")
            
            # 准备评估结果列表
            evaluation_results = []
            for case in prompt_data.get("test_cases", []):
                if "evaluation" in case and not "error" in case["evaluation"]:
                    evaluation_results.append(case["evaluation"])
            
            with st.spinner("正在生成优化建议..."):
                # 调用优化器
                optimizer = PromptOptimizer()
                
                # 实际应用中应使用适当的异步处理
                import asyncio
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                optimization_result = loop.run_until_complete(optimizer.optimize_prompt(
                    original_prompt,
                    evaluation_results,
                    optimization_strategy
                ))
                loop.close()
                
                if "error" in optimization_result:
                    st.error(f"优化失败: {optimization_result['error']}")
                else:
                    # 保存优化结果
                    st.session_state.optimized_prompts = optimization_result.get("optimized_prompts", [])
                    
                    # 显示优化结果
                    st.success("已生成优化建议")
                    
                    for i, opt_prompt in enumerate(st.session_state.optimized_prompts):
                        with st.expander(f"优化版本 {i+1}: {opt_prompt.get('strategy', '未知策略')}"):
                            st.markdown("**优化策略**:")
                            st.write(opt_prompt.get("strategy", ""))
                            
                            st.markdown("**预期改进**:")
                            st.write(opt_prompt.get("expected_improvements", ""))
                            
                            st.markdown("**优化后的提示词**:")
                            st.code(opt_prompt.get("prompt", ""))
                            
                            # 创建按钮，将优化后的提示词保存为新模板
                            if st.button(f"保存为新模板", key=f"save_opt_{i}"):
                                from ..config import save_template
                                
                                # 复制原始模板，替换提示词内容
                                original_template = prompt_data.get("template", {})
                                new_template = dict(original_template)
                                
                                new_template["name"] = f"{original_template.get('name', 'template')}_{optimization_strategy}_v{i+1}"
                                new_template["description"] = f"从 '{original_template.get('name', 'unknown')}' 优化: {opt_prompt.get('strategy', '')}"
                                new_template["template"] = opt_prompt.get("prompt", "")
                                
                                save_template(new_template["name"], new_template)
                                st.success(f"已保存为新模板: {new_template['name']}")
    
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
        # 检查evaluation是否存在且不为None
        if case.get("evaluation") is not None and "overall_score" in case["evaluation"]:
            total_score += case["evaluation"]["overall_score"]
            count += 1
    
    return total_score / count if count > 0 else 0