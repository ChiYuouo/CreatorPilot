import client from "./client";
export type AnalyticsPlatform = "xiaohongshu" | "douyin" | "kuaishou" | "bilibili" | "tencent" | "youtube";
type Platform = AnalyticsPlatform;

export interface PublishedContentWrite {
  platform: Platform;
  title: string;
  published_at: string;
}

export interface MetricWrite {
  metric_date: string;
  views: number | null;
  likes: number | null;
  comments: number | null;
  favorites: number | null;
  shares: number | null;
  follower_gain: number | null;
}

export interface Metric extends MetricWrite {
  source: string;
  collected_at: string | null;
  platform_updated_at: string | null;
  id: number;
  content_id: number;
}

export interface PublishedContent extends PublishedContentWrite {
  account_id: number | null;
  platform_content_id: string | null;
  id: number;
  metrics: Metric[];
  created_at: string;
  updated_at: string;
}

export interface AnalyticsReport {
  id?: number;
  title?: string;
  created_at?: string;
  content_id?: number | null;
  without_metrics_count?: number;
  scope: "single_content" | "recent_contents" | "batch_contents";
  report: string;
  content_count: number;
  excluded_without_metrics: number;
  days: number | null;
}

export type AnalyticsReportSummary = Omit<AnalyticsReport, "report">;
export interface AnalyticsReportPage { items: AnalyticsReportSummary[]; total: number }

export const analyticsApi = {
  async deleteReport(id: number) {
    await client.delete(`/analytics/reports/${id}`);
  },
  async deleteSyncRun(id: number) {
    await client.delete(`/analytics/sync-runs/${id}`);
  },
  async batchReport() {
    const { data } = await client.post<AnalyticsReport>("/analytics/reports/batch");
    return data;
  },
  async listReports(offset = 0, limit = 20) {
    const { data } = await client.get<AnalyticsReportPage>("/analytics/reports", { params: { offset, limit } });
    return data;
  },
  async getReport(id: number) {
    const { data } = await client.get<AnalyticsReport>(`/analytics/reports/${id}`);
    return data;
  },
  async syncRuns() {
    const { data } = await client.get<MetricsSyncRun[]>("/analytics/sync-runs");
    return data;
  },
  async syncAccount(account_id: number) {
    const { data } = await client.post<MetricsSyncRun>("/analytics/sync-runs", { account_id });
    return data;
  },
  async listContents() {
    const { data } = await client.get<PublishedContent[]>("/analytics/contents");
    return data;
  },
  async createContent(value: PublishedContentWrite) {
    const { data } = await client.post<PublishedContent>("/analytics/contents", value);
    return data;
  },
  async updateContent(id: number, value: PublishedContentWrite) {
    const { data } = await client.put<PublishedContent>(`/analytics/contents/${id}`, value);
    return data;
  },
  async deleteContent(id: number) {
    await client.delete(`/analytics/contents/${id}`);
  },
  async saveMetric(id: number, value: MetricWrite) {
    const { data } = await client.put<Metric>(`/analytics/contents/${id}/metrics`, value);
    return data;
  },
  async deleteMetric(id: number, metricDate: string) {
    await client.delete(`/analytics/contents/${id}/metrics/${metricDate}`);
  },
  async contentReport(id: number) {
    const { data } = await client.post<AnalyticsReport>(`/analytics/contents/${id}/report`);
    return data;
  },
  async recentReport(days: 7 | 30 | 90) {
    const { data } = await client.post<AnalyticsReport>(`/analytics/reports/recent?days=${days}`);
    return data;
  },
};

export interface MetricsSyncRun {
  id: number;
  account_id: number;
  status: "queued" | "running" | "completed" | "failed";
  content_count: number;
  metric_count: number;
  message: string | null;
  created_at: string;
  updated_at: string;
}
