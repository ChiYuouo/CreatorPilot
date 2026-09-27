import client from "./client";

export interface AutomationTaskWrite {
  task_type: "analysis_report" | "metrics_sync";
  name: string;
  frequency: "weekly";
  weekday: number;
  hour: number;
  minute: number;
  timezone: string;
  payload: { account_ids?: number[]; sync_first?: boolean };
  enabled: boolean;
}

export interface AutomationTask {
  id: number;
  task_type: string;
  name: string;
  frequency: string;
  weekday: number;
  hour: number;
  minute: number;
  timezone: string;
  payload: Record<string, unknown>;
  enabled: boolean;
  next_run_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface AutomationRun {
  id: number;
  task_id: number | null;
  task_type: string;
  task_name: string;
  scheduled_for: string;
  status: "queued" | "running" | "waiting_sync" | "succeeded" | "failed" | "canceled";
  payload: Record<string, unknown>;
  result: Record<string, unknown> | null;
  error_message: string | null;
  started_at: string | null;
  finished_at: string | null;
  created_at: string;
}

export const automationApi = {
  async listTasks() {
    const { data } = await client.get<AutomationTask[]>("/automation/tasks");
    return data;
  },
  async createTask(value: AutomationTaskWrite) {
    const { data } = await client.post<AutomationTask>("/automation/tasks", value);
    return data;
  },
  async updateTask(id: number, value: AutomationTaskWrite) {
    const { data } = await client.put<AutomationTask>(`/automation/tasks/${id}`, value);
    return data;
  },
  async deleteTask(id: number) {
    await client.delete(`/automation/tasks/${id}`);
  },
  async listRuns() {
    const { data } = await client.get<AutomationRun[]>("/automation/runs");
    return data;
  },
};
