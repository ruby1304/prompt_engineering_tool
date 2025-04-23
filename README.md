# Prompt Engineering Tool (提示词调优工程工具)

一个用于创建、测试和优化AI模型提示词的工具。支持多种AI模型提供商，包括OpenAI、Anthropic、Google以及国内的智谱AI、阿里云通义千问和百川智能等。

## 功能特点

- **提示词编辑器**：创建和管理提示词模板，支持变量和条件
- **测试管理**：创建和组织测试用例，设定评估标准
- **测试运行**：执行提示词测试并自动评估结果
- **结果分析**：详细分析测试结果和性能指标，提供可视化图表
- **多维度评估**：从多个维度评估提示词表现
- **提示词优化**：基于测试结果自动优化提示词
- **A/B测试**：比较不同提示词版本的效果
- **批量评估**：同时评估多个优化版本的提示词
- **多模型支持**：支持多个AI服务提供商的模型，包括国际和国内主流模型

## 快速开始

### 环境要求

- Python 3.8+
- pip 包管理器

### 安装步骤

1. 克隆项目：
```bash
git clone https://github.com/yourusername/prompt_engineering_tool.git
cd prompt_engineering_tool
```

2. 安装依赖：
```bash
pip install -r requirements.txt
```

3. 运行应用：
```bash
python run.py
```

应用将在 http://localhost:8501 启动。

### 配置API密钥

1. 首次运行时，系统会创建默认配置文件
2. 在应用的"API管理"页面中配置各个提供商的API密钥
3. 或者直接编辑 `data/config.json` 文件

## 支持的模型提供商

- OpenAI (ChatGPT)
  - gpt-3.5-turbo
  - gpt-4
  - gpt-4o
- Anthropic
  - claude-3-opus
  - claude-3-sonnet
  - claude-3-haiku
- Google
  - gemini-pro
  - gemini-1.5-pro
- 智谱AI
  - chatglm_turbo
  - chatglm_pro
  - chatglm_std
  - chatglm_lite
- 阿里云通义千问
  - qwen-turbo
  - qwen-plus
  - qwen-max
- 百川智能
  - Baichuan2-Turbo
  - Baichuan2-Turbo-192k

## 使用指南

### 1. 创建提示词模板

1. 在"提示词编辑"页面创建新模板
2. 设置模板名称和描述
3. 编写提示词内容，使用 `{{变量名}}` 语法插入变量
4. 设置变量的默认值和描述

### 2. 创建测试集

1. 在"测试管理"页面创建新测试集
2. 添加测试用例，包括：
   - 用例描述
   - 用户输入
   - 变量值
   - 期望输出
   - 评估标准

### 3. 运行测试

1. 在"测试运行"页面选择：
   - 提示词模板
   - 测试集
   - 要测试的模型
2. 设置运行参数（温度、最大token等）
3. 开始测试

### 4. 查看结果

在"结果分析"页面可以：
- 查看测试结果详情
- 比较不同模型的表现
- 分析评估指标
- 可视化测试数据

### 5. 优化提示词

1. 在"提示词专项优化"页面选择需要优化的提示词和测试集
2. 选择优化策略和参数
3. 运行优化并查看结果
4. 进行A/B测试比较原始和优化后的提示词

### 6. 批量评估

在"提示词批量评估"页面可以同时测试和比较多个优化版本的提示词效果

## 项目结构

```
prompt_engineering_tool/
├── app.py              # 主应用入口
├── config.py           # 配置管理
├── run.py              # 启动脚本
├── requirements.txt    # 依赖列表
├── models/             # 模型和API客户端
├── ui/                 # 用户界面组件
│   ├── api_manager.py      # API管理界面
│   ├── components.py       # 通用UI组件
│   ├── model_selector.py   # 模型选择器
│   ├── prompt_ab_test.py   # A/B测试界面
│   ├── prompt_batch_ab_test.py # 批量A/B测试界面
│   ├── prompt_editor.py    # 提示词编辑器
│   ├── prompt_optimization.py # 提示词优化界面
│   ├── provider_manager.py # 提供商管理界面
│   ├── results_viewer.py   # 结果查看界面
│   ├── test_manager.py     # 测试管理界面
│   └── test_runner.py      # 测试运行界面
└── utils/              # 工具函数
    ├── common.py          # 通用工具函数
    ├── evaluator.py       # 评估器
    ├── optimizer.py       # 优化器
    └── visualizer.py      # 可视化工具
```

## 自定义模型提供商

可以通过编辑 `data/config.json` 文件添加新的模型提供商，或使用"模型提供商管理"页面添加。配置格式如下：

```json
{
  "providers": {
    "provider_name": {
      "base_url": "API基础URL",
      "models": ["支持的模型列表"],
      "endpoint": "API端点",
      "auth_prefix": "认证前缀",
      "request_template": {
        "model": "{model}",
        "messages": "{messages}",
        "temperature": 0.7,
        "max_tokens": 1000
      },
      "response_mapping": {
        "text": "响应文本的JSON路径",
        "usage": "用量信息的JSON路径",
        "error": "错误信息的JSON路径"
      }
    }
  }
}
```

## 主要特性说明

### 提示词模板

- 支持变量插入：使用 `{{变量}}` 语法
- 条件逻辑：基于测试用例的不同输入调整提示词
- 模板保存和版本管理

### 测试和评估

- 多维度评估：准确性、相关性、创造性等
- 自定义评估标准：根据具体需求自定义评分维度
- 重复测试：支持多次测试以评估稳定性
- Token使用分析：分析模型的token消耗

### 结果分析

- 可视化比较：图表化展示不同模型和提示词的表现
- 详细报告：自动生成详细的测试报告
- 响应比较：并排比较不同版本的模型响应

### 模型管理

- 多提供商支持：统一接口管理多个AI服务提供商
- 自定义提供商：添加新的模型提供商
- 价格分析：估算API调用成本

## 贡献指南

欢迎提交 Issue 和 Pull Request。

## 许可证

MIT License