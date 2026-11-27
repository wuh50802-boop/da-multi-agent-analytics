# 项目状态交接文档

> 用途：开启新一轮对话时，先读这份文档即可恢复上下文，无需翻历史对话。
> 更新时间：2026-11-27（Agent 体系完善后）
> 当前 HEAD：`a8e083c`

---

## 0. 协作方式（必须遵守）

- **先讲清楚再动手**：改什么、为什么、改成什么样，一次一小步。用户明确反馈过"一口气全做完，概念没建立"。
- 用户说"开始/提交/做吧"才动手；否则只讲解、只分析。
- 回答要短、分点、一眼看懂。
- 用户最终目标：**项目做完后写进简历，作为 AI 产品经理代表作**。但节奏是"先做出来，再讲简历"，简历话题等用户主动提。

---

## 1. 项目是什么

复刻自 `liuchaoqi-7/DA_Multi_Agent_Workflow`（电商数据中台 + n8n 多 Agent）。当前 rebuild 已建成一个**可运行的电商数据智能分析平台**：

- 自然语言问数（Text2SQL）→ 人工审批 → 数仓查询 → 报告生成 → QA 质检闭环
- 数仓分层 ODS/DWD/DIM/DWS/ADS，中文表头字段
- 7 个 Agent + 手写状态机（非 LangGraph）
- 企业治理：元数据字典、权限、入口、审计、RAG、导出
- FastAPI + React 运维台 + APScheduler 定时 ETL

**Git 仓库**：`https://github.com/wuh50802-boop/da-multi-agent-analytics`
**项目路径**：`D:/AI_Projects/DA_Multi_Agent_Workflow_rebuild`
**环境**：必须用项目虚拟环境 `.venv/Scripts/python.exe`（系统 Python 缺依赖）

---

## 2. 当前架构（已全部落地并验证）

### 2.1 数据链路

```
mock API → ODS → DWD → DIM → DWS → ADS
```

| 层 | 表 | 行数（实测） |
|---|---|---|
| ODS | `ods_orders_raw` | 1000 |
| DWD | `dwd_orders` | 1000 |
| DIM | `dim_product` / `dim_kol` | 24 / 36 |
| DWS | `dws_kol_daily` | 612 |
| ADS | `ads_kol_rank` | 69 |

- `main.py:run_etl()` 一键跑全链路，**末尾自动同步元数据字典**（A 方案），同步失败不阻断 ETL；健康检查里看 `scheduler.last_run.stats.metadata_fields`。
- 写入幂等：`ON DUPLICATE KEY UPDATE`，连跑行数稳定。
- 采集框架：`src/etl/collector.py`（BaseCollector / MockAPICollector / DouDianCollector 骨架），本地 `mock_api_server.py` 模拟开放平台，Bearer 鉴权 + 分页。

### 2.2 Agent 体系（8 个角色 + 手写状态机）

| Agent | 文件 | 作用 |
|---|---|---|
| supervisor | `src/agents/supervisor.py` | 路由（sql/analysis/chat/clarification/reject）+ 问题补全 |
| analysis_planner_agent | `.../analysis_planner_agent.py` | 分析规划（目标/指标/维度/策略） |
| **knowledge_agent** | `.../knowledge_agent.py` | **RAG 检索业务口径，注入 SQL prompt** |
| sql_agent | `.../sql_agent.py` | Text2SQL，支持 tool calling 增强开关 |
| report_agent | `.../report_agent.py` | 报告生成，支持 QA 返工意见注入 |
| qa_agent | `.../qa_agent.py` | 质检，不通过触发返工（最多 2 次） |
| chat_agent / clarification_agent | `src/agents/` | 闲聊 / 澄清 |

- 编排：`src/core/workflow.py` 手写状态机，**不走 LangGraph**。含租约心跳、断点续跑（`run_step` 复用已完成步骤）、人工审批门禁、预算检查、审计。
- 三个能力缺口**本轮已补齐**：
  1. **上下文管理**（`src/core/context_manager.py`）：字符截断 → token 估算预算（3000）+ 分层裁剪，优先级：当前任务 > 业务口径 > 对话 > 历史任务。
  2. **RAG 接入工作流**：SQL 生成前 `run_step("knowledge_retrieval", ...)` 检索，命中注入 `# Business Context`，走审计；失败降级为空不影响主流程。实测命中 3 条。
  3. **Tool calling**（`src/tools/`）：LangChain `ChatOpenAI` 指向 DeepSeek（OpenAI 兼容），`bind_tools` 绑定 3 个只读工具（查 Schema / 查字典 / RAG 检索）。**执行类工具刻意不暴露**，审批门禁不受影响。DeepSeek 真实 tool calling 已验证通过。

### 2.3 企业治理（`src/governance/`）

