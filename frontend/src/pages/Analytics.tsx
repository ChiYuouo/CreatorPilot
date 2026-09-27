import { useEffect, useMemo, useRef, useState, type FormEvent } from "react";
import { History, Pencil, Plus, Trash2 } from "lucide-react";
import { toast } from "sonner";

import { analyticsApi, type AnalyticsReport, type MetricWrite, type PublishedContent, type PublishedContentWrite, type MetricsSyncRun } from "@/api/analytics";
import { publishingApi, type PlatformAccount } from "@/api/publishing";
import type { AnalyticsPlatform as Platform } from "@/api/analytics";
import { Button } from "@/components/ui/button";
import { Dialog } from "@/components/ui/dialog";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { DatePicker } from "@/components/ui/date-picker";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { SelectField } from "@/components/ui/select";
import { TimePicker } from "@/components/ui/time-picker";
import AnalyticsReportView from "@/components/AnalyticsReportView";
import AnalyticsReportHistory from "@/components/AnalyticsReportHistory";
import MetricsChart from "@/components/MetricsChart";
import ConsoleLayout from "@/components/ConsoleLayout";

const platforms: { value: Platform; label: string }[] = [
  { value: "xiaohongshu", label: "小红书" },
  { value: "douyin", label: "抖音" },
  { value: "kuaishou", label: "快手" },
  { value: "bilibili", label: "B站" },
  { value: "tencent", label: "视频号" },
  { value: "youtube", label: "YouTube" },
];
const metricFields = [
  { key: "views", label: "浏览" },
  { key: "likes", label: "点赞" },
  { key: "comments", label: "评论" },
  { key: "favorites", label: "收藏" },
  { key: "shares", label: "分享" },
  { key: "follower_gain", label: "累计新增粉丝" },
] as const;

const localDate = () => {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
};
const localDateTime = () => {
  const d = new Date();
  return `${localDate()}T${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`;
};
const emptyMetric = (): MetricWrite => ({ metric_date: localDate(), views: null, likes: null, comments: null, favorites: null, shares: null, follower_gain: null });
const syncLabels = { queued: "等待本机服务", running: "同步中", completed: "已完成", failed: "失败" };

function errorMessage(error: unknown, fallback: string): string {
  if (typeof error === "object" && error !== null && "response" in error) {
    const response = (error as { response?: { data?: { message?: string } } }).response;
    if (response?.data?.message) return response.data.message;
  }
  return fallback;
}

