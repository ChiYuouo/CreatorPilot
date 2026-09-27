import { useEffect, useRef, useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import { ArrowRight, CalendarClock, Check, FileVideo, RefreshCw, Search, Send, UploadCloud, Users } from "lucide-react";
import { SiBilibili, SiKuaishou, SiTiktok, SiWechat, SiXiaohongshu } from "react-icons/si";
import { toast } from "sonner";

import { publishingApi, type MediaAsset, type PlatformAccount, type PublishJob, type PublishingPlatform } from "@/api/publishing";
import ConsoleLayout from "@/components/ConsoleLayout";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { DatePicker } from "@/components/ui/date-picker";
import { Dialog } from "@/components/ui/dialog";
import { Drawer } from "@/components/ui/drawer";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { TimePicker } from "@/components/ui/time-picker";
import { accountLabel, platformName } from "@/lib/platformAccount";

const icons = { douyin: SiTiktok, kuaishou: SiKuaishou, xiaohongshu: SiXiaohongshu, tencent: SiWechat, bilibili: SiBilibili };

function localDateTime(value: Date) {
  const part = (number: number) => String(number).padStart(2, "0");
  return `${value.getFullYear()}-${part(value.getMonth() + 1)}-${part(value.getDate())}T${part(value.getHours())}:${part(value.getMinutes())}`;
}

const statusText: Record<string, string> = {
  queued: "排队中", running: "上传中", cancel_requested: "正在停止",
  canceled: "已停止", submitted: "已提交待核实", failed: "失败", needs_review: "结果待核实",
  confirmed: "已确认发布", not_published: "确认未发布",
  valid: "已连接", expired: "已失效", unchecked: "待检查",
};

function message(error: unknown, fallback: string) {
  if (typeof error === "object" && error !== null && "response" in error) {
    const response = (error as { response?: { data?: { message?: string } } }).response;
    if (response?.data?.message) return response.data.message;
  }
  return fallback;
}

function runHint(job: PublishJob, now: number) {
  const seconds = Math.max(0, Math.floor((now - new Date(job.created_at).getTime()) / 1000));
  const elapsed = seconds >= 60 ? `${Math.floor(seconds / 60)} 分 ${seconds % 60} 秒` : `${seconds} 秒`;
  if (!job.auto_stop_at) return `已运行 ${elapsed}，超时后自动停止`;
  const left = Math.floor((new Date(job.auto_stop_at).getTime() - now) / 1000);
  if (left <= 0) return `已运行 ${elapsed}，正在自动停止`;
  return `已运行 ${elapsed}，约 ${Math.max(1, Math.ceil(left / 60))} 分钟后自动停止`;
}

function ImageThumbnail({ id }: { id: number }) {
  const [url, setUrl] = useState("");
  useEffect(() => {
    const controller = new AbortController();
    let objectUrl = "";
    void publishingApi.imgPreview(id, controller.signal).then((blob) => {
      if (!controller.signal.aborted) { objectUrl = URL.createObjectURL(blob); setUrl(objectUrl); }
    }).catch(() => {});
    return () => { controller.abort(); if (objectUrl) URL.revokeObjectURL(objectUrl); };
  }, [id]);
  return url ? <img src={url} alt="图片缩略图" className="size-12 shrink-0 rounded object-cover" /> : <span className="size-12 shrink-0 rounded bg-muted" />;
}

export default function Publishing() {
  const [accounts, setAccounts] = useState<PlatformAccount[]>([]);
  const [assets, setAssets] = useState<MediaAsset[]>([]);
  const [platforms, setPlatforms] = useState<PublishingPlatform[]>([]);
  const [jobs, setJobs] = useState<PublishJob[]>([]);
  const [selectedPlatforms, setSelectedPlatforms] = useState<string[]>([]);
  const [accountIds, setAccountIds] = useState<number[]>([]);
  const [accountOpen, setAccountOpen] = useState(false);
  const [assetOpen, setAssetOpen] = useState(false);
  const [accountSearch, setAccountSearch] = useState("");
  const [assetSearch, setAssetSearch] = useState("");
  const [assetId, setAssetId] = useState("");
  const [mediaType, setMediaType] = useState<"video" | "image">("video");
  const [imageIds, setImageIds] = useState<number[]>([]);
  const [mode, setMode] = useState<"now" | "scheduled">("now");
  const [schedule, setSchedule] = useState(() => localDateTime(new Date(Date.now() + 4 * 3600_000)));
  const [bilibiliTid, setBilibiliTid] = useState("");
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [tagsText, setTagsText] = useState("");
  const [busy, setBusy] = useState("");
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState("");
  const [now, setNow] = useState(() => Date.now());
  const refreshInFlight = useRef(false);

  const refresh = async (manual = false) => {
    if (refreshInFlight.current) return;
    refreshInFlight.current = true;
    const startedAt = performance.now();
    if (manual) setRefreshing(true);
    try {
      const [nextAccounts, nextAssets, nextJobs, nextPlatforms] = await Promise.all([
        publishingApi.accounts(), publishingApi.assets(), publishingApi.jobs(), publishingApi.platforms(),
      ]);
      setAccounts(nextAccounts);
      setAssets(nextAssets);
      setPlatforms(nextPlatforms);
      setJobs(nextJobs);
      setError("");
    } catch (cause) { setError(message(cause, "发布中心加载失败")); }
    finally {
      refreshInFlight.current = false;
      if (manual) {
        await new Promise((resolve) => window.setTimeout(resolve, Math.max(0, 650 - (performance.now() - startedAt))));
        setRefreshing(false);
      }
    }
  };

  useEffect(() => {
    void refresh();
    const poll = window.setInterval(() => {
      if (!document.hidden) void refresh();
    }, 7000);
    return () => window.clearInterval(poll);
  }, []);

  useEffect(() => {
    if (!jobs.some((job) => job.status === "queued" || job.status === "running" || (job.scheduled_at && job.status === "submitted"))) return;
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, [jobs]);

  const primaryAssetId = mediaType === "image" ? String(imageIds[0] ?? "") : assetId;
  const titleLimit = (item: PublishingPlatform) => mediaType === "image" ? item.image_title_max_length : item.title_max_length;
  const imageLimit = Math.min(9, ...platforms.filter((item) => selectedPlatforms.includes(item.key) && item.image_publish_supported).map((item) => item.image_max_count));
  const selectedAsset = assets.find((item) => String(item.id) === primaryAssetId);
  const selectedAccounts = accounts.filter((item) => accountIds.includes(item.id));
  const selectedSpecs = platforms.filter((item) => selectedPlatforms.includes(item.key));
  const tags = tagsText.split(/[,，\n]/).map((tag) => tag.trim().replace(/^#+/, "")).filter(Boolean);
  const invalidTitle = !title.trim() || title.includes("\n") || selectedSpecs.some((item) => title.trim().length > titleLimit(item));
  const scheduleDate = mode === "scheduled" ? new Date(schedule) : null;
  const leadHours = 2 + accountIds.length / 6;
  const invalidSchedule = mode === "scheduled" && (!scheduleDate || Number.isNaN(scheduleDate.getTime()) || scheduleDate.getTime() <= Date.now() + leadHours * 3600_000);

  const togglePlatform = (key: string) => {
    if (selectedPlatforms.includes(key)) {
      setSelectedPlatforms((items) => items.filter((item) => item !== key));
      setAccountIds((items) => items.filter((id) => accounts.find((account) => account.id === id)?.platform !== key));
    } else setSelectedPlatforms((items) => [...items, key]);
  };

  const publish = async (event: FormEvent) => {
    event.preventDefault();
    if (!selectedPlatforms.length) { toast.error("请先选择发布平台"); return; }
    if (!accountIds.length) { toast.error("请先选择发布账号"); return; }
    if (!primaryAssetId) { toast.error("请先选择素材"); return; }
    if (mediaType === "image" && (imageIds.length > imageLimit || selectedSpecs.some((item) => !item.image_publish_supported))) { toast.error("请检查图片数量及平台图文支持情况"); return; }
    if (mediaType === "image" && selectedSpecs.some((item) => (item.key === "kuaishou" ? title.trim().length + (description.trim() ? 1 + description.trim().length : 0) : description.trim().length) > item.image_description_max_length)) { toast.error("图文正文超过平台限制"); return; }
    if (selectedAccounts.length !== accountIds.length || selectedAccounts.some((account) => account.status !== "valid")) { toast.error("所选账号已失效，请重新选择"); return; }
    if (invalidTitle) { toast.error("请检查作品标题及各平台的长度限制"); return; }
    if (selectedSpecs.some((item) => item.description_required && !description.trim())) { toast.error("所选平台要求填写作品正文"); return; }
    if (selectedSpecs.some((item) => tags.length > item.tags_max_count)) { toast.error("标签数量超过所选平台的限制"); return; }
    if (selectedSpecs.some((item) => item.category_required && !(Number(bilibiliTid) > 0))) { toast.error("请填写 B 站分区 ID"); return; }
    if (invalidSchedule) { toast.error(`预约时间至少需要提前 ${leadHours.toFixed(1)} 小时`); return; }
    const alreadyPublished = jobs.some((job) => accountIds.includes(job.account_id) && job.status === "confirmed" && (mediaType === "image" ? job.image_asset_ids.length === imageIds.length && imageIds.every((id) => job.image_asset_ids.includes(id)) : !job.image_asset_ids.length && job.asset_id === Number(primaryAssetId)));
    const prompt = alreadyPublished
      ? `所选账号中有账号曾发布同一素材。再次提交可能产生重复作品，确定继续吗？`
      : `将作品「${title.trim()}」提交到 ${accountIds.length} 个账号${mode === "scheduled" ? `，由平台预约 ${schedule.replace("T", " ")} 发布` : "并立即发布"}？`;
    if (!window.confirm(prompt)) return;
    setBusy("publish");
    try {
      const result = await publishingApi.publishPlan({
        account_ids: accountIds, asset_id: Number(primaryAssetId), image_asset_ids: mediaType === "image" ? imageIds : [], title: title.trim(),
        description: description.trim(), tags,
        scheduled_at: mode === "scheduled" ? scheduleDate!.toISOString() : null,
        platform_options: selectedPlatforms.includes("bilibili") ? { bilibili: { tid: Number(bilibiliTid) } } : {},
      });
      setJobs((items) => [...result.jobs, ...items]);
      toast.success(`${result.jobs.length} 个账号的${mode === "scheduled" ? "预约上传" : "发布"}任务已提交`);
    } catch (cause) { toast.error(message(cause, "发布任务提交失败")); }
    finally { setBusy(""); }
  };

  const cancelJob = async (job: PublishJob) => {
    if (["running", "cancel_requested"].includes(job.status) && !window.confirm("将立即停止本机上传进程。平台可能已收到部分提交，停止后请到对应平台后台核实结果。确定继续吗？")) return;
    setBusy(`cancel-${job.id}`);
    try {
      const updated = await publishingApi.cancelJob(job.id);
      setJobs((items) => items.map((item) => item.id === job.id ? updated : item));
      toast.success("任务已取消，可以重新发布");
    } catch (cause) { toast.error(message(cause, "取消任务失败")); }
    finally { setBusy(""); }
  };

  const confirmJob = async (job: PublishJob, result: "published" | "not_published") => {
    const prompt = result === "published"
      ? "请先到平台后台核对：已经看到这条作品了吗？确认后任务将标记为发布完成。"
      : "请先到平台后台核对：确定没有这条作品或待发布的预约作品，或已撤销预约吗？确认未发布后可以删除记录或重试。此操作不会撤销平台预约。";
    if (!window.confirm(prompt)) return;
    setBusy(`confirm-${job.id}`);
    try {
      const updated = await publishingApi.confirmJob(job.id, result);
      setJobs((items) => items.map((item) => item.id === job.id ? updated : item));
      toast.success(result === "published" ? "已记录发布成功" : "已记录未发布，可以删除或重试");
    } catch (cause) { toast.error(message(cause, "确认结果失败")); }
    finally { setBusy(""); }
  };

  const retryJob = (job: PublishJob) => {
    setSelectedPlatforms([job.platform]);
    setAccountIds([job.account_id]);
    setAssetId(String(job.asset_id));
    setImageIds(job.image_asset_ids);
    setMediaType(job.image_asset_ids.length ? "image" : "video");
    setMode(job.scheduled_at ? "scheduled" : "now");
    if (job.scheduled_at) setSchedule(localDateTime(new Date(job.scheduled_at)));
    setTitle(job.title);
    setDescription(job.description);
    setTagsText(job.tags.join(", "));
    document.getElementById("cp-publish-title")?.scrollIntoView({ behavior: "smooth", block: "center" });
    toast.info(job.status === "confirmed" ? "已带入上次的信息；再次提交会产生另一条作品" : "已带入上次的发布信息，请检查后重新提交");
  };

  const deleteJob = async (job: PublishJob) => {
    if (!window.confirm("确定删除这条任务记录吗？")) return;
    setBusy(`delete-${job.id}`);
    try {
      await publishingApi.deleteJob(job.id);
      setJobs((items) => items.filter((item) => item.id !== job.id));
      toast.success("任务记录已删除");
    } catch (cause) { toast.error(message(cause, "删除任务失败")); }
    finally { setBusy(""); }
  };

  const jobAccountLabel = (job: PublishJob) => {
    const account = accounts.find((item) => item.id === job.account_id);
    return account ? accountLabel(account) : `${platformName(job.platform)} #${job.account_id}`;
  };

  return <ConsoleLayout eyebrow="DISTRIBUTION / PUBLISH" title="发布中心" description="选择账号和素材，填写平台作品信息后提交" actions={<Button variant="outline" onClick={() => void refresh(true)} disabled={refreshing} aria-busy={refreshing}><RefreshCw size={14} className={refreshing ? "cp-spinning" : ""} />{refreshing ? "刷新中…" : "刷新状态"}</Button>}>
    {error && <div className="cp-error">{error}</div>}
    <div className="cp-step"><Link to="/accounts">1 绑定账号</Link><ArrowRight size={13} /><Link to="/media">2 上传素材</Link><ArrowRight size={13} /><span>3 确认发布</span></div>
    <section className="cp-panel">
      <div className="cp-panel-head"><div><h2>发布工作台</h2><p>选择平台、账号和素材，再选择立即发布或向平台预约发布</p></div><Send size={18} color="#737373" /></div>
      <form onSubmit={publish}>
        <div className="cp-field"><label>素材类型</label><div className="flex gap-2">{(["video", "image"] as const).map((type) => <Button key={type} type="button" variant={mediaType === type ? "default" : "outline"} onClick={() => { setMediaType(type); if (type === "image") { const supported = platforms.filter((p) => p.image_publish_supported).map((p) => p.key); setSelectedPlatforms((items) => items.filter((key) => supported.includes(key))); setAccountIds((items) => items.filter((id) => supported.includes(accounts.find((a) => a.id === id)?.platform ?? ""))); } }}>{type === "video" ? "视频" : "图文"}</Button>)}</div>{mediaType === "image" && <small>支持抖音、小红书、快手；最多 {imageLimit} 张图片，按下方顺序发布。</small>}</div>
        <div className="cp-field"><label>发布平台</label>
          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-5">{platforms.map((platform) => {
            const Icon = icons[platform.key as keyof typeof icons] ?? SiTiktok;
            const checked = selectedPlatforms.includes(platform.key);
            const unsupported = mediaType === "image" && !platform.image_publish_supported;
            return <button key={platform.key} type="button" disabled={unsupported} aria-pressed={checked} onClick={() => togglePlatform(platform.key)} className={`flex items-center gap-3 rounded-lg border p-3 text-left transition-colors ${checked ? "border-primary bg-primary/5" : "border-border hover:bg-accent"}`}>
              <Icon className="size-6 shrink-0" /><span className="min-w-0 flex-1"><strong className="block text-sm">{platform.name}</strong><small className="text-muted-foreground">{unsupported ? "暂不支持图文" : `已选 ${selectedAccounts.filter((account) => account.platform === platform.key).length} 个账号`}</small></span><span className={`flex size-4 items-center justify-center rounded border ${checked ? "border-primary bg-primary text-primary-foreground" : "border-border"}`}>{checked && <Check className="size-3" />}</span>
            </button>;
          })}</div>
        </div>
        <div className="grid gap-4 sm:grid-cols-2">
          <div className="cp-field"><label>发布账号</label><Button type="button" variant="outline" className="w-full justify-start" onClick={() => setAccountOpen(true)} disabled={!selectedPlatforms.length}><Users size={15} />{accountIds.length ? `已选择 ${accountIds.length} 个账号` : "选择账号"}</Button><small>可在右侧按平台多选账号。</small></div>
          <div className="cp-field"><label>{mediaType === "image" ? "图片素材" : "视频素材"}</label><Button type="button" variant="outline" className="w-full justify-start overflow-hidden" onClick={() => setAssetOpen(true)}><FileVideo size={15} /><span className="truncate">{mediaType === "image" ? `已选择 ${imageIds.length} 张图片` : selectedAsset?.filename ?? "选择视频素材"}</span></Button><small>可搜索素材；图片按选择顺序排列。</small></div>
        </div>
        {mediaType === "image" && <div className="mb-4 space-y-2">{imageIds.map((id, index) => <div key={id} className="flex items-center gap-2 rounded-md border p-2"><ImageThumbnail id={id} /><span className="min-w-0 flex-1 truncate text-sm">{index + 1}. {assets.find((a) => a.id === id)?.filename ?? `素材 #${id}`}</span><Button type="button" variant="outline" size="sm" disabled={index === 0} onClick={() => setImageIds((items) => { const next = [...items]; [next[index - 1], next[index]] = [next[index], next[index - 1]]; return next; })}>上移</Button><Button type="button" variant="outline" size="sm" disabled={index === imageIds.length - 1} onClick={() => setImageIds((items) => { const next = [...items]; [next[index + 1], next[index]] = [next[index], next[index + 1]]; return next; })}>下移</Button><Button type="button" variant="ghost" size="sm" onClick={() => setImageIds((items) => items.filter((item) => item !== id))}>移除</Button></div>)}</div>}
        <div className="cp-field"><label htmlFor="cp-publish-title">作品标题</label><Input id="cp-publish-title" value={title} onChange={(event) => setTitle(event.target.value)} placeholder="填写平台上显示的作品标题" /><small>{selectedSpecs.length ? `所选平台最短标题上限 ${Math.min(...selectedSpecs.map(titleLimit))} 字` : "请先选择平台"}。</small></div>
        <div className="cp-field"><label htmlFor="cp-publish-description">作品正文{selectedSpecs.some((item) => item.description_required) ? "" : "（可选）"}</label><Textarea id="cp-publish-description" value={description} onChange={(event) => setDescription(event.target.value)} rows={3} placeholder="填写发布页正文" />{mediaType === "image" && <small>图文正文最多 {Math.min(1000, ...selectedSpecs.map((item) => item.image_description_max_length))} 字；快手将标题放在正文首行，合并后计入长度。</small>}</div>
        <div className="cp-field"><label htmlFor="cp-publish-tags">话题标签（可选）</label><Input id="cp-publish-tags" value={tagsText} onChange={(event) => setTagsText(event.target.value)} placeholder="例如：创作,教程" /><small>用逗号分隔；按所选平台中最严格的数量限制校验。</small></div>
        {selectedPlatforms.includes("bilibili") && <div className="cp-field"><label htmlFor="cp-bilibili-tid">B 站分区 ID</label><Input id="cp-bilibili-tid" type="number" min="1" value={bilibiliTid} onChange={(event) => setBilibiliTid(event.target.value)} placeholder="填写 B 站视频分区 ID" /><small>请按 B 站当前分区填写有效 ID。</small></div>}
        <div className="cp-field"><label>发布方式</label><div className="flex flex-wrap gap-2"><Button type="button" variant={mode === "now" ? "default" : "outline"} aria-pressed={mode === "now"} onClick={() => setMode("now")}>现在发布</Button><Button type="button" variant={mode === "scheduled" ? "default" : "outline"} aria-pressed={mode === "scheduled"} onClick={() => { setMode("scheduled"); requestAnimationFrame(() => document.getElementById("cp-schedule-date")?.scrollIntoView({ behavior: "smooth", block: "center" })); }}><CalendarClock size={15} />指定时间</Button></div></div>
        {mode === "scheduled" && <div className="cp-field"><label>平台预约时间</label><div className="grid gap-2 sm:grid-cols-2"><DatePicker id="cp-schedule-date" value={schedule.slice(0, 10)} onValueChange={(value) => setSchedule(`${value}T${schedule.slice(11)}`)} /><TimePicker id="cp-schedule-time" value={schedule.slice(11, 16)} onValueChange={(value) => setSchedule(`${schedule.slice(0, 10)}T${value}`)} /></div><small>本地时间（{Intl.DateTimeFormat().resolvedOptions().timeZone}）。黑盒要求至少提前 2 小时；{accountIds.length} 个账号预计需提前 {leadHours.toFixed(1)} 小时。点击下方按钮后会立刻上传素材并向平台提交预约，无需等到目标时间才能检查预约是否成功。</small>{invalidSchedule && <small className="text-destructive">请选择至少 {leadHours.toFixed(1)} 小时后的时间。</small>}</div>}
        <div className="cp-row"><Button type="submit" disabled={busy !== "" || (mediaType === "image" && imageIds.length > imageLimit)} aria-busy={busy === "publish"}><UploadCloud size={15} />{busy === "publish" ? "提交中…" : mode === "scheduled" ? "提交平台预约" : "立即发布"}</Button><span className="cp-muted">将为 {accountIds.length} 个账号创建独立任务。提交后可在下方查看上传与预约结果。</span></div>
      </form>
    </section>
    {jobs.some((job) => job.scheduled_at && ["submitted", "needs_review"].includes(job.status)) && <div className="cp-hint">预约时间未到也可以确认未发布并删除记录，请先核实平台没有该作品或预约已撤销。站内确认不会撤销平台预约；确认已发布仍需等到预约时间后。</div>}
    <section className="cp-panel">
      <div className="cp-panel-head"><div><h2>任务记录</h2><p>自动刷新最近的发布任务</p></div><span className="cp-muted">{jobs.length} 条记录</span></div>
      {jobs.length ? <div className="overflow-x-auto"><table className="cp-table"><thead><tr><th>标题</th><th>账号</th><th>创建时间</th><th>状态</th><th className="min-w-48 whitespace-nowrap">操作</th></tr></thead><tbody>{jobs.map((job) => <tr key={job.id}><td><div>{job.title}</div>{job.plan_id && <small className="block text-muted-foreground">批次 #{job.plan_id}</small>}{job.error_message && <small className="text-destructive">{job.error_message}</small>}</td><td>{jobAccountLabel(job)}</td><td>{new Date(job.created_at).toLocaleString("zh-CN")}</td><td><span className={`cp-badge ${job.status}`}>{job.scheduled_at && job.status === "submitted" ? "预约已提交待核实" : statusText[job.status]}</span>{job.scheduled_at && <small className="mt-1 block text-muted-foreground">预约 {new Date(job.scheduled_at).toLocaleString("zh-CN")}</small>}{["queued", "running"].includes(job.status) && <small className="mt-1 block text-muted-foreground">{runHint(job, now)}</small>}{job.confirmed_at && <small className="mt-1 block text-muted-foreground">{new Date(job.confirmed_at).toLocaleString("zh-CN")} 人工确认</small>}</td><td><div className="flex flex-wrap gap-2">{["queued", "running", "cancel_requested"].includes(job.status) && <Button type="button" variant="outline" size="sm" disabled={busy !== ""} onClick={() => void cancelJob(job)}>取消任务</Button>}{["submitted", "needs_review"].includes(job.status) && <><Button type="button" variant="outline" size="sm" disabled={busy !== "" || (!!job.scheduled_at && new Date(job.scheduled_at).getTime() > now)} onClick={() => void confirmJob(job, "published")}>确认已发布</Button><Button type="button" variant="outline" size="sm" disabled={busy !== ""} onClick={() => void confirmJob(job, "not_published")}>确认未发布</Button></>}{["not_published", "confirmed"].includes(job.status) && <Button type="button" variant="outline" size="sm" disabled={busy !== ""} onClick={() => retryJob(job)}>{job.status === "confirmed" ? "再次发布" : "重试发布"}</Button>}{!["queued", "running", "cancel_requested", "submitted", "needs_review"].includes(job.status) && <Button type="button" variant="outline" size="sm" disabled={busy !== ""} onClick={() => void deleteJob(job)}>删除</Button>}</div></td></tr>)}</tbody></table></div> : <div className="cp-empty"><Send size={27} />还没有发布任务</div>}
    </section>
    <Drawer open={accountOpen} onOpenChange={setAccountOpen} title="选择发布账号">
      <div className="space-y-4"><div className="relative"><Search className="absolute left-3 top-3 size-4 text-muted-foreground" /><Input aria-label="搜索账号" className="pl-9" placeholder="搜索账号或备注" value={accountSearch} onChange={(event) => setAccountSearch(event.target.value)} /></div>
        {selectedSpecs.map((platform) => <section key={platform.key} className="space-y-2"><h3 className="text-sm font-semibold">{platform.name}</h3>{accounts.filter((account) => account.platform === platform.key && accountLabel(account).toLowerCase().includes(accountSearch.toLowerCase())).map((account) => <label key={account.id} className={`flex items-center gap-3 rounded-md border border-border p-3 ${account.status === "valid" ? "cursor-pointer hover:bg-accent" : "opacity-60"}`}><Checkbox checked={accountIds.includes(account.id)} disabled={account.status !== "valid"} onCheckedChange={(checked) => setAccountIds((items) => checked ? [...items, account.id] : items.filter((id) => id !== account.id))} /><span className="min-w-0 flex-1"><span className="block truncate text-sm font-medium">{accountLabel(account)}</span><small className="text-muted-foreground">编号 #{account.id} · {statusText[account.status]}</small></span></label>)}{!accounts.some((account) => account.platform === platform.key) && <p className="text-sm text-muted-foreground">暂无已绑定账号</p>}</section>)}
        <div className="flex items-center justify-between border-t border-border pt-4"><Link to="/accounts" className="cp-panel-link">管理账号</Link><Button type="button" onClick={() => setAccountOpen(false)}>完成（{accountIds.length}）</Button></div>
      </div>
    </Drawer>
    <Dialog open={assetOpen} onOpenChange={setAssetOpen} title={mediaType === "image" ? "选择图片素材" : "选择视频素材"} description={mediaType === "image" ? `多选图片，最多 ${imageLimit} 张；可在工作台调整顺序。` : "选择一个视频，可按文件名搜索。"}>
      <div className="space-y-4"><Input aria-label="搜索素材" placeholder="搜索文件名" value={assetSearch} onChange={(event) => setAssetSearch(event.target.value)} /><div className="max-h-[55vh] space-y-2 overflow-y-auto">{assets.filter((asset) => asset.media_type === mediaType && asset.filename.toLowerCase().includes(assetSearch.toLowerCase())).map((asset) => {
        const checked = mediaType === "image" ? imageIds.includes(asset.id) : assetId === String(asset.id);
        return <button key={asset.id} type="button" aria-pressed={checked} onClick={() => { if (mediaType === "video") { setAssetId(String(asset.id)); setAssetOpen(false); } else if (checked) setImageIds((items) => items.filter((id) => id !== asset.id)); else if (imageIds.length < imageLimit) setImageIds((items) => [...items, asset.id]); else toast.error(`最多选择 ${imageLimit} 张图片`); }} className={`flex w-full items-center gap-3 rounded-md border p-3 text-left hover:bg-accent ${checked ? "border-primary bg-primary/5" : "border-border"}`}>{mediaType === "image" && <ImageThumbnail id={asset.id} />}<span className="min-w-0 flex-1"><strong className="block truncate text-sm">{asset.filename}</strong><small className="text-muted-foreground">{(asset.size_bytes / 1024 / 1024).toFixed(1)} MB · {mediaType === "image" ? "图片" : "视频"}</small></span>{checked && <Check className="size-4 text-primary" />}</button>;
      })}</div>{!assets.some((asset) => asset.media_type === mediaType) && <p className="text-sm text-muted-foreground">暂无素材。<Link to="/media" className="cp-panel-link">去上传素材</Link></p>}{mediaType === "image" && <Button type="button" onClick={() => setAssetOpen(false)}>完成（{imageIds.length} 张）</Button>}</div>
    </Dialog>
  </ConsoleLayout>;
}
