import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import type { AnalyticsReport } from "@/api/analytics";

export function AnalyticsReportView({ report }: { report: AnalyticsReport }) {
  return (
    <div className="space-y-3">
      <p className="text-xs text-muted-foreground">
        {report.scope === "batch_contents"
          ? `全部 ${report.content_count} 篇内容 · ${report.without_metrics_count ?? 0} 篇缺少指标（已保留在分析中）`
          : report.scope === "recent_contents"
          ? `近 ${report.days} 天 · 分析 ${report.content_count} 篇有指标的内容 · ${report.excluded_without_metrics} 篇因无指标未纳入`
          : "单篇内容 · 基于已录入的累计指标"}
      </p>
      {report.created_at && <p className="text-xs text-muted-foreground">已保存 · {new Date(report.created_at).toLocaleString("zh-CN")}</p>}
      <div className="space-y-3 text-sm leading-7 [&_h2]:mt-4 [&_h2]:text-base [&_h2]:font-semibold [&_li]:ml-5 [&_li]:list-disc [&_p]:whitespace-pre-wrap">
        <ReactMarkdown remarkPlugins={[remarkGfm]} components={{
          table: ({ children }) => <div className="overflow-x-auto"><table className="w-full border-collapse text-left text-xs">{children}</table></div>,
          th: ({ children }) => <th className="whitespace-nowrap border p-2 font-medium">{children}</th>,
          td: ({ children }) => <td className="border p-2">{children}</td>,
        }}>{report.report}</ReactMarkdown>
      </div>
    </div>
  );
}

export default AnalyticsReportView;
