import { useEffect, useRef, useState } from "react";
import { isAxiosError } from "axios";
import { useNavigate } from "react-router-dom";
import { Bot, MessageSquare, Plus, Trash2 } from "lucide-react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { Bubble, Sender, ThoughtChain } from "@ant-design/x";
import { RobotOutlined, UserOutlined } from "@ant-design/icons";
import { Spin, message as antdMessage } from "antd";

import { Button } from "@/components/ui/button";
import { Dialog } from "@/components/ui/dialog";
import ConsoleLayout from "@/components/ConsoleLayout";
import { useAuthStore } from "@/stores/auth";
import {
  getAgentHistory,
  deleteAgentSession,
  streamAgentChat,
  type AgentEvent,
} from "@/api/agent";

interface SavedSession { id: string; title: string }

function sessionStorageKey(userId: number) { return `creatorpilot.agent.${userId}.sessionId`; }
function sessionListKey(userId: number) { return `creatorpilot.agent.${userId}.sessions`; }

type StepStatus = "pending" | "success" | "error";

interface ThoughtStep {
  key: string;
  title: string;
  description?: string;
  status: StepStatus;
}

interface ChatMessage {
  key: string;
  role: "user" | "assistant";
  content: string;
  steps: ThoughtStep[];
  status: "pending" | "streaming" | "done" | "error";
  assets?: AssetOption[];
}

interface AssetOption { id: number; filename: string; media_type: "video" | "image" }

const toolLabels: Record<string, string> = {
  list_assets: "查询素材", get_asset: "查看所选素材", list_accounts: "查询账号",
  list_platforms: "查询平台发布要求", submit_publish: "提交发布任务",
  list_publish_jobs: "查询发布任务", get_publish_status: "查询发布进度",
  get_current_datetime: "获取当前时间", get_platform_guidelines: "查询创作规范",
  list_published_contents: "查询作品和指标", get_content_metrics: "查看作品指标",
  sync_account_metrics: "提交指标同步", get_metrics_sync_status: "查询同步进度",
  generate_analysis_report: "提交分析报告", get_analysis_run_status: "查询分析进度",
  list_analysis_reports: "查询报告列表", get_analysis_report: "读取分析报告",
  list_automation_tasks: "查询自动化计划", get_automation_task: "查看自动化计划",
  create_automation_task: "创建自动化计划", update_automation_task: "修改自动化计划",
  set_automation_enabled: "暂停或恢复计划", delete_automation_task: "删除自动化计划",
  list_automation_runs: "查询自动化执行历史", get_automation_run: "查看自动化执行结果",
};

function assetOptions(output: unknown): AssetOption[] | undefined {
  if (!output || typeof output !== "object" || !("items" in output) || !Array.isArray(output.items)) return;
  return output.items.filter((item): item is AssetOption => item && typeof item.id === "number"
    && typeof item.filename === "string" && ["video", "image"].includes(item.media_type));
}

function newSessionId(): string {
  return crypto.randomUUID().replace(/-/g, "");
}

function loadSessions(userId: number): SavedSession[] {
  try {
    const parsed: unknown = JSON.parse(localStorage.getItem(sessionListKey(userId)) ?? "[]");
    return Array.isArray(parsed) ? parsed.filter((item): item is SavedSession => typeof item?.id === "string" && typeof item?.title === "string").slice(0, 20) : [];
  } catch { return []; }
}

function loadSessionId(userId: number): string {
  return localStorage.getItem(sessionStorageKey(userId)) ?? localStorage.getItem("creatorpilot.agent.sessionId") ?? newSessionId();
}

function routeName(route?: string): string {
  if (route === "content_agent") return "内容生产";
  if (route === "direct_reply") return "直接回复";
  if (route === "operations_agent") return "业务操作";
  return "未识别";
}

function stageStep(event: Extract<AgentEvent, { type: "stage" }>): ThoughtStep {
  const titles: Record<string, string> = {
    supervisor: "Supervisor 分派任务",
    content_agent: "Content Agent 内容生产",
    direct_reply: "直接回复",
    operations_agent: "查询数据与执行业务任务",
  };
  const title = titles[event.stage] ?? event.stage;
  const status: StepStatus = event.status === "start" ? "pending" : "success";
  let description: string | undefined;
  if (event.stage === "supervisor" && event.status === "done") {
    description = `路由：${routeName(event.route)}${
      event.reason ? `（${event.reason}）` : ""
    }`;
  }
  return { key: `stage-${event.stage}`, title, status, description };
}

