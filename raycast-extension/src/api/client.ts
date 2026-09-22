import http from "node:http";
import { isLoopback, normalizeApiUrl } from "../lib/connections";
import https from "node:https";
import type {
  HostInfo,
  HostSettings,
  SlurmDefaults,
  PartitionStatus,
  LaunchRequest,
  LaunchResponse,
  LaunchStatus,
  ConnectionSettings,
  JobInfo,
  JobOutputResponse,
  JobScriptResponse,
  JobStatusResponse,
  TriggerWatcherResponse,
  Watcher,
  WatcherEventsResponse,
  WatcherUpdate,
  WatchersResponse,
} from "../types/ssync";

type RequestOptions = {
  method?: "GET" | "POST" | "PUT" | "DELETE";
  params?: Record<string, string | number | boolean | undefined | null>;
  body?: unknown;
  timeoutMs?: number;
};

export type DownloadedOutput = {
  filename: string;
  content: Buffer;
};

export class SsyncApiError extends Error {
  constructor(
    message: string,
    public readonly statusCode?: number,
  ) {
    super(message);
    this.name = "SsyncApiError";
  }
}

export class SsyncClient {
  constructor(
    private readonly connection: Pick<
      ConnectionSettings,
      "apiUrl" | "apiKey" | "allowSelfSigned"
    >,
    private readonly signal?: AbortSignal,
  ) {}

  async testConnection(): Promise<void> {
    await this.request<Record<string, unknown>>("/api/info", {
      timeoutMs: 10_000,
    });
  }

  async getStatus(options: {
    since?: string;
    limit?: number;
    forceRefresh?: boolean;
  }): Promise<JobStatusResponse[]> {
    return this.request<JobStatusResponse[]>("/api/status", {
      params: {
        since: options.since,
        limit: options.limit,
        group_array_jobs: false,
        force_refresh: options.forceRefresh || undefined,
      },
      timeoutMs: 45_000,
    });
  }

  async getJob(job: JobInfo, forceRefresh = false): Promise<JobInfo> {
    return this.request<JobInfo>(
      `/api/jobs/${encodeURIComponent(job.job_id)}`,
      {
        params: {
          host: job.hostname,
          cache_first: true,
          force_refresh: forceRefresh || undefined,
        },
        timeoutMs: 30_000,
      },
    );
  }

  async getOutput(options: {
    job: JobInfo;
    outputType: "stdout" | "stderr";
    lines?: number;
    fullOutput?: boolean;
    forceRefresh?: boolean;
  }): Promise<JobOutputResponse> {
    return this.request<JobOutputResponse>(
      `/api/jobs/${encodeURIComponent(options.job.job_id)}/output`,
      {
        params: {
          host: options.job.hostname,
          output_type: options.outputType,
          lines: options.fullOutput ? undefined : options.lines,
          all: options.fullOutput || undefined,
          force_refresh: options.forceRefresh || undefined,
        },
        timeoutMs: options.fullOutput ? 90_000 : 45_000,
      },
    );
  }

  async downloadOutput(options: {
    job: JobInfo;
    outputType: "stdout" | "stderr";
    forceRefresh?: boolean;
  }): Promise<DownloadedOutput> {
    return this.requestBuffer(
      `/api/jobs/${encodeURIComponent(options.job.job_id)}/output/download`,
      {
        params: {
          host: options.job.hostname,
          output_type: options.outputType,
          compressed: false,
          force_refresh: options.forceRefresh || undefined,
        },
        timeoutMs: 120_000,
        fallbackFilename: `job_${options.job.job_id}_${options.outputType}.log`,
      },
    );
  }

  async getScript(job: JobInfo): Promise<JobScriptResponse> {
    return this.request<JobScriptResponse>(
      `/api/jobs/${encodeURIComponent(job.job_id)}/script`,
      {
        params: { host: job.hostname },
        timeoutMs: 45_000,
      },
    );
  }

  async getWatchers(job: JobInfo): Promise<WatchersResponse> {
    return this.request<WatchersResponse>(
      `/api/jobs/${encodeURIComponent(job.job_id)}/watchers`,
      {
        params: { host: job.hostname },
        timeoutMs: 30_000,
      },
    );
  }

