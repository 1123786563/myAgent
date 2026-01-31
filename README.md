# LedgerAlpha 项目说明

LedgerAlpha 是一个“三位一体”的微小企业全自动记账智能体系统，集成了 AgentScope, Moltbot 和 OpenManus 的核心优势。

## 🚀 快速开始

### 1. 环境准备
- Docker & Docker Compose
- OpenAI API Key (或其他兼容 LLM Key)

### 2. 配置
复制示例配置文件：
```bash
cp .env.example .env
```
编辑 `.env` 文件，填入你的 `OPENAI_API_KEY`。

### 3. 启动
使用 Docker Compose 一键启动所有服务：
```bash
docker-compose up -d
```

### 4. 使用
- **Web API**: 访问 `http://localhost:8000/docs` 查看 Swagger 文档。
- **状态监控**: `http://localhost:8000/health` 和 `http://localhost:8000/stats`。
- **文件投递**: 将图片或银行流水文件放入 `workspace/input` 目录，系统将自动开始处理。

## 🏗 架构说明

- **MasterDaemon**: 系统的守护进程，负责进程保活与自愈。
- **Collector**: 智能采集舱，监听文件变化并进行 OCR/Excel 解析。
- **AccountingAgent**: 记账核心，负责分类与分录生成 (L1/L2)。
- **Auditor**: 审计员，执行规则检查与异构审计。
- **Sentinel**: 税务哨兵，负责合规性检查与预算熔断。
- **MatchEngine**: 智能消消乐引擎，负责对账匹配。
- **InteractionHub**: 交互中心，负责 Webhook 回调与卡片推送。

## 🛡 数据安全
本系统采用“本地优先”策略，敏感财务数据仅存储在本地 SQLite 数据库中，对外交互时会自动进行脱敏处理。

## 📜 许可证
MIT License
