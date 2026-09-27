import { useEffect, useState, type FormEvent } from "react";
import { Pencil, Plus, RefreshCw, Trash2 } from "lucide-react";
import { toast } from "sonner";

import { automationApi, type AutomationRun, type AutomationTask, type AutomationTaskWrite } from "@/api/automation";
import { publishingApi, type PlatformAccount, type PublishingPlatform } from "@/api/publishing";
import AutomationRunHistory from "@/components/AutomationRunHistory";
import ConsoleLayout from "@/components/ConsoleLayout";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Dialog } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { SelectField } from "@/components/ui/select";
import { TimePicker } from "@/components/ui/time-picker";

const weekdays = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"];
const browserTimezone = Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC";
const emptyTask = (): AutomationTaskWrite => ({
  task_type: "analysis_report", name: "", frequency: "weekly", weekday: 0, hour: 9, minute: 0,
  timezone: browserTimezone, payload: { account_ids: [], sync_first: false }, enabled: true,
});
const taskLabels: Record<string, string> = { analysis_report: "定时分析报告", metrics_sync: "定时同步指标" };
const timeValue = (hour: number, minute: number) => `${String(hour).padStart(2, "0")}:${String(minute).padStart(2, "0")}`;

function errorMessage(error: unknown, fallback: string): string {
  if (typeof error === "object" && error !== null && "response" in error) {
    const response = (error as { response?: { data?: { message?: string } } }).response;
    if (response?.data?.message) return response.data.message;
  }
  return fallback;
}

