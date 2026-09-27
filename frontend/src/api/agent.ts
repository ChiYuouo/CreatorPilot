import axios from "axios";
import { useAuthStore } from "../stores/auth";
import client from "./client";

/** Agent SSE 事件类型（与后端 app/agents/events.py 对齐） */
export type AgentEvent =
  | { type: "session"; session_id: string }
  | {
      type: "stage";
      stage: string;
      status: string;
      route?: string;
      reason?: string;
    }
  | { type: "token"; text: string }
  | { type: "tool_call"; id: string; name: string; arguments: string }
  | {
      type: "tool_result";
      id: string;
      name: string;
      ok: boolean;
      output: unknown;
    }
  | { type: "done"; final_content: string }
  | { type: "error"; message: string };

export interface HistoryMessage {
  role: string;
  content: string;
}

/** 读取会话历史 */
export async function getAgentHistory(
  sessionId: string
): Promise<HistoryMessage[]> {
  const { data } = await client.get<{ messages: HistoryMessage[] }>(
    `/agent/sessions/${sessionId}/messages`
  );
  return data.messages;
}

/** 删除会话历史与工具记忆 */
export async function deleteAgentSession(sessionId: string): Promise<void> {
  await client.delete(`/agent/sessions/${encodeURIComponent(sessionId)}`);
}

async function requestOnce(
  payload: { session_id?: string | null; message: string },
  token: string | null
): Promise<Response> {
  return fetch("/api/v1/agent/chat", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: JSON.stringify(payload),
  });
}

/** 401 时用 refresh token 换新（裸请求，避免复用拦截器造成循环） */
async function tryRefreshToken(): Promise<boolean> {
  const refreshToken = useAuthStore.getState().refreshToken;
  if (!refreshToken) return false;
  try {
    const { data } = await axios.post("/api/v1/auth/refresh", {
      refresh_token: refreshToken,
    });
    useAuthStore
      .getState()
      .setAuth(data.access_token, data.refresh_token, data.user);
    return true;
  } catch {
    return false;
  }
}

/**
 * 与 Agent 对话（SSE 流式）。事件逐个回调给 onEvent。
 * 401 时自动尝试刷新 token 并重试一次，失败则抛错。
 */
export async function streamAgentChat(
  payload: { session_id?: string | null; message: string },
  onEvent: (event: AgentEvent) => void,
  signal?: AbortSignal
): Promise<void> {
  let resp = await requestOnce(payload, useAuthStore.getState().accessToken);

  if (resp.status === 401 && (await tryRefreshToken())) {
    resp = await requestOnce(payload, useAuthStore.getState().accessToken);
  }

  if (!resp.ok || !resp.body) {
    if (resp.status === 401) {
      useAuthStore.getState().clear();
      throw new Error("登录状态已过期，请重新登录");
    }
    const data = await resp.json().catch(() => null);
    throw new Error(data?.message ?? `请求失败（HTTP ${resp.status}）`);
  }

  const reader = resp.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  const handleFrames = () => {
    const frames = buffer.split("\n\n");
    buffer = frames.pop() ?? "";
    for (const frame of frames) {
      const line = frame.trim();
      if (!line.startsWith("data: ")) continue;
      try {
        onEvent(JSON.parse(line.slice("data: ".length)) as AgentEvent);
      } catch {
        // 坏帧直接跳过，不中断流
      }
    }
  };

  for (;;) {
    if (signal?.aborted) {
      await reader.cancel();
      return;
    }
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    handleFrames();
  }
  handleFrames();
}
