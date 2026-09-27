import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { Activity, ArrowUpRight, CircleAlert, Clock3, FileVideo, RefreshCw, Sparkles, UploadCloud, Users } from "lucide-react";

import { publishingApi, type PlatformAccount, type PublishJob, type PublishingOverview } from "@/api/publishing";
import ConsoleLayout from "@/components/ConsoleLayout";
import { Button } from "@/components/ui/button";
import { accountLabel, platformName } from "@/lib/platformAccount";

const statusText: Record<string, string> = { queued: "排队中", running: "上传中", submitted: "已提交待核实", failed: "失败", needs_review: "结果待核实", confirmed: "已确认发布", not_published: "确认未发布", canceled: "已停止", cancel_requested: "正在停止", valid: "已连接", expired: "已失效", unchecked: "待检查" };
const time = (raw: string) => new Date(raw).toLocaleString("zh-CN", { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" });

export default function Dashboard() {
  const [overview, setOverview] = useState<PublishingOverview | null>(null);
  const [accounts, setAccounts] = useState<PlatformAccount[]>([]);
  const [jobs, setJobs] = useState<PublishJob[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState("");
  const [now, setNow] = useState(new Date());

  const refresh = async (manual = false) => {
    const startedAt = performance.now();
    if (manual) setRefreshing(true);
    try {
      const [summary, savedAccounts, savedJobs] = await Promise.all([publishingApi.overview(), publishingApi.accounts(), publishingApi.jobs()]);
      setOverview(summary); setAccounts(savedAccounts); setJobs(savedJobs); setError("");
    } catch { setError("仪表盘数据加载失败，请检查后端服务和数据库迁移。"); }
    finally {
      setLoading(false);
      if (manual) {
        // 请求很快完成时也留出足够时间让用户看见刷新反馈。
        await new Promise((resolve) => window.setTimeout(resolve, Math.max(0, 650 - (performance.now() - startedAt))));
        setRefreshing(false);
      }
    }
  };

  useEffect(() => {
    void refresh();
    const clock = window.setInterval(() => setNow(new Date()), 1000);
    const poll = window.setInterval(() => void refresh(), 15000);
    return () => { window.clearInterval(clock); window.clearInterval(poll); };
  }, []);

  const stats = [
    { label: "平台账号", value: overview?.account_count, note: "已绑定的发布账号", icon: Users },
    { label: "素材库", value: overview?.asset_count, note: "图片与视频素材", icon: FileVideo },
    { label: "执行中的任务", value: overview?.pending_count, note: "排队或上传中", icon: Activity },
    { label: "需要处理", value: overview?.failed_count, note: "待核实或可重试的任务", icon: CircleAlert },
  ];

  return <ConsoleLayout eyebrow="OVERVIEW / WORKSPACE" title="运营仪表盘" description="账号、素材与发布任务的实时概览" actions={<Button variant="outline" onClick={() => void refresh(true)} disabled={refreshing} aria-busy={refreshing}><RefreshCw size={14} className={refreshing ? "cp-spinning" : ""} />{refreshing ? "刷新中…" : "刷新数据"}</Button>}>
    {error && <div className="cp-error">{error}</div>}
    <div className="cp-stats">{stats.map((stat) => <div className="cp-stat" key={stat.label}><div className="cp-stat-top"><span>{stat.label}</span><span className="cp-stat-icon"><stat.icon size={16} /></span></div><strong>{loading ? "…" : stat.value ?? "—"}</strong><small>{stat.note}</small></div>)}</div>
    <div className="cp-grid">
      <div>
        <section className="cp-panel"><div className="cp-panel-head"><div><h2>发布任务</h2><p>最近的上传状态与执行结果</p></div><Link className="cp-panel-link" to="/publishing">查看全部 ↗</Link></div>
          {jobs.length ? <div style={{ overflowX: "auto" }}><table className="cp-table"><thead><tr><th>内容标题</th><th>平台</th><th>提交时间</th><th>状态</th></tr></thead><tbody>{jobs.slice(0, 6).map((job) => <tr key={job.id}><td>{job.title}</td><td>{platformName(job.platform)}</td><td>{time(job.created_at)}</td><td><span className={`cp-badge ${job.status}`}>{statusText[job.status]}</span></td></tr>)}</tbody></table></div> : <div className="cp-empty"><UploadCloud size={27} />暂无发布任务，前往发布中心创建第一条任务</div>}
        </section>
        <section className="cp-panel"><div className="cp-panel-head"><div><h2>工作流入口</h2><p>从内容准备到分析复盘</p></div></div><div className="cp-shortcut-list"><Link className="cp-shortcut" to="/agent"><span><Sparkles size={18} /> AI 运营助手</span><ArrowUpRight size={16} /></Link><Link className="cp-shortcut" to="/publishing"><span><UploadCloud size={18} /> 发布视频</span><ArrowUpRight size={16} /></Link><Link className="cp-shortcut" to="/analytics"><span><Activity size={18} /> 查看数据分析</span><ArrowUpRight size={16} /></Link></div></section>
      </div>
      <div>
        <section className="cp-panel"><div className="cp-panel-head"><div><h2>账号运行状况</h2><p>本地登录态与平台连接状态</p></div><Link className="cp-panel-link" to="/accounts">管理账号 ↗</Link></div>{accounts.length ? accounts.slice(0, 5).map((account) => <div className="cp-account-line" key={account.id}><div><strong>{accountLabel(account)}</strong><small>{platformName(account.platform)} · {account.checked_at ? `检查于 ${time(account.checked_at)}` : "尚未检查"}</small></div><span className={`cp-badge ${account.status}`}>{statusText[account.status]}</span></div>) : <div className="cp-empty"><Users size={27} />尚未绑定平台账号</div>}</section>
        <section className="cp-panel"><div className="cp-panel-head"><div><h2>工作台时间</h2><p>按当前设备的本地时间显示</p></div><Clock3 size={18} color="#737373" /></div><div style={{ fontSize: 30, fontWeight: 600, letterSpacing: -1 }}>{now.toLocaleTimeString("zh-CN", { hour12: false })}</div><div className="cp-muted" style={{ marginTop: 8 }}>{now.toLocaleDateString("zh-CN", { year: "numeric", month: "long", day: "numeric", weekday: "long" })}</div></section>
      </div>
    </div>
  </ConsoleLayout>;
}