export default function Automation() {
  const [tasks, setTasks] = useState<AutomationTask[]>([]);
  const [accounts, setAccounts] = useState<PlatformAccount[]>([]);
  const [platforms, setPlatforms] = useState<PublishingPlatform[]>([]);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [editorOpen, setEditorOpen] = useState(false);
  const [form, setForm] = useState<AutomationTaskWrite>(emptyTask);
  const [runs, setRuns] = useState<AutomationRun[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const selected = tasks.find((task) => task.id === selectedId) ?? null;

  useEffect(() => {
    let active = true;
    Promise.all([automationApi.listTasks(), automationApi.listRuns(), publishingApi.accounts(), publishingApi.platforms()])
      .then(([savedTasks, history, savedAccounts, specs]) => {
        if (!active) return;
        setTasks(savedTasks); setSelectedId(savedTasks[0]?.id ?? null); setRuns(history);
        setAccounts(savedAccounts); setPlatforms(specs);
      })
      .catch((error) => toast.error(errorMessage(error, "自动化数据加载失败")))
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, []);

  useEffect(() => {
    if (!runs.some((run) => ["queued", "running", "waiting_sync"].includes(run.status))) return;
    const timer = window.setInterval(() => {
      automationApi.listRuns().then(setRuns).catch(() => {});
    }, 5000);
    return () => window.clearInterval(timer);
  }, [runs]);

  const startNew = () => { setEditingId(null); setForm(emptyTask()); setEditorOpen(true); };
  const editTask = (task: AutomationTask) => {
    if (!(task.task_type in taskLabels)) { toast.error("该任务类型暂不支持在此页面编辑"); return; }
    setEditingId(task.id);
    setForm({
      task_type: task.task_type as AutomationTaskWrite["task_type"], name: task.name, frequency: "weekly",
      weekday: task.weekday, hour: task.hour, minute: task.minute,
      timezone: task.timezone, payload: task.payload as AutomationTaskWrite["payload"],
      enabled: task.enabled,
    });
    setEditorOpen(true);
  };
  const save = async (event: FormEvent) => {
    event.preventDefault();
    if (form.task_type === "metrics_sync" && !form.payload.account_ids?.length) {
      toast.error("请至少选择一个账号"); return;
    }
    setSaving(true);
    try {
      const saved = editingId === null ? await automationApi.createTask(form) : await automationApi.updateTask(editingId, form);
      setTasks((items) => [saved, ...items.filter((item) => item.id !== saved.id)]);
      setSelectedId(saved.id); setEditorOpen(false);
      toast.success(editingId === null ? "自动化任务已创建" : "自动化任务已更新");
    } catch (error) { toast.error(errorMessage(error, "任务保存失败")); }
    finally { setSaving(false); }
  };
  const remove = async () => {
    if (!selected || !window.confirm("删除这个任务？已有执行记录会保留。")) return;
    try {
      await automationApi.deleteTask(selected.id);
      const remaining = tasks.filter((task) => task.id !== selected.id);
      setTasks(remaining); setSelectedId(remaining[0]?.id ?? null);
      toast.success("任务已删除，执行记录已保留");
    } catch (error) { toast.error(errorMessage(error, "任务删除失败")); }
  };
  const refreshRuns = async () => {
    const startedAt = performance.now();
    setRefreshing(true);
    try { setRuns(await automationApi.listRuns()); }
    catch (error) { toast.error(errorMessage(error, "执行记录刷新失败")); }
    finally {
      await new Promise((resolve) => window.setTimeout(resolve, Math.max(0, 650 - (performance.now() - startedAt))));
      setRefreshing(false);
    }
  };

  return <ConsoleLayout className="cp-legacy" eyebrow="AUTOMATION" title="自动化任务" description="按计划同步指标和生成分析报告" actions={<Button onClick={startNew}><Plus className="mr-1 size-4" />新建任务</Button>}>
    <div className="cp-legacy-body space-y-5">
      <div className="grid gap-5 lg:grid-cols-[280px_minmax(0,1fr)]">
        <section className="cp-panel h-fit" aria-label="任务列表">
          <div className="cp-panel-head"><div><h2>我的任务</h2><p>选择任务查看计划</p></div></div>
          {loading && <p className="text-sm text-muted-foreground">加载中…</p>}
          {!loading && tasks.length === 0 && <p className="text-sm text-muted-foreground">暂无任务。点击右上角新建。</p>}
          <div className="space-y-2">{tasks.map((task) => <Button key={task.id} type="button" variant="outline" onClick={() => setSelectedId(task.id)} className={`h-auto w-full flex-col items-start whitespace-normal p-3 text-left ${selectedId === task.id ? "border-primary bg-accent" : ""}`}>
            <span className="w-full truncate font-medium">{task.name}</span>
            <span className="mt-1 text-xs text-muted-foreground">{taskLabels[task.task_type] ?? task.task_type} · {task.enabled ? "已启用" : "已暂停"}</span>
          </Button>)}</div>
        </section>
        <section className="cp-panel min-h-[300px]" aria-label="任务详情">
          {selected ? <>
            <div className="cp-panel-head"><div><span className="text-xs text-muted-foreground">{taskLabels[selected.task_type] ?? selected.task_type} · {selected.enabled ? "已启用" : "已暂停"}</span><h2 className="mt-2">{selected.name}</h2></div><div className="flex gap-2"><Button variant="outline" size="sm" onClick={() => editTask(selected)}><Pencil className="mr-1 size-4" />编辑</Button><Button variant="ghost" size="sm" onClick={remove} aria-label="删除任务"><Trash2 className="size-4" /></Button></div></div>
            <div className="grid gap-4 sm:grid-cols-2">
              <div className="rounded-md border border-border bg-muted p-4"><div className="text-xs text-muted-foreground">执行时间</div><strong className="mt-2 block text-lg">{weekdays[selected.weekday]} {timeValue(selected.hour, selected.minute)}</strong><small>{selected.timezone}</small></div>
              <div className="rounded-md border border-border bg-muted p-4"><div className="text-xs text-muted-foreground">任务范围</div><strong className="mt-2 block text-lg">{Array.isArray(selected.payload.account_ids) && selected.payload.account_ids.length ? `${selected.payload.account_ids.length} 个指定账号` : "全部已收录作品"}</strong><small>{selected.payload.sync_first ? "先同步最新指标，再分析" : selected.task_type === "metrics_sync" ? "同步作品及指标，不调用 AI" : "使用已保存的指标分析"}</small></div>
            </div>
            <p className="mt-5 text-sm text-muted-foreground">下次执行：{selected.next_run_at ? new Date(selected.next_run_at).toLocaleString("zh-CN", { timeZone: selected.timezone }) : "任务已暂停"}</p>
          </> : <div className="flex min-h-[260px] items-center justify-center text-sm text-muted-foreground">选择任务查看计划，或新建任务</div>}
        </section>
      </div>
      <section className="cp-panel">
        <div className="cp-panel-head"><div><h2>执行记录</h2><p>查看同步、报告结果和失败原因</p></div><Button size="sm" variant="outline" onClick={refreshRuns} disabled={refreshing} aria-busy={refreshing}><RefreshCw className={`mr-1 size-4 ${refreshing ? "cp-spinning" : ""}`} />{refreshing ? "刷新中…" : "刷新"}</Button></div>
        <AutomationRunHistory runs={runs} />
      </section>
    </div>
    <Dialog open={editorOpen} onOpenChange={setEditorOpen} title={editingId === null ? "新建任务" : "编辑任务"} description="设置每周执行时间。同步需要本机发布服务保持运行。" className="max-w-lg">
      <form onSubmit={save} className="grid gap-4 sm:grid-cols-2">
        <div className="sm:col-span-2"><Label htmlFor="automation-name">任务名称</Label><Input id="automation-name" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} placeholder="例如：小红书周报" maxLength={100} required /></div>
        <div className="sm:col-span-2"><Label htmlFor="task-type">任务类型</Label><SelectField id="task-type" disabled={editingId !== null} value={form.task_type} onValueChange={(value) => setForm({ ...form, task_type: value as AutomationTaskWrite["task_type"], payload: value === "metrics_sync" ? { account_ids: [] } : { account_ids: [], sync_first: false } })} options={Object.entries(taskLabels).map(([value, label]) => ({ value, label }))} /></div>
        <div><Label htmlFor="task-weekday">每周</Label><SelectField id="task-weekday" value={String(form.weekday)} onValueChange={(value) => setForm({ ...form, weekday: Number(value) })} options={weekdays.map((day, index) => ({ value: String(index), label: day }))} /></div>
        <div><Label htmlFor="task-time-hour">执行时间</Label><TimePicker id="task-time" value={timeValue(form.hour, form.minute)} onValueChange={(value) => { const [hour, minute] = value.split(":").map(Number); setForm({ ...form, hour, minute }); }} /></div>
        {<div className="sm:col-span-2 space-y-2"><Label>账号范围</Label><p className="text-xs text-muted-foreground">{form.task_type === "metrics_sync" ? "至少选择一个支持同步的账号" : "不选则分析全部已收录作品，包括人工登记的作品；先同步时会同步全部已绑定账号"}</p>
          <div className="max-h-40 space-y-2 overflow-y-auto rounded-md border p-3">{accounts.map((account) => {
            const unavailable = account.status === "expired" || !platforms.some((spec) => spec.key === account.platform && spec.metrics_sync_supported);
            return <label key={account.id} className="flex items-center gap-2 text-sm"><Checkbox checked={form.payload.account_ids?.includes(account.id) ?? false} disabled={unavailable && (form.task_type === "metrics_sync" || !!form.payload.sync_first)} onCheckedChange={(checked) => setForm({ ...form, payload: { ...form.payload, account_ids: checked ? [...(form.payload.account_ids ?? []), account.id] : (form.payload.account_ids ?? []).filter((id) => id !== account.id) } })} />{account.remark || account.account_name} · {platforms.find((spec) => spec.key === account.platform)?.name ?? account.platform}{unavailable && "（暂不可同步）"}</label>;
          })}{accounts.length === 0 && <p className="text-sm text-muted-foreground">暂无绑定账号</p>}</div>
          {(form.payload.account_ids ?? []).filter((id) => !accounts.some((account) => account.id === id)).map((id) => <p key={id} className="text-sm text-destructive">账号 {id} 已不可用 <Button type="button" variant="ghost" size="sm" onClick={() => setForm({ ...form, payload: { ...form.payload, account_ids: form.payload.account_ids?.filter((item) => item !== id) } })}>移除</Button></p>)}
        </div>}
        {form.task_type === "analysis_report" && <div className="flex items-center gap-2 sm:col-span-2"><Checkbox id="sync-first" checked={form.payload.sync_first ?? false} onCheckedChange={(checked) => setForm({ ...form, payload: { ...form.payload, sync_first: checked === true } })} /><Label htmlFor="sync-first">先同步最新指标再分析（同步失败则停止）</Label></div>}
        <div><Label htmlFor="task-timezone">时区</Label><Input id="task-timezone" value={form.timezone} onChange={(e) => setForm({ ...form, timezone: e.target.value })} placeholder="例如 Asia/Shanghai" required /></div>
        <div className="flex items-center gap-2 sm:col-span-2"><Checkbox id="task-enabled" checked={form.enabled} onCheckedChange={(checked) => setForm({ ...form, enabled: checked === true })} /><Label htmlFor="task-enabled">启用任务</Label></div>
        <div className="flex justify-end gap-2 sm:col-span-2"><Button type="button" variant="outline" onClick={() => setEditorOpen(false)}>取消</Button><Button type="submit" disabled={saving} aria-busy={saving}>{saving ? "保存中…" : "保存任务"}</Button></div>
      </form>
    </Dialog>
  </ConsoleLayout>;
}
