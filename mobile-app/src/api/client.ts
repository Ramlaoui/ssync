import type {
  HostInfo,
  JobInfo,
  JobOutputResponse,
  JobScriptResponse,
  JobStatusResponse,
  LaunchJobRequest,
  LaunchJobResponse,
  LaunchStatusResponse,
  LocalListResponse,
  NotificationPreferences,
  NotificationStatus,
  PartitionStatusResponse,
  Watcher,
  WatcherEvent,
  WatcherEventsResponse,
  WatchersResponse
} from "../types/api";

export type ApiError = Error & {
  status?: number;
  detail?: string;
};

type Method = "GET" | "POST" | "PATCH" | "PUT" | "DELETE";

type RequestOptions = {
  params?: Record<string, string | number | boolean | undefined | null>;
  body?: unknown;
  timeoutMs?: number;
};

type NativeWebSocketInit = {
  headers?: Record<string, string>;
};

type NativeWebSocketConstructor = new (
  url: string,
  protocols?: string | string[],
  options?: NativeWebSocketInit
) => WebSocket;

function normalizeBaseURL(baseURL: string): string {
  return baseURL.trim().replace(/\/+$/, "");
}

function asQuery(params?: RequestOptions["params"]): string {
  if (!params) return "";
  const search = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => {
    if (value === undefined || value === null || value === "") return;
    search.append(key, String(value));
  });
  const value = search.toString();
  return value ? `?${value}` : "";
}

export class SsyncApiClient {
  constructor(
    private readonly getBaseURL: () => string,
    private readonly getApiKey: () => string
  ) {}

  get wsBaseURL(): string {
    const baseURL = normalizeBaseURL(this.getBaseURL());
    if (!baseURL) return "";
    if (baseURL.startsWith("https://")) return baseURL.replace(/^https:\/\//, "wss://");
    if (baseURL.startsWith("http://")) return baseURL.replace(/^http:\/\//, "ws://");
    return baseURL;
  }

  buildWebSocketURL(path: string): string {
    return `${this.wsBaseURL}${path}`;
  }

  openWebSocket(path: string): WebSocket {
    const apiKey = this.getApiKey();
    const WebSocketWithOptions = WebSocket as unknown as NativeWebSocketConstructor;
    return new WebSocketWithOptions(
      this.buildWebSocketURL(path),
      undefined,
      apiKey ? { headers: { "X-API-Key": apiKey } } : undefined
    );
  }

  async request<T>(method: Method, path: string, options: RequestOptions = {}): Promise<T> {
    const baseURL = normalizeBaseURL(this.getBaseURL());
    if (!baseURL) {
      const error = new Error("API URL is not configured") as ApiError;
      error.detail = "Set the ssync API URL in Settings.";
      throw error;
    }

    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), options.timeoutMs ?? 90_000);

    try {
      const response = await fetch(`${baseURL}${path}${asQuery(options.params)}`, {
        method,
        credentials: "include",
        headers: {
          Accept: "application/json",
          "Content-Type": "application/json",
          ...(this.getApiKey() ? { "X-API-Key": this.getApiKey() } : {})
        },
        body: options.body === undefined ? undefined : JSON.stringify(options.body),
        signal: controller.signal
      });

      if (!response.ok) {
        let detail = response.statusText;
        try {
          const payload = (await response.json()) as { detail?: string };
          detail = payload.detail || detail;
        } catch {
          // Keep status text.
        }
        const error = new Error(detail) as ApiError;
        error.status = response.status;
        error.detail = detail;
        throw error;
      }

      if (response.status === 204) {
        return undefined as T;
      }

      return (await response.json()) as T;
    } catch (error) {
      if ((error as Error).name === "AbortError") {
        const timeoutError = new Error("Request timed out") as ApiError;
        timeoutError.detail = "The API did not respond before the timeout.";
        throw timeoutError;
      }
      throw error;
    } finally {
      clearTimeout(timeout);
    }
  }

  get<T>(path: string, params?: RequestOptions["params"]): Promise<T> {
    return this.request<T>("GET", path, { params });
  }

  post<T>(path: string, body?: unknown, params?: RequestOptions["params"]): Promise<T> {
    return this.request<T>("POST", path, { body, params });
  }

  patch<T>(path: string, body?: unknown): Promise<T> {
    return this.request<T>("PATCH", path, { body });
  }

  put<T>(path: string, body?: unknown): Promise<T> {
    return this.request<T>("PUT", path, { body });
  }

  delete<T>(path: string): Promise<T> {
    return this.request<T>("DELETE", path);
  }

  async testConnection(): Promise<boolean> {
    if (this.getApiKey()) {
      await this.post<{ authenticated: boolean }>("/api/auth/session");
    }
    await this.getHosts();
    return true;
  }

  getHosts(): Promise<HostInfo[]> {
    return this.get<HostInfo[]>("/api/hosts");
  }

  getStatus(params: {
    host?: string;
    user?: string;
    since?: string;
    limit?: number;
    state?: string;
    active_only?: boolean;
    completed_only?: boolean;
    search?: string;
    group_array_jobs?: boolean;
    force_refresh?: boolean;
  }): Promise<JobStatusResponse[]> {
    return this.get<JobStatusResponse[]>("/api/status", params);
  }

  getPartitions(host?: string, forceRefresh = false): Promise<PartitionStatusResponse[]> {
    return this.get<PartitionStatusResponse[]>("/api/partitions", {
      host,
      force_refresh: forceRefresh || undefined
    });
  }

