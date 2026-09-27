import client from "./client";

export interface PublishingOverview {
  account_count: number;
  asset_count: number;
  pending_count: number;
  failed_count: number;
}

export interface PlatformAccount {
  id: number;
  platform: string;
  account_name: string;
  remark: string | null;
  status: "unchecked" | "valid" | "expired";
  checked_at: string | null;
  created_at: string;
}

export interface LoginSession {
  id: string;
  status: "starting" | "waiting" | "qrcode_ready" | "success" | "failed" | "cancelled";
  platform: string;
  qrcode_data_url: string | null;
  message: string | null;
  account_id: number | null;
}

export interface CheckAllResult {
  accounts: PlatformAccount[];
  failed_ids: number[];
}

export interface MediaAsset {
  id: number;
  media_type: "video" | "image";
  filename: string;
  size_bytes: number;
  created_at: string;
}

export interface PublishingPlatform {
  key: string;
  name: string;
  title_max_length: number;
  description_required: boolean;
  tags_max_count: number;
  category_required: boolean;
  metrics_sync_supported: boolean;
  image_publish_supported: boolean;
  image_max_count: number;
  image_title_max_length: number;
  image_description_max_length: number;
}

export interface PublishJob {
  id: number;
  platform: string;
  title: string;
  account_id: number;
  plan_id: number | null;
  asset_id: number;
  image_asset_ids: number[];
  description: string;
  tags: string[];
  status: "queued" | "running" | "cancel_requested" | "canceled" | "submitted" | "failed" | "needs_review" | "confirmed" | "not_published";
  error_message: string | null;
  submitted_at: string | null;
  confirmed_at: string | null;
  scheduled_at: string | null;
  created_at: string;
  auto_stop_at: string | null;
}

export const publishingApi = {
  async videoPreview(id: number, signal?: AbortSignal) {
    const { data } = await client.post<{ url: string; expires_in: number }>(`/publishing/assets/${id}/video-preview`, null, { signal });
    return data;
  },
  async imgPreview(id: number, signal?: AbortSignal) {
    const { data } = await client.get<Blob>(`/publishing/assets/${id}/preview`, { responseType: "blob", signal });
    return data;
  },
  async platforms() {
    const { data } = await client.get<PublishingPlatform[]>("/publishing/platforms");
    return data;
  },
  async overview() {
    const { data } = await client.get<PublishingOverview>("/publishing/overview");
    return data;
  },
  async accounts() {
    const { data } = await client.get<PlatformAccount[]>("/publishing/accounts");
    return data;
  },
  async updateAccountRemark(id: number, remark: string) {
    const { data } = await client.patch<PlatformAccount>(`/publishing/accounts/${id}`, { remark });
    return data;
  },
  async addAccount(account_name: string, claim_code: string) {
    const { data } = await client.post<PlatformAccount>("/publishing/accounts", { account_name, claim_code });
    return data;
  },
  async checkAccount(id: number) {
    const { data } = await client.post<PlatformAccount>(`/publishing/accounts/${id}/check`);
    return data;
  },
  async startLogin(platform: string, remark: string) {
    const { data } = await client.post<LoginSession>("/publishing/accounts/login-sessions", { platform, remark: remark.trim() || null });
    return data;
  },
  async restartLogin(id: number) {
    const { data } = await client.post<LoginSession>(`/publishing/accounts/${id}/login-sessions`);
    return data;
  },
  async loginSession(id: string, remark?: string) {
    const { data } = await client.get<LoginSession>(`/publishing/login-sessions/${id}`, {
      params: remark === undefined ? undefined : { remark },
    });
    return data;
  },
  async cancelLogin(id: string) {
    await client.delete(`/publishing/login-sessions/${id}`);
  },
  async checkAllAccounts() {
    const { data } = await client.post<CheckAllResult>("/publishing/accounts/check-all");
    return data;
  },
  async clearExpiredAccounts() {
    const { data } = await client.delete<{ deleted_count: number }>("/publishing/accounts/expired");
    return data;
  },
  async deleteAccount(id: number) {
    await client.delete(`/publishing/accounts/${id}`);
  },
  async assets() {
    const { data } = await client.get<MediaAsset[]>("/publishing/assets");
    return data;
  },
  async upload(file: File) {
    const form = new FormData();
    form.append("file", file);
    const { data } = await client.post<MediaAsset>("/publishing/assets", form);
    return data;
  },
  async jobs() {
    const { data } = await client.get<PublishJob[]>("/publishing/jobs");
    return data;
  },
  async cancelJob(id: number) {
    const { data } = await client.post<PublishJob>(`/publishing/jobs/${id}/cancel`);
    return data;
  },
  async confirmJob(id: number, result: "published" | "not_published") {
    const { data } = await client.post<PublishJob>(`/publishing/jobs/${id}/confirm`, { result });
    return data;
  },
  async deleteJob(id: number) {
    await client.delete(`/publishing/jobs/${id}`);
  },
  async publish(account_id: number, asset_id: number, title: string, description: string, tags: string[]) {
    const { data } = await client.post<PublishJob>("/publishing/jobs", { account_id, asset_id, title, description, tags });
    return data;
  },
  async publishPlan(value: { account_ids: number[]; asset_id: number; image_asset_ids: number[]; title: string; description: string; tags: string[]; scheduled_at: string | null; platform_options: Record<string, { tid?: number }> }) {
    const { data } = await client.post<{ plan_id: number; jobs: PublishJob[] }>("/publishing/plans", value);
    return data;
  },
};
