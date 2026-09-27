import { useEffect, useState } from "react";
import { Trash2 } from "lucide-react";
import { toast } from "sonner";
import { analyticsApi, type AnalyticsReport, type AnalyticsReportPage } from "@/api/analytics";
import { Dialog } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import AnalyticsReportView from "@/components/AnalyticsReportView";

const PAGE_SIZE = 20;
const labels = { single_content: "单篇分析", batch_contents: "批量分析", recent_contents: "定期汇总" };

export default function AnalyticsReportHistory({ open, onOpenChange, onDeleted }: { open: boolean; onOpenChange: (open: boolean) => void; onDeleted?: (id: number) => void }) {
  const [deletingId, setDeletingId] = useState<number | null>(null);
  const [page, setPage] = useState<AnalyticsReportPage>({ items: [], total: 0 });
  const [offset, setOffset] = useState(0);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [report, setReport] = useState<AnalyticsReport | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [retry, setRetry] = useState(0);

  useEffect(() => {
    if (!open) { setOffset(0); setSelectedId(null); setReport(null); return; }
    let disposed = false;
    setLoading(true); setError(""); setReport(null);
    const request = selectedId === null ? analyticsApi.listReports(offset, PAGE_SIZE) : analyticsApi.getReport(selectedId);
    request.then((data) => {
      if (disposed) return;
      if ("items" in data) setPage(data); else setReport(data);
    }).catch(() => { if (!disposed) setError("报告加载失败，请重试"); })
      .finally(() => { if (!disposed) setLoading(false); });
    return () => { disposed = true; };
  }, [open, offset, selectedId, retry]);

  const deleteReport = async (id: number) => {
    if (!window.confirm("确定删除这份报告？作品和指标会保留。")) return;
    setDeletingId(id);
    try {
      await analyticsApi.deleteReport(id);
      onDeleted?.(id);
      setSelectedId(null); setReport(null);
      setOffset(0); setRetry((value) => value + 1);
      toast.success("报告已删除");
    } catch { toast.error("报告删除失败，请重试"); }
    finally { setDeletingId(null); }
  };

  return <Dialog open={open} onOpenChange={onOpenChange} title="分析历史" description="最多保留最近 20 份报告，超出后自动删除最旧的。删除报告会保留作品和指标。">
    <div className="space-y-4">
      {selectedId !== null && <div className="flex justify-between gap-2"><Button variant="outline" size="sm" onClick={() => setSelectedId(null)}>返回报告列表</Button><Button variant="outline" size="sm" disabled={loading || deletingId !== null} onClick={() => deleteReport(selectedId)}><Trash2 className="mr-1 size-4" />删除报告</Button></div>}
      {loading ? <p className="text-sm text-muted-foreground">加载中…</p> : error ? <div><p>{error}</p><Button onClick={() => setRetry((value) => value + 1)}>重试</Button></div> : selectedId !== null ? report && <><h3 className="font-medium">{report.title}</h3><AnalyticsReportView report={report} /></> : <>
        {page.items.length === 0 && <p className="text-sm text-muted-foreground">暂无分析报告，生成后会自动保存在这里。</p>}
        {page.items.map((item) => <div key={item.id} className="flex items-center gap-2 rounded-md border p-1"><Button variant="ghost" className="h-auto min-w-0 flex-1 flex-col items-start whitespace-normal p-3 text-left" onClick={() => { if (item.id) setSelectedId(item.id); }}>
          <span className="font-medium">{item.title} · {labels[item.scope]}</span>
          <span className="mt-1 text-xs text-muted-foreground">{item.created_at ? new Date(item.created_at).toLocaleString("zh-CN") : ""} · {item.content_count} 篇内容</span>
        </Button><Button variant="ghost" size="sm" aria-label={`删除报告：${item.title}`} disabled={deletingId !== null || !item.id} onClick={() => item.id && deleteReport(item.id)}><Trash2 className="size-4" /></Button></div>)}
        {page.total > 0 && <div className="flex items-center justify-between gap-3"><span className="text-xs text-muted-foreground">共 {page.total} 份 · 第 {Math.floor(offset / PAGE_SIZE) + 1} 页</span><div className="flex gap-2"><Button size="sm" variant="outline" disabled={offset === 0} onClick={() => setOffset(offset - PAGE_SIZE)}>上一页</Button><Button size="sm" variant="outline" disabled={offset + PAGE_SIZE >= page.total} onClick={() => setOffset(offset + PAGE_SIZE)}>下一页</Button></div></div>}
      </>}
    </div>
  </Dialog>;
}
