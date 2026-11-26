import "./App.css";
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Legend,
  BarChart,
  Bar,
} from "recharts";
import { useState, useEffect, useRef } from "react";
import { apiRequest, getDateQueryString, buildDashboardUrl } from "./api";
import { API_BASE_URL } from "./api";
function App() {
  // 用于防止重复请求的锁
  const retryLockRef = useRef(false);
  // 当前页面
  const [currentPage, setCurrentPage] = useState("overview");

  // 任务列表数据
  const [taskList, setTaskList] = useState([]);

  // 任务列表加载状态
  const [taskListLoading, setTaskListLoading] = useState(false);

  // 任务列表错误信息
  const [taskListError, setTaskListError] = useState("");

  // 任务列表总数量
  const [taskTotal, setTaskTotal] = useState(0);

  // 当前选择的任务状态
  const [taskStatus, setTaskStatus] = useState("");

  // 当前选择的任务类型
  const [taskType, setTaskType] = useState("");

  // 任务操作状态
  const [taskActionLoading, setTaskActionLoading] = useState(false);
  const [taskActionError, setTaskActionError] = useState("");

  // 工作流步骤配置
  const workflowSteps = [
    { key: "routing", label: "任务路由" },
    { key: "sql_generation", label: "SQL 生成" },
    { key: "sql_execution", label: "SQL 执行" },
    { key: "report_generation", label: "报告生成" },
    { key: "qa_review", label: "质量检查" },
  ];

  // 任务详情
  const [selectedTask, setSelectedTask] = useState(null);
  const [taskDetailLoading, setTaskDetailLoading] = useState(false);
  const [taskDetailError, setTaskDetailError] = useState("");

  // Agent 对话状态
  const [agentInput, setAgentInput] = useState("");
  const [agentMessages, setAgentMessages] = useState([]);
  const [agentConversationId, setAgentConversationId] = useState(null);
  const [agentTask, setAgentTask] = useState(null);
  const [agentSending, setAgentSending] = useState(false);
  const [agentActionLoading, setAgentActionLoading] = useState(false);
  const [agentError, setAgentError] = useState("");

  // 搜索关键词
  const [taskKeyword, setTaskKeyword] = useState("");
  const [appliedKeyword, setAppliedKeyword] = useState("");

  // 当前任务列表页码
  const [currentTaskPage, setCurrentTaskPage] = useState(1);
  const [taskPageSize] = useState(10);
  const [taskTotalPages, setTaskTotalPages] = useState(0);

  // 保存后端返回的 Dashboard 总览数据
  const [overview, setOverview] = useState(null);

  // 保存请求是否正在进行
  const [loading, setLoading] = useState(true);

  // 保存请求错误信息
  const [error, setError] = useState("");

  //保存后端返回的每日任务趋势数组
  const [taskTrend, setTaskTrend] = useState([]);

  // 记录趋势数据是否正在加载
  const [taskTrendLoading, setTaskTrendLoading] = useState(true);

  // 保存后端返回的每日 Token 消耗趋势数组
  const [usageTrend, setUsageTrend] = useState([]);

  // 记录每日 Token 消耗趋势数据是否正在加载
  const [usageTrendLoading, setUsageTrendLoading] = useState(true);

  // 任务趋势接口错误
  const [taskTrendError, setTaskTrendError] = useState("");

  // Token 趋势接口错误
  const [usageTrendError, setUsageTrendError] = useState("");

  // Dashboard 时间筛选
  const [startDate, setStartDate] = useState("");
  const [endDate, setEndDate] = useState("");
  const [filterError, setFilterError] = useState("");

  // 当前已经应用到 Dashboard 的日期
  const [appliedStartDate, setAppliedStartDate] = useState("");
  const [appliedEndDate, setAppliedEndDate] = useState("");

  // 查询日期
  const handleFilter = () => {
    setFilterError("");

    if (startDate && endDate && startDate > endDate) {
      setFilterError("开始日期不能晚于结束日期");
      return;
    }

    // 将用户选择的日期应用到 Dashboard
    setAppliedStartDate(startDate);
    setAppliedEndDate(endDate);
  };

  // 重置日期
  const handleReset = () => {
    setStartDate("");
    setEndDate("");
    setFilterError("");

    // 清空已应用的筛选条件
    setAppliedStartDate("");
    setAppliedEndDate("");
  };

  // Dashboard 手动刷新标识
  const [refreshKey, setRefreshKey] = useState(0);

  // 手动刷新 Dashboard
  const handleRefresh = () => {
    setRefreshKey((prev) => prev + 1);
  };

  // 判断 Dashboard 是否正在刷新
  const isRefreshing = loading || taskTrendLoading || usageTrendLoading;

  // 搜索任务
  const handleTaskSearch = () => {
    setCurrentTaskPage(1);
    setAppliedKeyword(taskKeyword.trim());
  };

  // 上一页
  const handlePreviousPage = () => {
    setCurrentTaskPage((prev) => Math.max(1, prev - 1));
  };

  // 下一页
  const handleNextPage = () => {
    setCurrentTaskPage((prev) => Math.min(taskTotalPages, prev + 1));
  };

  // 获取任务详情
  const handleViewTask = async (taskId) => {
    setSelectedTask(null);
    setTaskDetailError("");
    setTaskDetailLoading(true);

    try {
      const data = await apiRequest(
        `${API_BASE_URL}/tasks/${taskId}`,
        undefined,
        "任务详情请求失败",
      );

      setSelectedTask(data);
      return data;
    } catch (err) {
      console.error("任务详情获取失败：", err);
      setTaskDetailError(err.message);
      throw err;
    } finally {
      setTaskDetailLoading(false);
    }
  };

  // 根据任务详情生成 Agent 回复
  const buildAgentReply = (task) => {
    if (task.status === "awaiting_approval") {
      return "分析任务已生成 SQL，等待你审批后继续执行。";
    }

    if (task.status === "completed") {
      if (typeof task.report === "string") return task.report;
      if (task.report) return JSON.stringify(task.report, null, 2);
      return "分析任务已完成，请查看右侧的执行结果。";
    }

    if (task.status === "failed") {
      return `任务执行失败：${task.error || "暂未提供错误信息"}`;
    }

    if (task.status === "rejected") {
      return "本次 SQL 执行已被拒绝。";
    }

    return `任务当前状态：${task.status || "处理中"}`;
  };

  // 发送 Agent 问题
  const handleAgentSend = async () => {
    const question = agentInput.trim();

    if (!question || agentSending) return;

    setAgentMessages((prev) => [
      ...prev,
      {
        id: `user-${Date.now()}`,
        role: "user",
        content: question,
      },
    ]);

    setAgentInput("");
    setAgentError("");
    setAgentSending(true);
    setAgentTask(null);

    try {
      // 创建 Agent 工作流任务
      const result = await apiRequest(
        `${API_BASE_URL}/chat`,
        undefined,
        "Agent 请求失败",
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
          },
          body: JSON.stringify({
            question,
            conversation_id: agentConversationId,
          }),
        },
      );

      setAgentConversationId(result.conversation_id);

      // 获取完整任务详情
      const detail = await apiRequest(
        `${API_BASE_URL}/tasks/${result.task_id}`,
        undefined,
        "获取 Agent 任务详情失败",
      );

      setAgentTask(detail);

      setAgentMessages((prev) => [
        ...prev,
        {
          id: `agent-${result.task_id}`,
          role: "assistant",
          taskId: result.task_id,
          content: buildAgentReply(detail),
        },
      ]);
    } catch (err) {
      setAgentError(err.message);
      setAgentMessages((prev) => [
        ...prev,
        {
          id: `error-${Date.now()}`,
          role: "assistant",
          content: `请求出现错误：${err.message}`,
        },
      ]);
    } finally {
      setAgentSending(false);
    }
  };

  // Agent SQL 审批与拒绝
  const handleAgentDecision = async (action) => {
    if (!agentTask?.task_id || agentActionLoading) return;

    setAgentActionLoading(true);
    setAgentError("");

    try {
      await apiRequest(
        `${API_BASE_URL}/tasks/${agentTask.task_id}/${action}`,
        undefined,
        action === "approve" ? "SQL 审批失败" : "SQL 拒绝失败",
        { method: "POST" },
      );

      const detail = await apiRequest(
        `${API_BASE_URL}/tasks/${agentTask.task_id}`,
        undefined,
        "刷新任务详情失败",
      );

      setAgentTask(detail);

      setAgentMessages((prev) =>
        prev.map((message) =>
          message.taskId === detail.task_id
            ? { ...message, content: buildAgentReply(detail) }
            : message,
        ),
      );
    } catch (err) {
      setAgentError(err.message);
    } finally {
      setAgentActionLoading(false);
    }
  };

  // 开始新对话
  const handleNewAgentConversation = () => {
    setAgentMessages([]);
    setAgentConversationId(null);
    setAgentTask(null);
    setAgentInput("");
    setAgentError("");
  };

  // 关闭任务详情
  const handleCloseTaskDetail = () => {
    setSelectedTask(null);
    setTaskDetailError("");
  };

  // 审批任务
  const handleApproveTask = async (taskId) => {
    // 与 retry、resume 共用防重复提交锁
    if (retryLockRef.current) {
      return;
    }

    if (!window.confirm("确定要批准这条任务吗？")) {
      return;
    }

    retryLockRef.current = true;
    setTaskActionLoading(true);
    setTaskActionError("");

    try {
      await apiRequest(
        `${API_BASE_URL}/tasks/${taskId}/approve`,
        undefined,
        "任务审批失败",
        { method: "POST" },
      );

      // 清除旧状态筛选
      setTaskStatus("");
      setCurrentTaskPage(1);

      // 刷新任务列表
      setTaskListRefreshKey((prev) => prev + 1);

      // 重新获取原任务详情
      try {
        await handleViewTask(taskId);
      } catch (detailErr) {
        console.error("审批成功，但任务详情获取失败：", detailErr);
      }
    } catch (err) {
      console.error("任务审批失败：", err);
      setTaskActionError(err.message || "任务审批失败");
    } finally {
      retryLockRef.current = false;
      setTaskActionLoading(false);
    }
  };

  // 拒绝任务
  const handleRejectTask = async (taskId) => {
    // 与 retry、resume 共用防重复提交锁
    if (retryLockRef.current) {
      return;
    }

    if (
      !window.confirm(
        "确定要拒绝这条任务吗？拒绝后可以通过重新生成 SQL 创建新任务。",
      )
    ) {
      return;
    }

    retryLockRef.current = true;
    setTaskActionLoading(true);
    setTaskActionError("");

    try {
      await apiRequest(
        `${API_BASE_URL}/tasks/${taskId}/reject`,
        undefined,
        "任务拒绝失败",
        { method: "POST" },
      );

      // 清除旧状态筛选
      setTaskStatus("");
      setCurrentTaskPage(1);

      // 刷新任务列表
      setTaskListRefreshKey((prev) => prev + 1);

      // 重新获取原任务详情
      try {
        await handleViewTask(taskId);
      } catch (detailErr) {
        console.error("拒绝成功，但任务详情获取失败：", detailErr);
      }
    } catch (err) {
      console.error("任务拒绝失败：", err);
      setTaskActionError(err.message || "任务拒绝失败");
    } finally {
      retryLockRef.current = false;
      setTaskActionLoading(false);
    }
  };

  // 恢复执行失败任务
  const handleResumeTask = async (taskId) => {
    // 防止重复提交
    if (retryLockRef.current) {
      return;
    }

    if (!window.confirm("确定要重新执行这条失败任务吗？")) {
      return;
    }

    retryLockRef.current = true;
    setTaskActionLoading(true);
    setTaskActionError("");

    try {
      const result = await apiRequest(
        `${API_BASE_URL}/tasks/${taskId}/resume`,
        undefined,
        "任务恢复执行失败",
        { method: "POST" },
      );
      // 清除旧状态筛选
      setTaskStatus("");
      setCurrentTaskPage(1);

      // 刷新任务列表：即使详情加载失败也能刷新
      setTaskListRefreshKey((prev) => prev + 1);

      // 恢复原任务，仍然查看原 taskId
      try {
        await handleViewTask(taskId);
      } catch (detailErr) {
        setTaskActionError(
          `任务恢复成功，但详情加载失败：${detailErr.message}`,
        );
      }
    } catch (err) {
      console.error("任务恢复执行失败：", err);
      setTaskActionError(err.message || "任务恢复执行失败");
    } finally {
      retryLockRef.current = false;
      setTaskActionLoading(false);
    }
  };

  // 重新尝试被拒绝的任务
  const handleRetryTask = async (taskId) => {
    // 防止重复提交
    if (retryLockRef.current) {
      return;
    }

    if (
      !window.confirm("确定要重新尝试这条被拒绝的任务吗？系统将重新生成 SQL。")
    ) {
      return;
    }

    retryLockRef.current = true;
    setTaskActionLoading(true);
    setTaskActionError("");

    try {
      const result = await apiRequest(
        `${API_BASE_URL}/tasks/${taskId}/retry`,
        undefined,
        "任务重新尝试失败",
        { method: "POST" },
      );

      if (!result?.task_id) {
        throw new Error("重新尝试成功，但未获取到新任务 ID");
      }

      // 清除旧状态筛选
      setTaskStatus("");
      setCurrentTaskPage(1);

      // 刷新任务列表
      setTaskListRefreshKey((prev) => prev + 1);

      // 查看新创建的任务
      try {
        await handleViewTask(result.task_id);
      } catch (detailErr) {
        setTaskActionError(
          `任务重新尝试成功，但详情加载失败：${detailErr.message}`,
        );
      }
    } catch (err) {
      console.error("任务重新尝试失败：", err);
      setTaskActionError(err.message || "任务重新尝试失败");
    } finally {
      retryLockRef.current = false;
      setTaskActionLoading(false);
    }
  };

  const [taskListRefreshKey, setTaskListRefreshKey] = useState(0);

  useEffect(() => {
    // 创建请求控制器
    const controller = new AbortController();

    // 请求开始，显示加载状态
    setLoading(true);

    // 构建日期筛选参数
    const queryString = getDateQueryString(appliedStartDate, appliedEndDate);

    const url = buildDashboardUrl("overview", queryString);

    // 请求后端接口
    apiRequest(url, controller.signal, "总览请求失败")
      .then((data) => {
        setOverview(data);
        setError("");
      })
      .catch((err) => {
        // 如果请求是被主动取消的，不当作接口错误
        if (err.name === "AbortError") {
          return;
        }

        console.error("Dashboard 数据获取失败：", err);

        setOverview(null);
        setError(err.message);
      })
      .finally(() => {
        // 只有当前请求没有被取消，才结束加载状态
        if (!controller.signal.aborted) {
          setLoading(false);
        }
      });

    // 日期或刷新标识发生变化时，取消上一次请求
    return () => {
      controller.abort();
    };
  }, [appliedStartDate, appliedEndDate, refreshKey]);

  useEffect(() => {
    // 创建请求控制器
    const controller = new AbortController();

    // 开始请求，显示加载状态
    setTaskTrendLoading(true);

    // 构建日期参数
    const queryString = getDateQueryString(appliedStartDate, appliedEndDate);

    const url = buildDashboardUrl("task-trend", queryString);

    // 请求后端任务趋势接口
    apiRequest(url, controller.signal, "任务趋势请求失败")
      .then((data) => {
        setTaskTrend(data.data || []);
        setTaskTrendError("");
      })
      .catch((err) => {
        // 被主动取消的请求不算错误
        if (err.name === "AbortError") {
          return;
        }

        console.error("任务趋势数据获取失败：", err);

        setTaskTrend([]);
        setTaskTrendError(err.message);
      })
      .finally(() => {
        // 仅当前请求结束时关闭加载状态
        if (!controller.signal.aborted) {
          setTaskTrendLoading(false);
        }
      });

    // 清理上一次请求
    return () => {
      controller.abort();
    };
  }, [appliedStartDate, appliedEndDate, refreshKey]);

  useEffect(() => {
    const controller = new AbortController();

    setUsageTrendLoading(true);

    const queryString = getDateQueryString(appliedStartDate, appliedEndDate);

    const url = buildDashboardUrl("usage-trend", queryString);

    apiRequest(url, controller.signal, "Token 趋势请求失败")
      .then((data) => {
        setUsageTrend(data.data || []);
        setUsageTrendError("");
      })
      .catch((err) => {
        if (err.name === "AbortError") {
          return;
        }

        console.error("Token 趋势请求失败：", err);

        setUsageTrend([]);
        setUsageTrendError(err.message);
      })
      .finally(() => {
        if (!controller.signal.aborted) {
          setUsageTrendLoading(false);
        }
      });

    return () => {
      controller.abort();
    };
  }, [appliedStartDate, appliedEndDate, refreshKey]);

  // 获取任务列表
  useEffect(() => {
    // 只有进入任务管理页面才请求
    if (currentPage !== "tasks") {
      return;
    }

    const controller = new AbortController();

    setTaskListLoading(true);
    setTaskListError("");

    // 构建任务列表查询参数
    const params = new URLSearchParams();

    params.append("page", String(currentTaskPage));
    params.append("page_size", String(taskPageSize));

    // 如果选择了状态，则添加状态筛选参数
    if (taskStatus) {
      params.append("status", taskStatus);
    }

    if (taskType) {
      params.append("task_type", taskType);
    }

    if (appliedKeyword.trim()) {
      params.append("keyword", appliedKeyword.trim());
    }

    const url = `${API_BASE_URL}/tasks?${params.toString()}`;

    apiRequest(url, controller.signal, "任务列表请求失败")
      .then((data) => {
        setTaskList(data.tasks || []);
        setTaskTotal(data.total || 0);
        setTaskTotalPages(data.total_pages || 0);
      })
      .catch((err) => {
        if (err.name === "AbortError") {
          return;
        }

        console.error("任务列表获取失败：", err);

        setTaskList([]);
        setTaskTotal(0);
        setTaskListError(err.message);
      })
      .finally(() => {
        if (!controller.signal.aborted) {
          setTaskListLoading(false);
        }
      });

    return () => {
      controller.abort();
    };
  }, [
    currentPage,
    taskStatus,
    taskType,
    appliedKeyword,
    currentTaskPage,
    taskPageSize,
    taskListRefreshKey,
  ]);

  return (
    <div className="dashboard">
      {/* 左侧导航栏 */}
      <aside className="sidebar">
        <div className="logo">
          <span className="logo-icon">AI</span>
          <span>Data Platform</span>
        </div>

        <div className="nav-title">工作空间</div>

        <nav>
          <div
            className={`nav-item ${currentPage === "overview" ? "active" : ""}`}
            onClick={() => setCurrentPage("overview")}
          >
            <span>▦</span>
            <span>数据总览</span>
          </div>

          <div
            className={`nav-item ${currentPage === "tasks" ? "active" : ""}`}
            onClick={() => setCurrentPage("tasks")}
          >
            <span>☷</span>
            <span>任务管理</span>
          </div>

          <div
            className={`nav-item ${currentPage === "agents" ? "active" : ""}`}
            onClick={() => setCurrentPage("agents")}
          >
            <span>◈</span>
            <span>Agent 分析</span>
          </div>
        </nav>

        <div className="sidebar-bottom">
          Multi-Agent Workflow
          <br />
          <span>数据分析工作流平台</span>
        </div>
      </aside>

      {/* 右侧主区域 */}
      <main className="main-content">
        <header className="topbar">
          <div>
            <h2>
              {currentPage === "overview"
                ? "数据总览"
                : currentPage === "tasks"
                  ? "任务管理"
                  : "Agent 分析"}
            </h2>

            <p>Multi-Agent 数据分析管理平台</p>
          </div>

          <div className="user-info">
            <span className="status-dot"></span>
            系统运行中
          </div>
        </header>

        <section className="content">
          {currentPage === "overview" && (
            <>
              <div className="welcome">
                <h1>工作流数据看板</h1>
                <p>实时了解任务执行情况、Token 消耗和 Agent 运行表现。</p>
              </div>

              {/* 时间筛选区域 */}
              <div className="filter-section">
                <div className="filter-item">
                  <label>开始日期</label>
                  <input
                    type="date"
                    value={startDate}
                    onChange={(e) => setStartDate(e.target.value)}
                  />
                </div>

                <div className="filter-item">
                  <label>结束日期</label>
                  <input
                    type="date"
                    value={endDate}
                    onChange={(e) => setEndDate(e.target.value)}
                  />
                </div>

                <div className="filter-actions">
                  <button
                    className="filter-button primary"
                    onClick={handleFilter}
                  >
                    查询
                  </button>

                  <button
                    className="filter-button secondary"
                    onClick={handleReset}
                  >
                    重置
                  </button>

                  <button
                    className="filter-button secondary"
                    onClick={handleRefresh}
                    disabled={isRefreshing}
                  >
                    {isRefreshing ? "刷新中..." : "↻ 刷新"}
                  </button>
                </div>

                {filterError && (
                  <div className="filter-error">{filterError}</div>
                )}
              </div>
              {error && (
                <div className="error-message">数据加载失败：{error}</div>
              )}
              {/* 统计卡片区域 */}
              <div className="stats-grid">
                <div className="stat-card">
                  <p>总任务数</p>
                  <h2>
                    {loading
                      ? "加载中..."
                      : (overview?.task_stats?.total_tasks ?? "--")}
                  </h2>
                  <span>累计创建的任务</span>
                </div>

                <div className="stat-card">
                  <p>成功任务数</p>
                  <h2>
                    {loading
                      ? "加载中..."
                      : (overview?.task_stats?.completed_tasks ?? "--")}
                  </h2>
                  <span>成功完成的任务</span>
                </div>

                <div className="stat-card">
                  <p>任务成功率</p>
                  <h2>
                    {loading
                      ? "加载中..."
                      : overview?.task_stats?.success_rate != null
                        ? `${overview.task_stats.success_rate}%`
                        : "--"}
                  </h2>
                  <span>成功任务 / 总任务</span>
                </div>

                <div className="stat-card">
                  <p>Token 总消耗</p>
                  <h2>
                    {loading
                      ? "加载中..."
                      : (overview?.usage_stats?.total_tokens?.toLocaleString() ??
                        "--")}
                  </h2>
                  <span>Prompt + Completion</span>
                </div>
              </div>

              <div className="chart-grid">
                {/* 每日任务趋势 */}
                <div className="chart-card">
                  <h3>每日任务趋势</h3>
                  <p>观察每日任务总量和执行结果变化</p>
                  {taskTrendError && (
                    <div className="error-message">
                      任务趋势加载失败：{taskTrendError}
                    </div>
                  )}
                  <div className="chart-container">
                    {taskTrendLoading ? (
                      <div className="chart-loading">加载中...</div>
                    ) : taskTrendError ? null : taskTrend.length === 0 ? (
                      <div className="chart-empty">
                        当前日期范围内暂无任务数据
                      </div>
                    ) : (
                      <ResponsiveContainer width="100%" height={240}>
                        <LineChart data={taskTrend}>
                          <CartesianGrid strokeDasharray="3 3" />
                          <XAxis dataKey="date" />
                          <YAxis />
                          <Tooltip />
                          <Legend />

                          <Line
                            type="monotone"
                            dataKey="total_tasks"
                            name="总任务数"
                            stroke="#8884d8"
                          />

                          <Line
                            type="monotone"
                            dataKey="completed_tasks"
                            name="成功任务数"
                            stroke="#82ca9d"
                          />

                          <Line
                            type="monotone"
                            dataKey="failed_tasks"
                            name="失败任务数"
                            stroke="#ff6b6b"
                          />
                        </LineChart>
                      </ResponsiveContainer>
                    )}
                  </div>
                </div>

                {/* 每日 Token 消耗趋势 */}
                <div className="chart-card">
                  <h3>每日 Token 消耗趋势</h3>
                  <p>观察 Prompt Token 和 Completion Token 的每日变化</p>
                  {usageTrendError && (
                    <div className="error-message">
                      Token 趋势加载失败：{usageTrendError}
                    </div>
                  )}
                  <div className="chart-container">
                    {usageTrendLoading ? (
                      <div className="chart-loading">加载中...</div>
                    ) : usageTrendError ? null : usageTrend.length === 0 ? (
                      <div className="chart-empty">
                        当前日期范围内暂无 Token 数据
                      </div>
                    ) : (
                      <ResponsiveContainer width="100%" height={240}>
                        <LineChart data={usageTrend}>
                          <CartesianGrid strokeDasharray="3 3" />
                          <XAxis dataKey="date" />
                          <YAxis />
                          <Tooltip />
                          <Legend />

                          <Line
                            type="monotone"
                            dataKey="prompt_tokens"
                            name="Prompt Token"
                            stroke="#4778e8"
                            strokeWidth={2}
                          />

                          <Line
                            type="monotone"
                            dataKey="completion_tokens"
                            name="Completion Token"
                            stroke="#e6a23c"
                            strokeWidth={2}
                          />

                          <Line
                            type="monotone"
                            dataKey="total_tokens"
                            name="Total Token"
                            stroke="#67c23a"
                            strokeWidth={3}
                            dot={{ r: 4 }}
                          />
                        </LineChart>
                      </ResponsiveContainer>
                    )}
                  </div>
                </div>
              </div>
              {/* Agent 成本排行 */}
              <div className="chart-card">
                <h3>Agent 成本排行</h3>
                <p>比较不同 Agent 的模型调用成本，单位：人民币（元）</p>
                {usageTrendError && (
                  <div className="error-message">
                    Agent 成本排行加载失败：{usageTrendError}
                  </div>
                )}
                <div className="chart-container">
                  {loading ? (
                    <div className="chart-loading">加载中...</div>
                  ) : error ? null : !overview?.agent_stats ||
                    overview.agent_stats.length === 0 ? (
                    <div className="chart-empty">
                      当前日期范围内暂无 Agent 成本数据
                    </div>
                  ) : (
                    <ResponsiveContainer width="100%" height={240}>
                      <BarChart
                        data={overview.agent_stats}
                        layout="vertical"
                        margin={{ left: 30, right: 30 }}
                      >
                        <CartesianGrid strokeDasharray="3 3" />

                        <XAxis type="number" />

                        <YAxis
                          type="category"
                          dataKey="agent_name"
                          width={130}
                        />

                        <Tooltip
                          formatter={(value) => [
                            `¥${Number(value).toFixed(6)}`,
                            "成本",
                          ]}
                        />

                        <Bar
                          dataKey="total_cost_rmb"
                          name="总成本"
                          fill="#4778e8"
                          radius={[0, 6, 6, 0]}
                        />
                      </BarChart>
                    </ResponsiveContainer>
                  )}
                </div>
              </div>
            </>
          )}

          {currentPage === "tasks" && (
            <div className="page-placeholder">
              <h2>任务管理</h2>
              {/* 任务状态筛选 */}
              <div className="task-filter">
                <label htmlFor="task-status">任务状态：</label>

                <select
                  id="task-status"
                  value={taskStatus}
                  onChange={(e) => {
                    setCurrentTaskPage(1);
                    setTaskStatus(e.target.value);
                  }}
                >
                  <option value="">全部状态</option>
                  <option value="pending">等待执行</option>
                  <option value="running">执行中</option>
                  <option value="awaiting_approval">等待审批</option>
                  <option value="completed">已完成</option>
                  <option value="failed">执行失败</option>
                  <option value="rejected">已拒绝</option>
                  <option value="budget_exceeded">超出预算</option>
                </select>
              </div>

              <div className="task-filter">
                <label htmlFor="task-type">任务类型：</label>
                <select
                  id="task-type"
                  value={taskType}
                  onChange={(e) => {
                    setCurrentTaskPage(1);
                    setTaskType(e.target.value);
                  }}
                >
                  <option value="">全部类型</option>
                  <option value="sql">SQL 查询</option>
                  <option value="analysis">数据分析</option>
                  <option value="chat">普通对话</option>
                </select>
              </div>

              <div className="task-search">
                <input
                  type="text"
                  placeholder="搜索任务 ID 或问题内容"
                  value={taskKeyword}
                  onChange={(e) => setTaskKeyword(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter") {
                      handleTaskSearch();
                    }
                  }}
                />

                <button className="filter-button" onClick={handleTaskSearch}>
                  搜索
                </button>
              </div>

              <p className="task-total">当前共有 {taskTotal} 条任务</p>

              {taskListLoading ? (
                <div className="chart-loading">正在加载任务列表...</div>
              ) : taskListError ? (
                <div className="error-message">
                  任务列表加载失败：{taskListError}
                </div>
              ) : taskList.length === 0 ? (
                <div className="chart-empty">暂无任务数据</div>
              ) : (
                <div className="task-table-wrapper">
                  <table className="task-table">
                    <thead>
                      <tr>
                        <th>任务 ID</th>
                        <th>用户问题</th>
                        <th>任务类型</th>
                        <th>执行状态</th>
                        <th>创建时间</th>
                      </tr>
                    </thead>

                    <tbody>
                      {taskList.map((task) => (
                        <tr key={task.task_id}>
                          <td>
                            <button
                              className="task-id-button"
                              onClick={() => handleViewTask(task.task_id)}
                            >
                              {task.task_id}
                            </button>
                          </td>

                          <td className="task-question">{task.question}</td>

                          <td>{task.task_type || "--"}</td>

                          <td>
                            <span
                              className={`task-status status-${task.status}`}
                            >
                              {task.status}
                            </span>
                          </td>

                          <td>{task.created_at || "--"}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
              <div className="task-pagination">
                <span>
                  共 {taskTotal} 条记录，第 {currentTaskPage} /{" "}
                  {taskTotalPages || 1} 页
                </span>

                <div className="pagination-buttons">
                  <button
                    className="filter-button secondary"
                    onClick={handlePreviousPage}
                    disabled={currentTaskPage <= 1}
                  >
                    上一页
                  </button>

                  <button
                    className="filter-button secondary"
                    onClick={handleNextPage}
                    disabled={
                      currentTaskPage >= taskTotalPages || taskTotalPages === 0
                    }
                  >
                    下一页
                  </button>
                </div>
              </div>
              {(selectedTask || taskDetailLoading || taskDetailError) && (
                <div className="task-modal-overlay">
                  <div className="task-modal">
                    <div className="task-modal-header">
                      <h2>任务详情</h2>
                      <button
                        className="task-modal-close"
                        onClick={handleCloseTaskDetail}
                      >
                        ×
                      </button>
                    </div>

                    {taskDetailLoading && (
                      <div className="task-detail-loading">
                        正在加载任务详情...
                      </div>
                    )}

                    {taskDetailError && (
                      <div className="error-message">{taskDetailError}</div>
                    )}

                    {selectedTask && (
                      <div className="task-detail-content">
                        <div className="task-detail-section">
                          {/* 工作流执行进度 */}
                          <div className="task-detail-section">
                            <h3>工作流执行进度</h3>

                            <div className="workflow-step-list">
                              {workflowSteps.map((step, index) => {
                                const status =
                                  selectedTask.steps?.[step.key] || "pending";

                                return (
                                  <div className="workflow-step" key={step.key}>
                                    <div
                                      className={`workflow-step-icon ${status}`}
                                    >
                                      {status === "completed"
                                        ? "✓"
                                        : status === "failed"
                                          ? "!"
                                          : index + 1}
                                    </div>

                                    <div className="workflow-step-info">
                                      <span className="workflow-step-name">
                                        {step.label}
                                      </span>

                                      <span
                                        className={`workflow-step-status ${status}`}
                                      >
                                        {status === "completed"
                                          ? "已完成"
                                          : status === "failed"
                                            ? "执行失败"
                                            : status === "running"
                                              ? "执行中"
                                              : "待执行"}
                                      </span>
                                    </div>
                                  </div>
                                );
                              })}
                            </div>
                          </div>
                          <h3>基本信息</h3>

                          <div className="task-detail-grid">
                            <div>
                              <span>任务 ID</span>
                              <p>{selectedTask.task_id}</p>
                            </div>

                            <div>
                              <span>任务类型</span>
                              <p>{selectedTask.task_type || "--"}</p>
                            </div>

                            <div>
                              <span>任务状态</span>
                              <p>{selectedTask.status || "--"}</p>
                            </div>

                            <div>
                              <span>创建时间</span>
                              <p>{selectedTask.created_at || "--"}</p>
                            </div>
                          </div>

                          <div className="task-detail-field">
                            <span>用户问题</span>
                            <p>{selectedTask.question || "--"}</p>
                          </div>

                          {selectedTask.error && (
                            <div className="task-detail-field">
                              <span>错误信息</span>
                              <p className="task-detail-error">
                                {selectedTask.error}
                              </p>
                            </div>
                          )}
                        </div>

                        <div className="task-detail-section">
                          <h3>Token 与成本统计</h3>

                          <div className="task-detail-grid">
                            <div>
                              <span>Prompt Tokens（输入）</span>
                              <p>
                                {selectedTask.agent_usage?.reduce(
                                  (sum, agent) =>
                                    sum + (agent.prompt_tokens || 0),
                                  0,
                                ) ?? "--"}
                              </p>
                            </div>

                            <div>
                              <span>Completion Tokens（输出）</span>
                              <p>
                                {selectedTask.agent_usage?.reduce(
                                  (sum, agent) =>
                                    sum + (agent.completion_tokens || 0),
                                  0,
                                ) ?? "--"}
                              </p>
                            </div>

                            <div>
                              <span>Total Tokens（总计）</span>
                              <p>{selectedTask.usage?.total_tokens ?? "--"}</p>
                            </div>

                            <div>
                              <span>总成本（元）</span>
                              <p>
                                {selectedTask.usage?.total_cost_rmb ?? "--"}
                              </p>
                            </div>
                          </div>
                        </div>

                        {/* 任务操作 */}
                        {selectedTask.status === "awaiting_approval" && (
                          <div className="task-detail-section">
                            <h3>任务审批</h3>

                            {taskActionError && (
                              <div className="error-message">
                                {taskActionError}
                              </div>
                            )}

                            <div className="task-action-buttons">
                              <button
                                className="filter-button"
                                disabled={taskActionLoading}
                                onClick={() =>
                                  handleApproveTask(selectedTask.task_id)
                                }
                              >
                                {taskActionLoading ? "处理中..." : "批准任务"}
                              </button>

                              <button
                                className="filter-button danger"
                                disabled={taskActionLoading}
                                onClick={() =>
                                  handleRejectTask(selectedTask.task_id)
                                }
                              >
                                {taskActionLoading ? "处理中..." : "拒绝任务"}
                              </button>
                            </div>
                          </div>
                        )}

                        {/* 失败任务恢复与运行中任务接管 */}
                        {selectedTask.status === "failed" && (
                          <div className="task-detail-section">
                            <h3>失败任务恢复</h3>

                            {taskActionError && (
                              <div className="error-message">
                                {taskActionError}
                              </div>
                            )}

                            <div className="task-action-buttons">
                              <button
                                className="filter-button"
                                disabled={taskActionLoading}
                                onClick={() =>
                                  handleResumeTask(selectedTask.task_id)
                                }
                              >
                                {taskActionLoading ? "处理中..." : "重新执行"}
                              </button>
                            </div>
                          </div>
                        )}

                        {selectedTask.status === "running" && (
                          <div className="task-detail-section">
                            <h3>运行中任务</h3>

                            {taskActionError && (
                              <div className="error-message">
                                {taskActionError}
                              </div>
                            )}

                            {Boolean(selectedTask.lease_expired) ? (
                              <>
                                <p>任务租约已过期，可以尝试接管执行。</p>

                                <div className="task-action-buttons">
                                  <button
                                    className="filter-button"
                                    disabled={taskActionLoading}
                                    onClick={() =>
                                      handleResumeTask(selectedTask.task_id)
                                    }
                                  >
                                    {taskActionLoading
                                      ? "处理中..."
                                      : "尝试接管执行"}
                                  </button>
                                </div>
                              </>
                            ) : (
                              <p>
                                任务正在执行中，当前租约尚未过期，暂不可接管。
                              </p>
                            )}
                          </div>
                        )}

                        {/* 被拒绝任务：重新生成 SQL */}
                        {selectedTask.status === "rejected" && (
                          <div className="task-detail-section">
                            <h3>重新生成 SQL</h3>

                            {taskActionError && (
                              <div className="error-message">
                                {taskActionError}
                              </div>
                            )}

                            <div className="task-action-buttons">
                              <button
                                className="filter-button"
                                disabled={taskActionLoading}
                                onClick={() =>
                                  handleRetryTask(selectedTask.task_id)
                                }
                              >
                                {taskActionLoading
                                  ? "处理中..."
                                  : "重新生成 SQL"}
                              </button>
                            </div>
                          </div>
                        )}

                        {/* SQL 执行信息 */}
                        <div className="task-detail-section">
                          <h3>SQL 执行信息</h3>

                          <div className="task-detail-field">
                            <span>SQL 审批状态</span>
                            <p>
                              {selectedTask.sql_approved === true
                                ? "已批准"
                                : selectedTask.sql_approved === false
                                  ? "未批准"
                                  : "--"}
                            </p>
                          </div>

                          <div className="task-detail-field">
                            <span>SQL 语句</span>
                            {selectedTask.sql ? (
                              <pre className="task-sql-code">
                                {selectedTask.sql}
                              </pre>
                            ) : (
                              <p>暂无 SQL 语句</p>
                            )}
                          </div>
                        </div>

                        {/* SQL 查询结果 */}
                        <div className="task-detail-section">
                          <h3>SQL 查询结果</h3>

                          {selectedTask.query_results?.length > 0 ? (
                            <div className="task-result-wrapper">
                              <table className="task-table">
                                <thead>
                                  <tr>
                                    {Object.keys(
                                      selectedTask.query_results[0],
                                    ).map((key) => (
                                      <th key={key}>{key}</th>
                                    ))}
                                  </tr>
                                </thead>

                                <tbody>
                                  {selectedTask.query_results.map(
                                    (row, index) => (
                                      <tr key={index}>
                                        {Object.keys(
                                          selectedTask.query_results[0],
                                        ).map((key) => (
                                          <td key={key}>
                                            {row[key] === null ||
                                            row[key] === undefined
                                              ? "--"
                                              : String(row[key])}
                                          </td>
                                        ))}
                                      </tr>
                                    ),
                                  )}
                                </tbody>
                              </table>
                            </div>
                          ) : (
                            <p>暂无查询结果</p>
                          )}
                        </div>

                        {/* QA 质量检查 */}
                        <div className="task-detail-section">
                          <h3>QA 质量检查</h3>

                          {selectedTask.qa_result ? (
                            <>
                              <div className="task-detail-field">
                                <span>检查结果</span>
                                <p
                                  className={
                                    selectedTask.qa_result.passed
                                      ? "qa-status-passed"
                                      : "qa-status-failed"
                                  }
                                >
                                  {selectedTask.qa_result.passed
                                    ? "检查通过"
                                    : "检查未通过"}
                                </p>
                              </div>

                              <div className="task-detail-field">
                                <span>检查总结</span>
                                <p>{selectedTask.qa_result.summary || "--"}</p>
                              </div>

                              <div className="task-detail-field">
                                <span>发现的问题</span>

                                {selectedTask.qa_result.issues?.length > 0 ? (
                                  <ul className="qa-list">
                                    {selectedTask.qa_result.issues.map(
                                      (issue, index) => (
                                        <li key={index}>{issue}</li>
                                      ),
                                    )}
                                  </ul>
                                ) : (
                                  <p>未发现问题</p>
                                )}
                              </div>

                              <div className="task-detail-field">
                                <span>改进建议</span>

                                {selectedTask.qa_result.suggestions?.length >
                                0 ? (
                                  <ul className="qa-list">
                                    {selectedTask.qa_result.suggestions.map(
                                      (suggestion, index) => (
                                        <li key={index}>{suggestion}</li>
                                      ),
                                    )}
                                  </ul>
                                ) : (
                                  <p>暂无改进建议</p>
                                )}
                              </div>
                            </>
                          ) : (
                            <p>暂无质量检查结果</p>
                          )}
                        </div>

                        {/* 分析报告 */}
                        <div className="task-detail-section">
                          <h3>分析报告</h3>

                          {selectedTask.report ? (
                            <div className="task-report-content">
                              {typeof selectedTask.report === "string" ? (
                                <div className="task-report-text">
                                  {selectedTask.report}
                                </div>
                              ) : (
                                <pre className="task-report-json">
                                  {JSON.stringify(selectedTask.report, null, 2)}
                                </pre>
                              )}
                            </div>
                          ) : (
                            <p>当前任务没有生成分析报告</p>
                          )}
                        </div>

                        <div className="task-detail-section">
                          <h3>Agent 使用统计</h3>

                          {selectedTask.agent_usage?.length > 0 ? (
                            <table className="task-table">
                              <thead>
                                <tr>
                                  <th>Agent</th>
                                  <th>调用次数</th>
                                  <th>Prompt Tokens</th>
                                  <th>Completion Tokens</th>
                                  <th>Total Tokens</th>
                                  <th>成本（元）</th>
                                </tr>
                              </thead>

                              <tbody>
                                {selectedTask.agent_usage.map((agent) => (
                                  <tr key={agent.agent_name}>
                                    <td>{agent.agent_name}</td>
                                    <td>--</td>
                                    <td>{agent.prompt_tokens}</td>
                                    <td>{agent.completion_tokens}</td>
                                    <td>{agent.total_tokens}</td>
                                    <td>{agent.total_cost_rmb}</td>
                                  </tr>
                                ))}
                              </tbody>
                            </table>
                          ) : (
                            <p>暂无 Agent 使用统计</p>
                          )}
                        </div>
                      </div>
                    )}
                  </div>
                </div>
              )}
            </div>
          )}

          {currentPage === "agents" && (
            <div className="agent-workspace">
              {/* 左侧对话区域 */}
              <div className="agent-chat-panel">
                <div className="agent-panel-header">
                  <div>
                    <h2>数据分析 Agent</h2>
                    <p>向多个智能体提问，完成数据分析任务</p>
                  </div>

                  <button
                    className="agent-new-chat"
                    onClick={handleNewAgentConversation}
                    disabled={agentSending || agentActionLoading}
                  >
                    + 新建对话
                  </button>
                </div>

                <div className="agent-message-list">
                  {agentMessages.length === 0 && (
                    <div className="agent-empty">
                      <div className="agent-empty-icon">✦</div>
                      <h3>你好，我是数据分析 Agent</h3>
                      <p>
                        你可以直接提出数据分析问题，我会调用相应的 Agent
                        完成任务。
                      </p>
                      <div className="agent-examples">
                        <button
                          onClick={() =>
                            setAgentInput("请介绍一下当前数据分析中台的功能")
                          }
                        >
                          介绍数据分析中台
                        </button>
                        <button
                          onClick={() =>
                            setAgentInput("帮我分析最近一段时间的业务数据表现")
                          }
                        >
                          分析业务数据表现
                        </button>
                      </div>
                    </div>
                  )}

                  {agentMessages.map((message) => (
                    <div
                      key={message.id}
                      className={`agent-message ${message.role}`}
                    >
                      <div className="agent-message-avatar">
                        {message.role === "user" ? "我" : "AI"}
                      </div>
                      <div className="agent-message-content">
                        <div className="agent-message-role">
                          {message.role === "user" ? "你" : "数据分析 Agent"}
                        </div>
                        <pre>{message.content}</pre>
                      </div>
                    </div>
                  ))}

                  {agentSending && (
                    <div className="agent-thinking">
                      <span className="agent-loading-dot"></span>
                      Agent 正在处理你的问题，请稍候……
                    </div>
                  )}

                  <div />
                </div>

                {agentError && <div className="agent-error">{agentError}</div>}

                <form
                  className="agent-input-area"
                  onSubmit={(event) => {
                    event.preventDefault();
                    handleAgentSend();
                  }}
                >
                  <textarea
                    value={agentInput}
                    onChange={(event) => setAgentInput(event.target.value)}
                    placeholder="输入你的数据分析问题……"
                    maxLength={2000}
                    rows={3}
                    disabled={agentSending || agentActionLoading}
                  />

                  <div className="agent-input-footer">
                    <span>{agentInput.length}/2000</span>
                    <button
                      type="submit"
                      disabled={
                        !agentInput.trim() || agentSending || agentActionLoading
                      }
                    >
                      {agentSending ? "处理中..." : "发送问题"}
                    </button>
                  </div>
                </form>
              </div>

              {/* 右侧任务执行区域 */}
              <aside className="agent-task-panel">
                <h3>任务执行详情</h3>

                {!agentTask ? (
                  <div className="agent-task-empty">
                    <span>◷</span>
                    <p>提交问题后，这里将展示任务状态和执行结果。</p>
                  </div>
                ) : (
                  <>
                    <div className="agent-task-meta">
                      <div>
                        <span>任务状态</span>
                        <strong>{agentTask.status}</strong>
                      </div>
                      <div>
                        <span>任务类型</span>
                        <strong>{agentTask.task_type || "--"}</strong>
                      </div>
                      <div>
                        <span>任务 ID</span>
                        <small>{agentTask.task_id}</small>
                      </div>
                    </div>

                    <div className="agent-task-section">
                      <h4>工作流执行步骤</h4>

                      {workflowSteps.map((step) => {
                        const status = agentTask.steps?.[step.key] || "pending";

                        return (
                          <div className="agent-step" key={step.key}>
                            <span className={`agent-step-dot ${status}`} />
                            <span>{step.label}</span>
                            <small>{status}</small>
                          </div>
                        );
                      })}
                    </div>

                    {agentTask.status === "awaiting_approval" && (
                      <div className="agent-approval">
                        <h4>SQL 待审批</h4>
                        <pre>{agentTask.sql || "暂无 SQL 内容"}</pre>
                        <div className="agent-approval-actions">
                          <button
                            onClick={() => handleAgentDecision("approve")}
                            disabled={agentActionLoading}
                          >
                            {agentActionLoading ? "处理中..." : "批准执行"}
                          </button>
                          <button
                            onClick={() => handleAgentDecision("reject")}
                            disabled={agentActionLoading}
                          >
                            拒绝
                          </button>
                        </div>
                      </div>
                    )}

                    {agentTask.error && (
                      <div className="agent-task-error">
                        <h4>执行错误</h4>
                        <p>{agentTask.error}</p>
                      </div>
                    )}

                    {agentTask.report && (
                      <div className="agent-task-section">
                        <h4>分析报告</h4>
                        <pre className="agent-result">
                          {typeof agentTask.report === "string"
                            ? agentTask.report
                            : JSON.stringify(agentTask.report, null, 2)}
                        </pre>
                      </div>
                    )}

                    {agentTask.query_results?.length > 0 && (
                      <div className="agent-task-section">
                        <h4>查询结果</h4>
                        <pre className="agent-result">
                          {JSON.stringify(agentTask.query_results, null, 2)}
                        </pre>
                      </div>
                    )}
                  </>
                )}
              </aside>
            </div>
          )}
        </section>
      </main>
    </div>
  );
}

export default App;
