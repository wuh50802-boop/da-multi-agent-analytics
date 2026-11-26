# 项目状态交接文档

> 用途：开启新一轮对话时，先读这份文档即可恢复上下文。
> 更新时间：2026-11-26

---

## 0. 协作方式（必须遵守）

- **不要主动改代码**。每次操作前先说清楚"要改什么、为什么改、改成什么样"。
- 用户会选择：**自己照着说明慢慢执行**，或者**明确让我动手改**。没有被明确授权时，只读、只分析、只写规划文档。
- 一次只聚焦一个小步骤，不要一次铺开太多内容——用户明确反馈过"看得头大"。
- 回答要短、要分点、要一眼看懂。

---

## 1. 项目是什么

本 rebuild 复刻自 GitHub 项目 `liuchaoqi-7/DA_Multi_Agent_Workflow`（电商全域数据中台 + n8n 自动化分析系统）。

- **母版源码**：`D:/AI_Projects/DA_Multi_Agent_Workflow_reference`（完整可用）
- **当前项目**：`D:/AI_Projects/DA_Multi_Agent_Workflow_rebuild`

当前 rebuild 只复刻了母版的**数据分析 Agent 环节 + mini ETL 骨架**，母版的三根支柱（电商数据、n8n 调度、飞书交互）都还没移植过来。

### 当前代码结构

| 文件/目录 | 状态 |
|---|---|
| `schema.sql` | 4 张电商数仓表 DDL（已导入本地 MySQL），英文表名 + 中文字段名 |
| `main.py` | 一次性 ETL：本地 mock → ODS → DWD → DWS → ADS |
| `config.py` | 全局配置；`ALLOWED_TABLES` 为 4 张电商表 |
| `src/etl/` | 数据管道：api_client（读 mock）/ data_processor（清洗）/ data_storage（四层写入）/ mock_data_generator |
| `src/agents/` | 五个 Agent + sql_executor（路由→SQL生成→审批→执行→报告→QA） |
| `src/core/` | workflow 状态机 / state / context_manager / retry / budget / main_agent |
| `src/storage/` | workflow_storage / conversation_storage / usage_storage（MySQL 持久化） |
| `src/service/` | task_service / conversation_manager |
| `src/prompts/` | 5 份提示词，sql_generator 已含反引号约束 |
| `src/api.py` | FastAPI，11 个路由（chat / 审批 / 重试 / 任务 / Dashboard） |
| `frontend/` | React + Vite 单页（总览 / 任务管理 / Agent 分析），`App.jsx` 1865 行未拆 |
| `data/mock_orders.csv` / `.json` | 1000 条模拟电商订单（抖店/微信/小红书），带脏数据与勾稽关系 |
| `tests/` | 2 个真正的单测（context_manager / retry_task） |

> 2026-11-27 已完成目录重组（原 src 平铺 28 文件 → 6 个子包）与 A1 阶段 1/2/3 步（schema + 数据生成器 + ETL 改造）。代码备份在 `D:/AI_Projects/_backup_code_20261127`。

### 已知的阻塞项与缺口

1. 原始 `requirements.txt` 缺 `fastapi/uvicorn/pydantic`，后端起不来（**已被上一轮改动修复，见第 3 节**）
2. **无任何建表 DDL**，7 张表靠外部手工创建，唯一索引无定义
3. QA 结果不生效（**已被上一轮改动修复，见第 3 节**）
4. `.env` 有明文 API key，建议轮换
5. 数据源是 jsonplaceholder 帖子，不是电商数据
6. 无调度、无增量、无数据质量校验
7. 应用层无业务图表、无流式问答、无报告导出、无异常预警

---

## 2. 下一步规划（五阶段）

详细规划见 `PLAN.md`（一页纸简版）。

| 阶段 | 做什么 | 完成后能看到什么 |
|---|---|---|
| **A** 数据底座 | 造 1000 条模拟订单、建电商数仓表、改造 ETL 和 SQL prompt | 自然语言问"本月抖店 GMV TOP10 达人"能出结果 |
| **B** n8n 调度 | Docker 起 n8n，定时跑 ETL，失败推飞书告警 | 每天自动更新数据 |
| **C** Agent 增强 | 补澄清/拒绝/直答路由、QA 自动返工 | Agent 会追问、会拒绝、会自我纠正 |
| **D** 双端交互 | Web 加业务图表和流式问答；飞书推交互卡片 | 同一个问题两端都能看结果 |
| **E** 企业治理 | 知识库、权限白名单、审计日志 | 敏感数据拦得住，问过的都能追溯 |