function describeToolOutput(output: unknown): string {
  let text: string;
  try {
    text = JSON.stringify(output);
  } catch {
    text = String(output);
  }
  return text.length > 200 ? `${text.slice(0, 200)}…` : text;
}

function AssistantContent({ message, onSelectAsset, disabled }: {
  message: ChatMessage; onSelectAsset: (asset: AssetOption) => void; disabled: boolean;
}) {
  return (
    <div className="flex min-w-0 flex-col gap-2">
      {message.steps.length > 0 && (
        <ThoughtChain
          size="small"
          items={message.steps.map((s) => ({
            key: s.key,
            title: s.title,
            description: s.description,
            status: s.status,
          }))}
        />
      )}
      {message.content && <div className="cp-markdown">
        <ReactMarkdown remarkPlugins={[remarkGfm]} components={{
          table: ({ children }) => <div className="max-w-full overflow-x-auto rounded-md border border-border"><table className="w-full border-collapse text-left text-sm">{children}</table></div>,
          th: ({ children }) => <th className="whitespace-nowrap border-b border-border bg-muted px-3 py-2 font-medium">{children}</th>,
          td: ({ children }) => <td className="min-w-24 border-b border-border px-3 py-2 align-top">{children}</td>,
        }}>{message.content}</ReactMarkdown>
      </div>}
      {!!message.assets?.length && <div className="space-y-2">
        {message.assets.map((asset) => <div key={asset.id} className="flex items-center gap-3 rounded-md border border-border p-3">
          <div className="min-w-0 flex-1"><strong className="block truncate text-sm">{asset.filename}</strong><small className="text-muted-foreground">ID {asset.id} · {asset.media_type === "video" ? "视频" : "图片"}</small></div>
          <Button type="button" size="sm" variant="outline" disabled={disabled} onClick={() => onSelectAsset(asset)}>选择</Button>
        </div>)}
        <small className="text-muted-foreground">选择后会填入素材 ID，发送消息即可继续；不会直接发布。</small>
      </div>}
    </div>
  );
}