export default function Analytics() {
  const [contents, setContents] = useState<PublishedContent[]>([]);
  const [accounts, setAccounts] = useState<PlatformAccount[]>([]);
  const [syncRuns, setSyncRuns] = useState<MetricsSyncRun[]>([]);
  const [syncHistoryOpen, setSyncHistoryOpen] = useState(false);
  const [syncAccountId, setSyncAccountId] = useState("");
  const [syncSubmitting, setSyncSubmitting] = useState(false);
  const [deletingSyncId, setDeletingSyncId] = useState<number | null>(null);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [editingContentId, setEditingContentId] = useState<number | null>(null);
  const [platform, setPlatform] = useState<Platform>("xiaohongshu");
  const [title, setTitle] = useState("");
  const [publishedAt, setPublishedAt] = useState(localDateTime);
  const [metric, setMetric] = useState<MetricWrite>(emptyMetric);
  const [loading, setLoading] = useState(true);
  const [savingContent, setSavingContent] = useState(false);
  const [savingMetric, setSavingMetric] = useState(false);
  const [contentEditorOpen, setContentEditorOpen] = useState(false);
  const [metricEditorOpen, setMetricEditorOpen] = useState(false);
  const [reportHistoryOpen, setReportHistoryOpen] = useState(false);
  const [batchReport, setBatchReport] = useState<AnalyticsReport | null>(null);
  const [contentReport, setContentReport] = useState<AnalyticsReport | null>(null);
  const [runningBatch, setRunningBatch] = useState(false);
  const [runningContent, setRunningContent] = useState(false);
  const selectedIdRef = useRef<number | null>(null);

  const selected = useMemo(() => contents.find((item) => item.id === selectedId) ?? null, [contents, selectedId]);
  const orderedMetrics = useMemo(() => [...(selected?.metrics ?? [])].sort((a, b) => b.metric_date.localeCompare(a.metric_date)), [selected]);

  useEffect(() => {
    analyticsApi.listContents()
      .then((items) => { setContents(items); if (items[0]) { setSelectedId(items[0].id); selectedIdRef.current = items[0].id; } })
      .catch((error) => toast.error(errorMessage(error, "数据加载失败")))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    Promise.all([publishingApi.accounts(), publishingApi.platforms()]).then(([items, specs]) => {
      const supported = items.filter((item) => specs.some((spec) => spec.key === item.platform && spec.metrics_sync_supported));
      setAccounts(supported);
      setSyncAccountId(supported[0] ? String(supported[0].id) : "");
    }).catch(() => toast.error("账号加载失败"));
    analyticsApi.syncRuns().then(setSyncRuns).catch(() => toast.error("同步记录加载失败"));
  }, []);

  const syncPending = syncRuns.some((run) => run.status === "queued" || run.status === "running");
  useEffect(() => {
    if (!syncPending) return;
    let disposed = false;
    let inFlight = false;
    const timer = window.setInterval(async () => {
      if (inFlight) return;
      inFlight = true;
      try {
        const runs = await analyticsApi.syncRuns();
        const items = await analyticsApi.listContents();
        if (!disposed) {
          setSyncRuns(runs); setContents(items); setBatchReport(null); setContentReport(null);
          if (selectedIdRef.current === null && items[0]) {
            selectedIdRef.current = items[0].id; setSelectedId(items[0].id);
          }
        }
      } catch { /* 短暂断网后下一轮继续；任务状态保存在服务端。 */ }
      finally { inFlight = false; }
    }, 3000);
    return () => { disposed = true; window.clearInterval(timer); };
  }, [syncPending]);

  const syncAccount = async () => {
    if (!syncAccountId) return;
    setSyncSubmitting(true);
    try {
      const run = await analyticsApi.syncAccount(Number(syncAccountId));
      setSyncRuns(await analyticsApi.syncRuns());
      if (run.status === "failed") toast.error(run.message ?? "同步任务入队失败");
      else toast.success("同步已排队，完成后会自动更新作品与指标");
    } catch (error) { toast.error(errorMessage(error, "同步启动失败")); }
    finally { setSyncSubmitting(false); }
  };

  const deleteSyncRun = async (id: number) => {
    if (!window.confirm("确定删除这条同步记录？已同步的作品和指标会保留。")) return;
    setDeletingSyncId(id);
    try {
      await analyticsApi.deleteSyncRun(id);
      setSyncRuns((items) => items.filter((item) => item.id !== id));
      toast.success("同步记录已删除");
    } catch (error) { toast.error(errorMessage(error, "同步记录删除失败")); }
    finally { setDeletingSyncId(null); }
  };

  const selectContent = (item: PublishedContent) => {
    selectedIdRef.current = item.id;
    setSelectedId(item.id);
    setPlatform(item.platform);
    setTitle(item.title);
    setPublishedAt(new Date(item.published_at).toLocaleString("sv-SE").replace(" ", "T").slice(0, 16));
    setMetric(emptyMetric());
    setContentReport(null);
  };
  const startNew = () => {
    setEditingContentId(null);
    setPlatform("xiaohongshu");
    setTitle("");
    setPublishedAt(localDateTime());
    setMetric(emptyMetric());
    setContentEditorOpen(true);
  };

  const saveContent = async (event: FormEvent) => {
    event.preventDefault();
    if (!title.trim() || !publishedAt || Number.isNaN(new Date(publishedAt).getTime())) {
      toast.error("请填写标题和有效的发布时间");
      return;
    }
    const payload: PublishedContentWrite = { platform, title: title.trim(), published_at: new Date(publishedAt).toISOString() };
    setSavingContent(true);
    try {
      const saved = editingContentId === null ? await analyticsApi.createContent(payload) : await analyticsApi.updateContent(editingContentId, payload);
      setContents((items) => [saved, ...items.filter((item) => item.id !== saved.id)]);
      selectContent(saved);
      setContentEditorOpen(false);
      setBatchReport(null);
      toast.success(editingContentId === null ? "已登记发布内容" : "发布内容已更新");
    } catch (error) {
      toast.error(errorMessage(error, "保存失败"));
    } finally { setSavingContent(false); }
  };

  const removeContent = async () => {
    if (selectedId === null || !window.confirm("删除这篇已发布内容及全部指标记录？")) return;
    try {
      await analyticsApi.deleteContent(selectedId);
      const remaining = contents.filter((item) => item.id !== selectedId);
      setContents(remaining);
      setSelectedId(remaining[0]?.id ?? null);
      selectedIdRef.current = remaining[0]?.id ?? null;
      setContentReport(null);
      setBatchReport(null);
      toast.success("已删除");
    } catch (error) { toast.error(errorMessage(error, "删除失败")); }
  };

  const saveMetric = async (event: FormEvent) => {
    event.preventDefault();
    if (selectedId === null) return;
    setSavingMetric(true);
    try {
      await analyticsApi.saveMetric(selectedId, metric);
      const refreshed = await analyticsApi.listContents();
      setContents(refreshed);
      setMetric(emptyMetric());
      setMetricEditorOpen(false);
      setBatchReport(null);
      setContentReport(null);
      toast.success("累计指标已保存");
    } catch (error) { toast.error(errorMessage(error, "指标保存失败")); }
    finally { setSavingMetric(false); }
  };

  const removeMetric = async (metricDate: string) => {
    if (selectedId === null || !window.confirm(`删除 ${metricDate} 的指标记录？`)) return;
    try {
      await analyticsApi.deleteMetric(selectedId, metricDate);
      setContents(await analyticsApi.listContents());
      setBatchReport(null);
      setContentReport(null);
      toast.success("指标记录已删除");
    } catch (error) { toast.error(errorMessage(error, "删除失败")); }
  };

  const generateBatchReport = async () => {
    setRunningBatch(true);
    try {
      const result = await analyticsApi.batchReport();
      setBatchReport(result);
      toast.success("批量分析报告已保存");
    }
    catch (error) { toast.error(errorMessage(error, "汇总报告生成失败")); }
    finally { setRunningBatch(false); }
  };

  const generateContentReport = async () => {
    if (selectedId === null) return;
    const requestedId = selectedId;
    setRunningContent(true);
    try {
      const result = await analyticsApi.contentReport(requestedId);
      if (selectedIdRef.current === requestedId) setContentReport(result);
      toast.success("单篇分析报告已保存");
    }
    catch (error) { toast.error(errorMessage(error, "单篇报告生成失败")); }
    finally { setRunningContent(false); }
  };

  return (
    <ConsoleLayout className="cp-legacy" eyebrow="ANALYTICS / INSIGHTS" title="数据分析" description="同步平台作品与累计指标，生成运营报告">
      <div className="cp-legacy-body space-y-5">
        <p className="text-sm text-muted-foreground">同步已接入平台的公开作品，或手动登记各平台累计指标。未获取的指标显示为“未提供”，不计作零。</p>
        <Card><CardHeader className="flex-row items-center justify-between space-y-0"><CardTitle>平台数据同步</CardTitle><Button size="sm" variant="outline" onClick={() => { setSyncHistoryOpen(true); analyticsApi.syncRuns().then(setSyncRuns).catch(() => toast.error("同步记录加载失败")); }}><History className="mr-1 size-4" />同步记录{syncPending ? "（进行中）" : ""}</Button></CardHeader><CardContent className="space-y-3">
          <div className="flex flex-wrap items-end gap-3"><div className="min-w-56 space-y-1.5"><Label htmlFor="sync-account">平台账号</Label><SelectField id="sync-account" value={syncAccountId} onValueChange={setSyncAccountId} options={accounts.map((account) => ({ value: String(account.id), label: `${platforms.find((p) => p.value === account.platform)?.label ?? account.platform} · ${account.remark || account.account_name}${account.status === "expired" ? "（需重新登录）" : ""}` }))} /></div>
          <Button onClick={syncAccount} disabled={!syncAccountId || syncSubmitting || syncRuns.some((run) => run.account_id === Number(syncAccountId) && (run.status === "queued" || run.status === "running"))}>{syncSubmitting ? "提交中…" : "同步作品与指标"}</Button></div>
          <p className="text-xs text-muted-foreground">使用账号已有登录态，由本机服务执行；同一天的自动快照会更新，人工修正记录保留。当前接入抖音、B 站、快手、小红书、视频号同步；需先绑定对应账号。快手发布时间使用平台上传时间，采集范围沿用后台默认筛选。</p>
          {accounts.length === 0 && <p className="text-sm text-muted-foreground">请先到账号管理绑定支持同步的平台账号。</p>}
        </CardContent></Card>
        <Card><CardHeader className="flex-row items-center justify-between space-y-0"><CardTitle>批量内容分析</CardTitle><Button size="sm" variant="outline" onClick={() => setReportHistoryOpen(true)}><History className="mr-1 size-4" />分析历史</Button></CardHeader><CardContent className="space-y-4">
          <p className="text-sm text-muted-foreground">读取全部已保存的已发布内容和指标快照，一次交给模型进行逐篇比较与总体分析。报告生成后自动保存。</p>
          <Button onClick={generateBatchReport} disabled={runningBatch || loading || contents.length === 0} aria-busy={runningBatch}>{runningBatch ? "分析中…" : "生成批量报告"}</Button>
          {batchReport && <AnalyticsReportView report={batchReport} />}
        </CardContent></Card>
        <div className="grid gap-5 lg:grid-cols-[260px_minmax(0,1fr)]">
          <Card className="h-fit">
            <CardHeader className="flex-row items-center justify-between space-y-0"><CardTitle>已发布内容</CardTitle><Button size="sm" variant="outline" onClick={startNew} aria-label="新增已发布内容"><Plus className="size-4" /></Button></CardHeader>
            <CardContent className="space-y-2">
              {loading && <p className="text-sm text-muted-foreground">加载中…</p>}
              {!loading && contents.length === 0 && <p className="text-sm text-muted-foreground">暂无已发布内容。</p>}
              {contents.map((item) => <Button key={item.id} type="button" variant="outline" onClick={() => selectContent(item)} className={`h-auto w-full flex-col items-start whitespace-normal border p-3 text-left text-sm hover:border-primary ${selectedId === item.id ? "border-primary bg-accent" : "border-border"}`}>
                <span className="block w-full truncate font-medium">{item.title}</span>
                <span className="mt-1 block text-xs text-muted-foreground">{platforms.find((p) => p.value === item.platform)?.label} · {new Date(item.published_at).toLocaleDateString("zh-CN")}</span>
              </Button>)}
            </CardContent>
          </Card>
          <div className="space-y-5">
            {selected && <Card><CardHeader className="flex-row items-center justify-between space-y-0"><CardTitle>{selected.title}</CardTitle><div className="flex gap-2"><Button size="sm" variant="outline" onClick={() => { selectContent(selected); setEditingContentId(selected.id); setContentEditorOpen(true); }}><Pencil className="mr-1 size-4" />编辑</Button><Button size="sm" variant="ghost" onClick={removeContent} aria-label="删除已发布内容"><Trash2 className="size-4" /></Button></div></CardHeader><CardContent className="text-sm text-muted-foreground">{platforms.find((p) => p.value === selected.platform)?.label} · 发布于 {new Date(selected.published_at).toLocaleString("zh-CN")}{selected.platform_content_id && ["douyin", "bilibili", "kuaishou", "xiaohongshu"].includes(selected.platform) && <a className="ml-3 text-primary underline" href={selected.platform === "xiaohongshu" ? `https://creator.xiaohongshu.com/statistics/note-detail?noteId=${selected.platform_content_id}` : selected.platform === "bilibili" ? `https://www.bilibili.com/video/av${selected.platform_content_id}` : selected.platform === "kuaishou" ? `https://www.kuaishou.com/short-video/${selected.platform_content_id}` : `https://www.douyin.com/video/${selected.platform_content_id}`} target="_blank" rel="noreferrer">查看平台作品</a>}</CardContent></Card>}
            {selected && <>
               <Card><CardHeader><CardTitle>单篇内容分析</CardTitle></CardHeader><CardContent className="space-y-4"><Button onClick={generateContentReport} disabled={runningContent} aria-busy={runningContent}>{runningContent ? "分析中…" : "生成单篇报告"}</Button>{contentReport && <AnalyticsReportView report={contentReport} />}</CardContent></Card>
              <Card><CardHeader><CardTitle>累计指标趋势</CardTitle></CardHeader><CardContent><MetricsChart metrics={selected.metrics} /></CardContent></Card>
              <Card><CardHeader className="flex-row items-center justify-between space-y-0"><CardTitle>累计指标记录</CardTitle><Button size="sm" variant="outline" onClick={() => { setMetric(emptyMetric()); setMetricEditorOpen(true); }}><Plus className="mr-1 size-4" />录入指标</Button></CardHeader><CardContent>
                {orderedMetrics.length === 0 && <p className="text-sm text-muted-foreground">暂无指标记录，录入后可查看趋势。</p>}
                {orderedMetrics.length > 0 && <div className="space-y-2">{orderedMetrics.map((item) => <div key={item.id} className="flex flex-wrap items-center justify-between gap-2 rounded-md border p-3 text-sm"><span>{item.metric_date} · {item.source === "manual" ? "人工录入" : "平台同步"}{item.collected_at ? `（${new Date(item.collected_at).toLocaleString("zh-CN")}）` : ""} · 浏览 {item.views ?? "未提供"} · 点赞 {item.likes ?? "未提供"} · 评论 {item.comments ?? "未提供"} · 收藏 {item.favorites ?? "未提供"} · 分享 {item.shares ?? "未提供"} · 新增粉丝 {item.follower_gain ?? "未提供"}{item.platform_updated_at && <span className="mt-1 block text-xs text-muted-foreground">平台指标更新于 {new Date(item.platform_updated_at).toLocaleString("zh-CN")}</span>}</span><div className="flex gap-1"><Button size="sm" variant="ghost" onClick={() => { setMetric({ metric_date: item.metric_date, views: item.views, likes: item.likes, comments: item.comments, favorites: item.favorites, shares: item.shares, follower_gain: item.follower_gain }); setMetricEditorOpen(true); }}><Pencil className="mr-1 size-4" />修正</Button><Button size="sm" variant="ghost" onClick={() => removeMetric(item.metric_date)} aria-label={`删除 ${item.metric_date} 的指标`}><Trash2 className="size-4" /></Button></div></div>)}</div>}
              </CardContent></Card>
            </>}
          </div>
        </div>
      </div>
      <AnalyticsReportHistory open={reportHistoryOpen} onOpenChange={setReportHistoryOpen} onDeleted={(id) => {
        setBatchReport((report) => report?.id === id ? null : report);
        setContentReport((report) => report?.id === id ? null : report);
      }} />
      <Dialog open={syncHistoryOpen} onOpenChange={setSyncHistoryOpen} title="同步记录" description="最多保留最近 20 条，超出后自动删除最旧的已结束记录。排队或执行中的任务暂不能删除。">
        <div className="space-y-3">
          {syncRuns.length === 0 && <p className="text-sm text-muted-foreground">暂无同步记录。</p>}
          {syncRuns.map((run) => <div key={run.id} className="flex items-start gap-2 rounded-md border p-3 text-sm"><div className="min-w-0 flex-1"><span className="font-medium">{accounts.find((account) => account.id === run.account_id)?.remark || accounts.find((account) => account.id === run.account_id)?.account_name || `账号 #${run.account_id}`} · {syncLabels[run.status]}</span><span className="ml-2 text-xs text-muted-foreground">{new Date(run.created_at).toLocaleString("zh-CN")}</span><p className="mt-1 text-muted-foreground">{run.message || "等待本机同步服务处理，可稍后回来查看结果。"}</p></div><Button variant="ghost" size="sm" aria-label={`删除同步记录 ${run.id}`} title={run.status === "queued" || run.status === "running" ? "任务结束后才能删除" : "删除记录"} disabled={deletingSyncId !== null || run.status === "queued" || run.status === "running"} onClick={() => deleteSyncRun(run.id)}><Trash2 className="size-4" /></Button></div>)}
        </div>
      </Dialog>
      <Dialog open={contentEditorOpen} onOpenChange={setContentEditorOpen} title={editingContentId === null ? "登记发布内容" : "编辑发布内容"} description="登记平台上已发布的内容，便于录入指标和生成报告。" className="max-w-lg">
        <form onSubmit={saveContent} className="grid gap-4 sm:grid-cols-2">
          <div className="sm:col-span-2"><Label htmlFor="published-title">标题</Label><Input id="published-title" value={title} onChange={(e) => setTitle(e.target.value)} maxLength={255} required /></div>
          <div><Label htmlFor="published-platform">平台</Label><SelectField id="published-platform" value={platform} onValueChange={(value) => setPlatform(value as Platform)} options={platforms} /></div>
          <div className="sm:col-span-2"><Label htmlFor="published-date">发布时间</Label><div className="grid grid-cols-[minmax(0,1.3fr)_minmax(0,1fr)] gap-2"><DatePicker id="published-date" value={publishedAt.slice(0, 10)} onValueChange={(value) => setPublishedAt(`${value}T${publishedAt.slice(11, 16)}`)} /><TimePicker id="published-time" value={publishedAt.slice(11, 16)} onValueChange={(value) => setPublishedAt(`${publishedAt.slice(0, 10)}T${value}`)} /></div></div>
           <div className="flex justify-end gap-2 sm:col-span-2"><Button type="button" variant="outline" onClick={() => setContentEditorOpen(false)}>取消</Button><Button type="submit" disabled={savingContent} aria-busy={savingContent}>{savingContent ? "保存中…" : "保存发布内容"}</Button></div>
        </form>
      </Dialog>
      <Dialog open={metricEditorOpen} onOpenChange={setMetricEditorOpen} title="录入或修正累计指标" description="同一日期再次保存会更新已有记录。留空表示未提供，填写 0 表示真实零值。">
        <form onSubmit={saveMetric} className="grid gap-4 sm:grid-cols-3">
          <div className="sm:col-span-3"><Label htmlFor="metric-date">指标日期</Label><DatePicker id="metric-date" value={metric.metric_date} onValueChange={(value) => setMetric({ ...metric, metric_date: value })} className="sm:w-56" /></div>
          {metricFields.map(({ key, label }) => <div key={key}><Label htmlFor={`metric-${key}`}>{label}</Label><Input id={`metric-${key}`} type="number" min={0} value={metric[key] ?? ""} placeholder="未提供" onChange={(e) => setMetric({ ...metric, [key]: e.target.value === "" ? null : Number(e.target.value) })} /></div>)}
           <div className="flex justify-end gap-2 sm:col-span-3"><Button type="button" variant="outline" onClick={() => setMetricEditorOpen(false)}>取消</Button><Button type="submit" disabled={savingMetric} aria-busy={savingMetric}>{savingMetric ? "保存中…" : "保存指标"}</Button></div>
        </form>
      </Dialog>
    </ConsoleLayout>
  );
}