**A0（阶段 A 的阻塞项修复）分三小步**：
1. 补依赖清单 —— **上一轮已改**
2. 修 QA 门禁 —— **上一轮已改**
3. 轮换 `.env` API key —— **未做**，需要用户去 DeepSeek 控制台生成新 key，我无法代劳

---

## 3. 上一轮已经改了什么（用户尚未确认去留）

项目**无 git 跟踪**，无法一键回退。以下为全部改动，用户决定保留或手动还原。

### 3.1 `requirements.txt` —— 已改

现内容：
```
# Core
requests>=2.28.0
python-dotenv>=1.0.0

# Database
mysql-connector-python>=8.1.0

# Data processing
pandas>=2.0.0

# LLM
openai>=1.0.0

# API server
fastapi>=0.110.0
uvicorn>=0.27.0
pydantic>=2.5.0
```

原始内容（如需还原，贴回去即可）：
```
requests
pandas
mysql-connector-python
python-dotenv
openai
```

### 3.2 `src/workflow.py:448-484` —— 已改

在 QA 步骤（原第 446 行）之后、"完成"逻辑之前插入了门禁检查：QA 未通过时设 `status="failed"`、记录 issues 到 error、重置 `qa_review` 步骤为 pending，然后 return；QA 通过才走原来的 `completed`。

原始"完成"段（如需还原，把 448-484 行整段替换成下面这段即可）：
```python
            # 完成
            check_execution_lease(
                task_id,
                execution_token,
                heartbeat.lost_event
            )

            state["status"] = "completed"
            state["error"] = None

            save_workflow_state(
                state,
                execution_token=execution_token
            )

            logger.info(
                "工作流完成 | Task：%s",
                task_id
            )

            return state
```

### 3.3 验证情况

- `workflow.py` 语法检查通过
- 单测未跑成：隔离环境和系统环境都缺项目依赖（dotenv / mysql），这正是 A0 要解决的问题；一个依赖安装的后台任务被中断打断，可能部分执行，只影响隔离 Python 环境，不影响项目代码

### 3.4 待用户拍板的设计问题

QA 未通过后我设成了 `failed` 并重置 QA 步骤——这样点"恢复"会重新跑 QA 审核，但**不会自动重写报告**（真正的自动返工是阶段 C）。这个处理需要用户确认是否认可。

---

## 4. 已定的决策

| 决策项 | 结论 |
|---|---|
| 分析内核 | 保留 Python FastAPI + 现有 Agent，不引入 LangGraph |
| 调度层 | 移植 n8n（不做 APScheduler） |
| 交互端 | Web + 飞书并行，共用后端 API |
| 数据起步 | 模拟电商数据 1000 条 |
| 字段范围 | 核心 30 字段 |
| 命名方案 | 英文表名 + 中文字段名（用户已认可） |

---

## 5. 待确认项（下次对话从这里接着聊）

1. 上面第 3 节的两处改动：**保留还是还原**？
2. QA 未通过 → `failed` + 重置 QA 步骤，这个处理是否认可？
3. n8n 用官方镜像从零配，还是改造母版那份 `docker-compose.yml`？
4. 有飞书应用的 `app_id` / `app_secret` / `chat_id` 吗？没有就先留占位符
5. 下一步想从哪开始：先学某个概念，还是继续 A0 第 3 步，还是进入 A1（表结构设计）？

---

## 6. 母版可移植资产（快速参考）

**可直接复制**：
- `SQL_create_table/dim_Metadata&Dictionary.sql`（唯一零采集依赖）
- `数据分析Agent (1).json` 中报告增强/QA/直答 Agent 的 systemMessage
- 飞书 V2 交互卡片模板（同文件 `飞书推送数据分析结果3` 节点的 content）
- 采集模块 `config.py` 的枚举映射字典
- `n8n_setting/custom.css`、`.env.example`

**需改造**：
- `数据分析Agent (1).json`：换凭证、换表结构
- `数据中台 - 完整ETL工作流Agent (2).json`：2 个失效子工作流 ID、9 处硬编码路径、错名凭证，不要整包导入
- `docker-compose.yml`：arm64 镜像改 x86、去 macOS 路径

**不要照搬**：
- `web_crawler/`（与模拟数据方向相反）
- `KOL_live_control.sql`（硬编码达人专场）
- 含表名 bug 的 `dim_order_product.sql`（维度/纬度）、`live_material_order.sql`（大小写）
