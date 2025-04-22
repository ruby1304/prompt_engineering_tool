#!/usr/bin/env python
import streamlit.web.cli as stcli
import sys
import os
from pathlib import Path

def run_streamlit():
    """运行Streamlit应用"""
    # 获取当前目录
    current_dir = Path(__file__).parent
    
    # 构建app.py的路径
    app_path = current_dir / "app.py"
    
    # 检查app.py是否存在
    if not app_path.exists():
        print(f"错误: 找不到应用入口文件 '{app_path}'")
        sys.exit(1)
    
    # 准备Streamlit命令行参数
    sys.argv = [
        "streamlit", "run",
        str(app_path),
        "--server.port=8501",
        "--server.address=localhost",
        "--browser.serverAddress=localhost",
        "--theme.primaryColor=#FF4B4B",
        "--theme.backgroundColor=#FFFFFF",
        "--theme.secondaryBackgroundColor=#F0F2F6",
        "--theme.textColor=#262730"
    ]
    
    # 运行Streamlit
    sys.exit(stcli.main())

if __name__ == "__main__":
    run_streamlit()