  getJob(jobId: string, host: string, forceRefresh = false): Promise<JobInfo> {
    return this.get<JobInfo>(`/api/jobs/${encodeURIComponent(jobId)}`, {
      host,
      force_refresh: forceRefresh || undefined
    });
  }

  getJobOutput(jobId: string, host: string, outputType: "stdout" | "stderr" | "both", forceRefresh = false): Promise<JobOutputResponse> {
    return this.get<JobOutputResponse>(`/api/jobs/${encodeURIComponent(jobId)}/output`, {
      host,
      output_type: outputType,
      max_bytes: 524_288,
      force_refresh: forceRefresh || undefined
    });
  }

  getJobScript(jobId: string, host: string): Promise<JobScriptResponse> {
    return this.get<JobScriptResponse>(`/api/jobs/${encodeURIComponent(jobId)}/script`, { host });
  }

  cancelJob(jobId: string, host: string): Promise<{ message: string }> {
    return this.post<{ message: string }>(`/api/jobs/${encodeURIComponent(jobId)}/cancel`, undefined, { host });
  }

  launchJob(payload: LaunchJobRequest): Promise<LaunchJobResponse> {
    return this.post<LaunchJobResponse>("/api/jobs/launch", payload);
  }

  getLaunchStatus(launchId: string): Promise<LaunchStatusResponse> {
    return this.get<LaunchStatusResponse>(`/api/launches/${encodeURIComponent(launchId)}`);
  }

  listLocalPath(path: string, dirsOnly = true): Promise<LocalListResponse> {
    return this.get<LocalListResponse>("/api/local/list", { path, dirs_only: dirsOnly, limit: 200 });
  }

  getWatchers(limit = 300): Promise<WatchersResponse> {
    return this.get<WatchersResponse>("/api/watchers", { limit });
  }

  getJobWatchers(jobId: string, host: string): Promise<WatchersResponse> {
    return this.get<WatchersResponse>(`/api/jobs/${encodeURIComponent(jobId)}/watchers`, { host });
  }

  getWatcherEvents(params: { job_id?: string; watcher_id?: number; limit?: number } = {}): Promise<WatcherEventsResponse> {
    return this.get<WatcherEventsResponse>("/api/watchers/events", { limit: 300, ...params });
  }

  createWatcher(payload: Record<string, unknown>): Promise<Watcher> {
    return this.post<Watcher>("/api/watchers", payload);
  }

  updateWatcher(watcherId: number, payload: Record<string, unknown>): Promise<Watcher> {
    return this.put<Watcher>(`/api/watchers/${watcherId}`, payload);
  }

  pauseWatcher(watcherId: number): Promise<Record<string, unknown>> {
    return this.post<Record<string, unknown>>(`/api/watchers/${watcherId}/pause`);
  }

  resumeWatcher(watcherId: number): Promise<Record<string, unknown>> {
    return this.post<Record<string, unknown>>(`/api/watchers/${watcherId}/resume`);
  }

  triggerWatcher(watcherId: number, testText?: string): Promise<Record<string, unknown>> {
    return this.post<Record<string, unknown>>(`/api/watchers/${watcherId}/trigger`, testText || null);
  }

  deleteWatcher(watcherId: number): Promise<Record<string, unknown>> {
    return this.delete<Record<string, unknown>>(`/api/watchers/${watcherId}`);
  }

  getNotificationPreferences(): Promise<NotificationPreferences> {
    return this.get<NotificationPreferences>("/api/notifications/preferences");
  }

  patchNotificationPreferences(payload: Partial<NotificationPreferences>): Promise<NotificationPreferences> {
    return this.patch<NotificationPreferences>("/api/notifications/preferences", payload);
  }

  registerNotificationDevice(payload: {
    token: string;
    platform: string;
    token_type?: string;
    client_type?: string;
    payload_format?: string;
    environment?: string;
    bundle_id?: string;
    device_id?: string;
    enabled?: boolean;
  }): Promise<{ success: boolean; token: string; token_type: string; client_type: string; payload_format: string }> {
    return this.post<{ success: boolean; token: string; token_type: string; client_type: string; payload_format: string }>("/api/notifications/devices", payload);
  }

  sendTestNotification(payload: { title: string; body: string; token?: string; token_type?: string }): Promise<{ success: boolean; sent: number }> {
    return this.post<{ success: boolean; sent: number }>("/api/notifications/test", payload);
  }

  getNotificationStatus(): Promise<NotificationStatus> {
    return this.get<NotificationStatus>("/api/notifications/status");
  }

  getCacheStats(): Promise<{ statistics: Record<string, unknown> }> {
    return this.get<{ statistics: Record<string, unknown> }>("/api/cache/stats");
  }

  clearCache(): Promise<{ status: string; message: string }> {
    return this.post<{ status: string; message: string }>("/api/cache/clear");
  }

  getInfo(): Promise<Record<string, unknown>> {
    return this.get<Record<string, unknown>>("/api/info");
  }

  getLogs(lines = 50): Promise<{ logs: string[]; count: number }> {
    return this.get<{ logs: string[]; count: number }>("/api/logs", { lines });
  }

  getConnectionStats(): Promise<Record<string, unknown>> {
    return this.get<Record<string, unknown>>("/api/connections/stats");
  }

  refreshConnections(): Promise<Record<string, unknown>> {
    return this.post<Record<string, unknown>>("/api/connections/refresh");
  }
}
