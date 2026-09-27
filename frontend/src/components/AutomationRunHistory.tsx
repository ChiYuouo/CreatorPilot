import { useState } from "react";

import type { AutomationRun } from "@/api/automation";
import { AnalyticsReportView } from "@/components/AnalyticsReportView";
import { Button } from "@/components/ui/button";

const statusLabel: Record<AutomationRun["status"], string> = {
  queued: "等待执行",
  running: "执行中",
  waiting_sync: "等待指标同步",
  succeeded: "已完成",
  failed: "失败",
  canceled: "已取消",
};

export default function AutomationRunHistory({ runs }: { runs: AutomationRun[] }) {
  const [openId, setOpenId] = useState<number | null>(null);

  if (runs.length === 0) {
    return <p className="text-sm text-muted-foreground">暂无执行记录。任务到期后会在这里显示结果。</p>;
  }

  return <div className="space-y-3">
    {runs.map((run) => <div key={run.id} className="rounded-md border p-3 text-sm">
      <Button type="button" variant="ghost" onClick={() => setOpenId(openId === run.id ? null : run.id)} className="h-auto w-full justify-between gap-3 whitespace-normal p-0 text-left">
        <span>{run.task_name} · {new Date(run.scheduled_for).toLocaleString("zh-CN")}</span>
        <span className={run.status === "failed" ? "text-destructive" : "text-muted-foreground"}>{statusLabel[run.status]}</span>
      </Button>
      {openId === run.id && <div className="mt-3 border-t pt-3">
        {run.error_message && <p className="text-destructive">{run.error_message}</p>}
        {typeof run.result?.message === "string" && <p>{run.result.message}</p>}
        {Array.isArray(run.result?.sync_run_ids) && <p className="text-muted-foreground">同步记录：{run.result.sync_run_ids.join("、")}</p>}
        {typeof run.result?.report === "string" && <AnalyticsReportView report={{
          scope: run.result.scope === "single_content" ? "single_content" : run.result.scope === "recent_contents" || typeof run.payload.days === "number" ? "recent_contents" : "batch_contents", report: run.result.report,
          content_id: typeof run.result.content_id === "number" ? run.result.content_id : null,
          days: typeof run.payload.days === "number" ? run.payload.days : null,
          content_count: typeof run.result.content_count === "number" ? run.result.content_count : 0,
          excluded_without_metrics: typeof run.result.excluded_without_metrics === "number" ? run.result.excluded_without_metrics : 0,
          without_metrics_count: typeof run.result.without_metrics_count === "number" ? run.result.without_metrics_count : 0,
        }} />}
      </div>}
    </div>)}
  </div>;
}