  async getWatcherEvents(options: {
    job?: JobInfo;
    watcherId?: number;
    limit?: number;
  }): Promise<WatcherEventsResponse> {
    const payload = await this.request<WatcherEventsResponse>(
      "/api/watchers/events",
      {
        params: {
          job_id: options.job?.job_id,
          watcher_id: options.watcherId,
          limit: options.limit || 100,
        },
        timeoutMs: 30_000,
      },
    );
    if (options.job)
      payload.events = payload.events.filter(
        (event) =>
          event.hostname === options.job!.hostname &&
          event.job_id === options.job!.job_id,
      );
    return payload;
  }

  async triggerWatcher(
    watcher: Pick<Watcher, "id">,
    testText?: string,
  ): Promise<TriggerWatcherResponse> {
    return this.request<TriggerWatcherResponse>(
      `/api/watchers/${watcher.id}/trigger`,
      {
        method: "POST",
        body: testText || null,
        timeoutMs: 90_000,
      },
    );
  }

  async pauseWatcher(watcher: Pick<Watcher, "id">): Promise<void> {
    await this.request<Record<string, unknown>>(
      `/api/watchers/${watcher.id}/pause`,
      {
        method: "POST",
        timeoutMs: 30_000,
      },
    );
  }

  async resumeWatcher(watcher: Pick<Watcher, "id">): Promise<void> {
    await this.request<Record<string, unknown>>(
      `/api/watchers/${watcher.id}/resume`,
      {
        method: "POST",
        timeoutMs: 30_000,
      },
    );
  }

  async updateWatcher(
    watcher: Pick<Watcher, "id">,
    update: WatcherUpdate,
  ): Promise<Watcher> {
    return this.request<Watcher>(`/api/watchers/${watcher.id}`, {
      method: "PUT",
      body: update,
      timeoutMs: 30_000,
    });
  }

  async deleteWatcher(watcher: Pick<Watcher, "id">): Promise<void> {
    await this.request<Record<string, unknown>>(`/api/watchers/${watcher.id}`, {
      method: "DELETE",
      timeoutMs: 30_000,
    });
  }

  async cancelJob(job: JobInfo): Promise<void> {
    await this.request<Record<string, unknown>>(
      `/api/jobs/${encodeURIComponent(job.job_id)}/cancel`,
      {
        method: "POST",
        params: { host: job.hostname },
        timeoutMs: 30_000,
      },
    );
  }

  getHosts(): Promise<HostInfo[]> {
    return this.request("/api/hosts");
  }
  getPartitions(
    host: string,
    forceRefresh = false,
  ): Promise<PartitionStatus[]> {
    return this.request("/api/partitions", {
      params: { host, force_refresh: forceRefresh },
      timeoutMs: 45_000,
    });
  }
  getHostSettings(host: string): Promise<HostSettings> {
    return this.request("/api/hosts/" + encodeURIComponent(host) + "/settings");
  }
  updateHostSettings(
    host: string,
    settings: { revision: string; slurm_defaults: SlurmDefaults },
  ): Promise<HostSettings> {
    return this.request(
      "/api/hosts/" + encodeURIComponent(host) + "/settings",
      { method: "PUT", body: settings },
    );
  }
  getAllWatchers(): Promise<WatchersResponse> {
    return this.request("/api/watchers", { params: { limit: 500 } });
  }
  createWatcher(job: JobInfo, settings: WatcherUpdate): Promise<Watcher> {
    return this.request("/api/watchers", {
      method: "POST",
      body: { ...settings, job_id: job.job_id, hostname: job.hostname },
    });
  }
  launchJob(request: LaunchRequest): Promise<LaunchResponse> {
    return this.request("/api/jobs/launch", {
      method: "POST",
      body: request,
      timeoutMs: 45_000,
    });
  }
  getLaunchStatus(id: string): Promise<LaunchStatus> {
    return this.request("/api/launches/" + encodeURIComponent(id));
  }