| 模块 | 触发方式 |
|---|---|
| 元数据字典 | `POST /admin/metadata/sync` 手动 + ETL 末尾自动 |
| 入口治理 | 每次 `/chat` 创建任务前自动 |
| 权限治理 | SQL 执行前自动（敏感字段/回溯天数） |
| 分析治理 | SQL 生成前自动（规划 + 空结果友好提示） |
| RAG | 上传/列出/检索/重建走管理端点；工作流检索自动 |
| 审计 | 全链路 `trace_id` 串联 |
| 导出 | `GET /tasks/{id}/export`（CSV 带 BOM） |

RAG 技术栈：BM25（jieba）+ Chroma 持久化向量 DB + `bge-small-zh-v1.5` 语义向量（fastembed，模型缓存在 `data/fastembed_cache/`，离线可加载）+ RRF 混合检索。

### 2.4 调度与服务

- `src/service/scheduler.py`：APScheduler 每天 02:00（Asia/Shanghai）跑 ETL，`misfire_grace_time=3600`。
- `src/api.py`：FastAPI，lifespan 启动调度器；`/health` 暴露调度状态；治理端点齐全。
- 前端 `frontend/`：React + Vite 单页（总览 / 任务管理 / Agent 分析）。

---

## 3. Git 状态（重要）

| 提交 | 内容 | 推送状态 |
|---|---|---|
| `47f82ae` | 企业治理全套 | ✅ 已推 |
| `39957ce` | 元数据 ETL 末尾自动同步 + 过期字段清理 | ✅ 已推 |
| `e96a135` | chat/clarification/analysis_planner 包装成 Agent | ❌ 未推 |
| `a2a5136` | 混合 RAG（BM25 + Chroma + 语义向量） | ❌ 未推 |
| `a8e083c` | Agent 体系完善（上下文/RAG 接入/tool calling） | ❌ 未推 |

**本地领先远端 3 个提交**。网络恢复后补推：

```bash
env -u HTTP_PROXY -u HTTPS_PROXY -u http_proxy -u https_proxy git -C "D:/AI_Projects/DA_Multi_Agent_Workflow_rebuild" push origin main
```

`.gitignore` 已排除 `.env`、`.workbuddy/`、`data/chroma_db/`、`data/fastembed_cache/`、`node_modules/`、`.venv/` 等。

---

## 4. 关键决策记录

| 决策 | 结论 | 原因 |
|---|---|---|
| 分析内核 | Python FastAPI + 手写状态机，**不迁 LangGraph** | 迁移会破坏断点续跑/人工审批/租约心跳三大机制，且这些是简历核心资产 |
| Tool calling | 方案 B：只引 LangChain 工具层，状态机不动 | 渐进引入，审批门禁不受影响 |
| 调度 | APScheduler（非 n8n） | 已落地并验证 |
| 向量库 | Chroma（嵌入式持久化） | 无需独立服务 |
| 字段/表名 | 英文表名 + 中文字段名 | 用户已认可 |
| 反引号 | prompt 强约束方案 A | 已落地 |
| QA 返工 | 最多 2 次 | 用户定 |
| DIM 复合键 | 平台 + ID | 用户定 |

---

## 5. 验证结果（2026-11-27）

- `python main.py`：ODS 1000 / DWD 1000 / 元数据 87 字段 / 清理 0 条 / 0.92s。
- `python demo_a2.py`：端到端 `completed`，QA 通过，报告含表格 + GMV 占比 + 运营建议；15903 Token / 0.056 元。
- 6 个步骤（含新增 `knowledge_retrieval`）全部 `completed` 落库，RAG 命中 3 条，审计有留痕。
- 断点续跑、QA 返工循环、权限拦截、敏感词拦截、CSV 导出、RAG 三模式检索均验证通过。

---

## 6. 下一步候选（按优先级）

1. **补推 3 个本地提交**（网络问题，见第 3 节）。
2. **启用 tool calling 增强模式**：`.env` 设 `ENABLE_TOOL_CALLING=true`，跑一次问数看模型自主调只读工具的效果（当前默认关闭，主流程稳定）。
3. **RAG 效果演示**：上传一份"GMV 不含退款"口径文档，问数时观察 SQL 是否据此改写——这是简历上很有说服力的场景。
4. **简历提炼**（用户主动提再做）：AI 产品经理代表作，突出全链路、人工审批门禁、多 Agent 编排、治理闭环、成本管控。

---

## 7. 已知遗留项

- `.env` 有明文 API key，建议用户去 DeepSeek 控制台轮换（我无法代劳）。
- 前端 `App.jsx` 1865 行未拆组件。
- 元数据同步只覆盖 6 张受管表，非实时（ETL 末尾触发，有分钟级滞后）。
- 数据源是 mock 订单 + 抖店采集器骨架，未接真实电商平台凭证。
- 飞书交互端未移植（当前只有 Web）。
