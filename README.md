# Prompt Engineering Tool

一个用于创建、测试和优化AI模型提示词的工具。支持多种AI模型提供商，包括OpenAI、Anthropic、Google以及国内的智谱AI、阿里云通义千问和百川智能等。

## 功能特点

- 提示词编辑器：创建和管理提示词模板
- 测试管理：创建和组织测试用例
- 测试运行：执行提示词测试并评估结果
- 结果分析：分析测试结果和性能指标
- 多模型支持：支持多个AI服务提供商的模型

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
- Anthropic
  - claude-3-opus
  - claude-3-sonnet
- Google
  - gemini-pro
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

## 项目结构

```
prompt_engineering_tool/
├── app.py              # 主应用入口
├── config.py           # 配置管理
├── models/             # 模型和数据库
├── ui/                 # 用户界面组件
└── utils/             # 工具函数
```

## 自定义模型提供商

可以通过编辑 `data/config.json` 文件添加新的模型提供商，配置格式如下：

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

## 贡献指南

欢迎提交 Issue 和 Pull Request。

## 许可证

MIT License