export default function AgentChat() {
  const navigate = useNavigate();
  const userId = useAuthStore((state) => state.user?.id ?? 0);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [sessionId, setSessionId] = useState(() => loadSessionId(userId));
  const [sessions, setSessions] = useState<SavedSession[]>(() => loadSessions(userId));
  const [input, setInput] = useState("");
  const [streaming, setStreaming] = useState(false);
  const [historyLoading, setHistoryLoading] = useState(true);
  const [switching, setSwitching] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState<SavedSession | null>(null);
  const [deleting, setDeleting] = useState(false);
  const listRef = useRef<HTMLDivElement>(null);
  const abortRef = useRef<AbortController | null>(null);
  const switchTimerRef = useRef<number | null>(null);

  // 切换会话时恢复该用户的历史
  useEffect(() => {
    let cancelled = false;
    setHistoryLoading(true);
    localStorage.setItem(sessionStorageKey(userId), sessionId);
    getAgentHistory(sessionId)
      .then((history) => {
        if (cancelled) return;
        const firstUserMessage = history.find((item) => item.role === "user");
        if (firstUserMessage) setSessions((previous) => {
          if (previous.some((item) => item.id === sessionId)) return previous;
          const next = [{ id: sessionId, title: firstUserMessage.content.slice(0, 32) }, ...previous].slice(0, 20);
          localStorage.setItem(sessionListKey(userId), JSON.stringify(next));
          return next;
        });
        setMessages(
          history
            .filter((m) => m.role === "user" || m.role === "assistant")
            .map((m, i) => ({
              key: `hist-${i}`,
              role: m.role as "user" | "assistant",
              content: m.content,
              steps: [],
              status: "done" as const,
            }))
        );
      })
      .catch(() => {
        // 历史恢复失败不阻塞使用
      })
      .finally(() => { if (!cancelled) setHistoryLoading(false); });
    return () => {
      cancelled = true;
    };
  }, [sessionId, userId]);

  // 自动滚动到底部
  useEffect(() => {
    const el = listRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [messages]);

  useEffect(() => {
    return () => {
      abortRef.current?.abort();
      if (switchTimerRef.current !== null) window.clearTimeout(switchTimerRef.current);
    };
  }, []);

  const updateMessage = (
    key: string,
    updater: (m: ChatMessage) => ChatMessage
  ) => {
    setMessages((prev) => prev.map((m) => (m.key === key ? updater(m) : m)));
  };

  const handleEvent = (key: string, event: AgentEvent) => {
    switch (event.type) {
      case "session":
        setSessionId(event.session_id);
        localStorage.setItem(sessionStorageKey(userId), event.session_id);
        break;
      case "stage": {
        const step = stageStep(event);
        updateMessage(key, (m) => ({
          ...m,
          status: "streaming",
          steps: m.steps.some((s) => s.key === step.key)
            ? m.steps.map((s) => (s.key === step.key ? step : s))
            : [...m.steps, step],
        }));
        break;
      }
      case "tool_call":
        updateMessage(key, (m) => ({
          ...m,
          steps: [
            ...m.steps,
            {
              key: `tool-${event.id}`,
              title: toolLabels[event.name] ?? `调用工具：${event.name}`,
              status: "pending",
              description: event.arguments,
            },
          ],
        }));
        break;
      case "tool_result":
        updateMessage(key, (m) => ({
          ...m,
          assets: event.ok && event.name === "list_assets" ? assetOptions(event.output) : m.assets,
          steps: m.steps.map((s) =>
            s.key === `tool-${event.id}`
              ? {
                  ...s,
                  status: event.ok ? "success" : "error",
                  description: describeToolOutput(event.output),
                }
              : s
          ),
        }));
        break;
      case "token":
        updateMessage(key, (m) => ({
          ...m,
          status: "streaming",
          content: m.content + event.text,
        }));
        break;
      case "done":
        updateMessage(key, (m) => ({ ...m, status: "done", content: event.final_content }));
        break;
      case "error":
        antdMessage.error(event.message);
        updateMessage(key, (m) => ({
          ...m,
          status: "error",
          content: m.content || `⚠️ ${event.message}`,
        }));
        break;
    }
  };

  const handleSubmit = async (value: string) => {
    const text = value.trim();
    if (!text || streaming || historyLoading || switching || deleteTarget || deleting) return;
    setInput("");
    setStreaming(true);
    setSessions((previous) => {
      const existing = previous.find((item) => item.id === sessionId);
      const next = [{ id: sessionId, title: existing?.title ?? text.slice(0, 32) }, ...previous.filter((item) => item.id !== sessionId)].slice(0, 20);
      localStorage.setItem(sessionListKey(userId), JSON.stringify(next));
      return next;
    });
    const assistantKey = crypto.randomUUID();
    setMessages((prev) => [
      ...prev,
      {
        key: crypto.randomUUID(),
        role: "user",
        content: text,
        steps: [],
        status: "done",
      },
      {
        key: assistantKey,
        role: "assistant",
        content: "",
        steps: [],
        status: "pending",
      },
    ]);

    abortRef.current = new AbortController();
    try {
      await streamAgentChat(
        { session_id: sessionId, message: text },
        (event) => handleEvent(assistantKey, event),
        abortRef.current.signal
      );
    } catch (error) {
      const text2 =
        error instanceof Error ? error.message : "请求失败，请稍后重试";
      antdMessage.error(text2);
      updateMessage(assistantKey, (m) => ({
        ...m,
        status: "error",
        content: m.content || `⚠️ ${text2}`,
      }));
      if (text2.includes("登录状态已过期")) {
        navigate("/login", { replace: true });
      }
    } finally {
      setStreaming(false);
    }
  };

  const switchSession = (id: string) => {
    if (streaming || switching || deleting || id === sessionId) return;
    setSwitching(true);
    switchTimerRef.current = window.setTimeout(() => {
      setHistoryLoading(true);
      setMessages([]);
      setInput("");
      setSessionId(id);
      setSwitching(false);
      switchTimerRef.current = null;
    }, 140);
  };

  const handleNewChat = () => switchSession(newSessionId());
  const openSession = (id: string) => switchSession(id);

  const handleDeleteSession = async () => {
    if (!deleteTarget || deleting || streaming || switching || historyLoading) return;
    setDeleting(true);
    try {
      await deleteAgentSession(deleteTarget.id);
      const next = sessions.filter((session) => session.id !== deleteTarget.id);
      localStorage.setItem(sessionListKey(userId), JSON.stringify(next));
      setSessions(next);
      if (deleteTarget.id === sessionId) {
        const freshId = newSessionId();
        localStorage.setItem(sessionStorageKey(userId), freshId);
        localStorage.removeItem("creatorpilot.agent.sessionId");
        setMessages([]);
        setInput("");
        setHistoryLoading(true);
        setSessionId(freshId);
      }
      setDeleteTarget(null);
      antdMessage.success("对话已删除");
    } catch (error) {
      const detail = isAxiosError(error)
        ? error.response?.status === 404
          ? "后端尚未加载删除接口，请重启后端后再试"
          : error.response?.data?.message ?? (error.response ? `请求失败（HTTP ${error.response.status}）` : "无法连接后端，请检查服务是否启动")
        : "删除失败，请稍后重试";
      antdMessage.error(detail);
    } finally {
      setDeleting(false);
    }
  };

  return (
    <ConsoleLayout className="cp-legacy" eyebrow="AI / AGENT WORKFLOW" title="AI 运营助手" description="通过对话完成选题、文案创作与运营建议">
      <div className="cp-chat">
      <aside className="cp-chat-sidebar" aria-label="会话列表">
        <Button variant="outline" onClick={handleNewChat} disabled={streaming || switching || deleting} className="w-full justify-start"><Plus className="mr-2 size-4" />新会话</Button>
        <div className="cp-chat-sidebar-title">最近会话</div>
        <div className="cp-chat-sessions">{sessions.map((session) => <div key={session.id} className={`flex min-w-0 shrink-0 items-center rounded-md ${session.id === sessionId ? "bg-accent" : ""}`}>
          <Button type="button" variant="ghost" disabled={streaming || switching || deleting} onClick={() => openSession(session.id)} className="min-w-0 flex-1 justify-start text-left" title={session.title}><MessageSquare className="size-4 shrink-0" /><span className="truncate">{session.title}</span></Button>
          <Button type="button" variant="ghost" size="icon" disabled={streaming || switching || historyLoading || deleting} onClick={() => setDeleteTarget(session)} aria-label={`删除对话：${session.title}`} title="删除对话" className="size-8 shrink-0 text-muted-foreground hover:text-destructive"><Trash2 /></Button>
        </div>)}</div>
      </aside>
      <div className="cp-chat-main">

      <div ref={listRef} className="flex-1 overflow-y-auto px-4 py-6">
        <div key={`${sessionId}-${historyLoading ? "loading" : "ready"}`} className={`cp-chat-conversation mx-auto max-w-3xl ${switching ? "is-leaving" : ""}`}>
          {historyLoading ? <div className="mt-24 text-center text-sm text-muted-foreground"><Spin size="small" /> <span className="ml-2">正在打开会话…</span></div> : messages.length === 0 ? (
            <div className="mt-24 text-center">
              <Bot className="mx-auto mb-4 size-10 text-primary" />
              <h2 className="mb-2 text-xl font-semibold">开始创作或执行任务</h2>
              <p className="text-sm text-muted-foreground">
                试试：我有哪些素材？ / 查询发布进度 / 分析账号最近 7 天的表现 / 查看已有报告
              </p>
            </div>
          ) : (
            <Bubble.List
              items={messages.map((m) => ({
                key: m.key,
                role: m.role,
                content:
                  m.role === "assistant" ? (
                    <AssistantContent message={m} disabled={streaming || historyLoading || switching}
                      onSelectAsset={(asset) => setInput(`选择素材 ID ${asset.id}（${asset.filename}）`)} />
                  ) : (
                    m.content
                  ),
                loading: m.role === "assistant" && m.status === "pending",
              }))}
              roles={{
                user: {
                  placement: "end",
                  avatar: {
                    icon: <UserOutlined />,
                    style: { background: "#e5e5e5" },
                  },
                },
                assistant: {
                  placement: "start",
                  avatar: {
                    icon: <RobotOutlined />,
                    style: { background: "#f5f5f5" },
                  },
                  loadingRender: () => <Spin size="small" />,
                },
              }}
            />
          )}
        </div>
      </div>

      <div className="border-t px-4 py-3">
        <div className="mx-auto max-w-3xl">
          <Sender
            value={input}
            onChange={setInput}
            onSubmit={handleSubmit}
            loading={streaming}
            disabled={historyLoading || switching || deleting || !!deleteTarget}
            placeholder="查询素材、创作文案、发布视频，或同步指标并生成分析报告"
          />
        </div>
      </div>
      </div>
      </div>
      <Dialog open={!!deleteTarget} onOpenChange={(open) => { if (!open && !deleting) setDeleteTarget(null); }} title="删除对话" description="删除聊天记录和工具记忆，已创建的发布任务与报告会保留。" className="max-w-md">
        <p className="break-words text-sm">确定删除“{deleteTarget?.title}”吗？删除后无法恢复。</p>
        <div className="mt-5 flex justify-end gap-2">
          <Button type="button" variant="outline" disabled={deleting} onClick={() => setDeleteTarget(null)}>取消</Button>
          <Button type="button" variant="destructive" disabled={deleting} onClick={() => void handleDeleteSession()}>{deleting ? "正在删除…" : "删除"}</Button>
        </div>
      </Dialog>
    </ConsoleLayout>
  );
}
