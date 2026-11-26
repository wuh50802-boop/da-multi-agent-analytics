// 后端 API 基础地址
export const API_BASE_URL = "http://127.0.0.1:8000";

// 统一构建日期筛选参数
export function getDateQueryString(startDate, endDate) {
  const params = new URLSearchParams();

  if (startDate) {
    params.append("start_time", `${startDate}T00:00:00`);
  }

  if (endDate) {
    params.append("end_time", `${endDate}T23:59:59`);
  }

  return params.toString();
}


// 统一 API 请求函数
export async function apiRequest(
  url,
  signal,
  errorMessage,
  options = {}
) {
  let response;

  try {
    response = await fetch(url, {
      signal,
      ...options,
    });
  } catch (err) {
    if (err.name === "AbortError") {
      throw err;
    }

    throw new Error(`${errorMessage}：网络连接失败，请检查服务是否正常运行`);
  }

  if (!response.ok) {
    let detail = "";

    try {
      const errorData = await response.json();
      detail = errorData.detail || "";
    } catch {
      // 后端没有返回 JSON 时使用状态码
    }

    throw new Error(
      `${errorMessage}：${detail || `HTTP ${response.status}`}`
    );
  }

  try {
    return await response.json();
  } catch {
    throw new Error(`${errorMessage}：服务器返回的数据格式异常`);
  }
}


// 构建 Dashboard 接口地址
export function buildDashboardUrl(endpoint, queryString = "") {
  return queryString
    ? `${API_BASE_URL}/dashboard/${endpoint}?${queryString}`
    : `${API_BASE_URL}/dashboard/${endpoint}`;
}