  private async request<T>(
    path: string,
    options: RequestOptions = {},
  ): Promise<T> {
    const { content, statusCode } = await this.requestRaw(
      path,
      options,
      "application/json",
    );
    if (!content.length) return undefined as T;
    try {
      return JSON.parse(content.toString("utf8")) as T;
    } catch {
      throw new SsyncApiError(
        "The ssync API server returned an invalid JSON response.",
        statusCode,
      );
    }
  }

  private async requestBuffer(
    path: string,
    options: RequestOptions & { fallbackFilename: string },
  ): Promise<DownloadedOutput> {
    const result = await this.requestRaw(path, options, "text/plain");
    return {
      content: result.content,
      filename: filenameFromContentDisposition(
        result.disposition,
        options.fallbackFilename,
      ),
    };
  }

  private requestRaw(
    path: string,
    options: RequestOptions,
    accept: string,
  ): Promise<{ content: Buffer; statusCode: number; disposition?: string }> {
    const url = this.buildUrl(path, options.params);
    const isHttps = url.protocol === "https:";
    return new Promise((resolve, reject) => {
      const request = (isHttps ? https : http).request(
        url,
        {
          method: options.method || "GET",
          headers: this.requestHeaders(accept),
          timeout: options.timeoutMs || 30_000,
          signal: this.signal,
          ...(isHttps
            ? {
                rejectUnauthorized: !(
                  isLoopback(this.connection.apiUrl) ||
                  this.connection.allowSelfSigned
                ),
              }
            : {}),
        },
        (response) => {
          const chunks: Buffer[] = [];
          response.on("data", (chunk: Buffer) => chunks.push(chunk));
          response.on("error", reject);
          response.on("aborted", () =>
            reject(
              new SsyncApiError("The ssync API connection was interrupted."),
            ),
          );
          response.on("end", () => {
            const content = Buffer.concat(chunks);
            const statusCode = response.statusCode || 0;
            if (statusCode < 200 || statusCode >= 300) {
              reject(
                new SsyncApiError(
                  errorMessage(statusCode, content.toString("utf8")),
                  statusCode,
                ),
              );
              return;
            }
            resolve({
              content,
              statusCode,
              disposition: response.headers["content-disposition"],
            });
          });
        },
      );
      request.on("timeout", () =>
        request.destroy(new SsyncApiError("The ssync API request timed out.")),
      );
      request.on("error", (error) =>
        reject(
          error instanceof SsyncApiError
            ? error
            : new SsyncApiError(error.message),
        ),
      );
      if (options.body !== undefined)
        request.write(JSON.stringify(options.body));
      request.end();
    });
  }

  private buildUrl(path: string, params?: RequestOptions["params"]): URL {
    const url = new URL(normalizeApiUrl(this.connection.apiUrl) + path);
    for (const [key, value] of Object.entries(params || {})) {
      if (value !== undefined && value !== null && value !== "")
        url.searchParams.set(key, String(value));
    }
    return url;
  }

  private requestHeaders(accept: string): Record<string, string> {
    const headers: Record<string, string> = {
      Accept: accept,
      "Content-Type": "application/json",
    };
    if (this.connection.apiKey) headers["X-API-Key"] = this.connection.apiKey;
    return headers;
  }
}

function errorMessage(statusCode: number, text: string): string {
  if (!text) return `ssync API returned HTTP ${statusCode}`;
  try {
    const parsed = JSON.parse(text) as { detail?: unknown; message?: unknown };
    const detail = parsed.detail || parsed.message;
    if (typeof detail === "string") return detail;
  } catch {
    // Fall through to raw body preview.
  }
  return `ssync API returned HTTP ${statusCode}: ${text.slice(0, 200)}`;
}

function filenameFromContentDisposition(
  header: string | string[] | undefined,
  fallback: string,
): string {
  const raw = Array.isArray(header) ? header[0] : header;
  const match = raw?.match(/filename="?([^";]+)"?/);
  return sanitizeFilename(match?.[1] || fallback);
}

function sanitizeFilename(value: string): string {
  return value.replace(/[^a-zA-Z0-9._-]/g, "_") || "output.log";
}
