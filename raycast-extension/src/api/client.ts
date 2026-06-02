import http from "node:http";
import https from "node:https";
import type {
  ConnectionSettings,
  JobInfo,
  JobOutputResponse,
  JobScriptResponse,
  JobStatusResponse,
  WatcherEventsResponse,
  WatchersResponse,
} from "../types/ssync";

type RequestOptions = {
  method?: "GET" | "POST";
  params?: Record<string, string | number | boolean | undefined | null>;
  body?: unknown;
  timeoutMs?: number;
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
  constructor(private readonly connection: Pick<ConnectionSettings, "apiUrl" | "apiKey">) {}

  async testConnection(): Promise<void> {
    await this.request<Record<string, unknown>>("/api/info", { timeoutMs: 10_000 });
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
    return this.request<JobInfo>(`/api/jobs/${encodeURIComponent(job.job_id)}`, {
      params: {
        host: job.hostname,
        cache_first: true,
        force_refresh: forceRefresh || undefined,
      },
      timeoutMs: 30_000,
    });
  }

  async getOutput(options: {
    job: JobInfo;
    outputType: "stdout" | "stderr";
    lines?: number;
    fullOutput?: boolean;
    forceRefresh?: boolean;
  }): Promise<JobOutputResponse> {
    return this.request<JobOutputResponse>(`/api/jobs/${encodeURIComponent(options.job.job_id)}/output`, {
      params: {
        host: options.job.hostname,
        output_type: options.outputType,
        lines: options.fullOutput ? undefined : options.lines,
        all: options.fullOutput || undefined,
        force_refresh: options.forceRefresh || undefined,
      },
      timeoutMs: options.fullOutput ? 90_000 : 45_000,
    });
  }

  async getScript(job: JobInfo): Promise<JobScriptResponse> {
    return this.request<JobScriptResponse>(`/api/jobs/${encodeURIComponent(job.job_id)}/script`, {
      params: { host: job.hostname },
      timeoutMs: 45_000,
    });
  }

  async getWatchers(job: JobInfo): Promise<WatchersResponse> {
    return this.request<WatchersResponse>(`/api/jobs/${encodeURIComponent(job.job_id)}/watchers`, {
      params: { host: job.hostname },
      timeoutMs: 30_000,
    });
  }

  async getWatcherEvents(job: JobInfo, limit = 100): Promise<WatcherEventsResponse> {
    return this.request<WatcherEventsResponse>("/api/watchers/events", {
      params: {
        job_id: job.job_id,
        limit,
      },
      timeoutMs: 30_000,
    });
  }

  async cancelJob(job: JobInfo): Promise<void> {
    await this.request<Record<string, unknown>>(`/api/jobs/${encodeURIComponent(job.job_id)}/cancel`, {
      method: "POST",
      params: { host: job.hostname },
      timeoutMs: 30_000,
    });
  }

  private request<T>(path: string, options: RequestOptions = {}): Promise<T> {
    const base = this.connection.apiUrl.replace(/\/+$/, "");
    const url = new URL(path, base);
    for (const [key, value] of Object.entries(options.params || {})) {
      if (value === undefined || value === null || value === "") continue;
      url.searchParams.set(key, String(value));
    }

    const isHttps = url.protocol === "https:";
    const transport = isHttps ? https : http;
    const headers: Record<string, string> = {
      Accept: "application/json",
      "Content-Type": "application/json",
    };
    if (this.connection.apiKey) headers["X-API-Key"] = this.connection.apiKey;

    return new Promise<T>((resolve, reject) => {
      const request = transport.request(
        url,
        {
          method: options.method || "GET",
          headers,
          timeout: options.timeoutMs || 30_000,
          ...(isHttps ? { rejectUnauthorized: false } : {}),
        },
        (response) => {
          const chunks: Buffer[] = [];
          response.on("data", (chunk: Buffer) => chunks.push(chunk));
          response.on("end", () => {
            const text = Buffer.concat(chunks).toString("utf8");
            const statusCode = response.statusCode || 0;

            if (statusCode >= 400) {
              reject(new SsyncApiError(errorMessage(statusCode, text), statusCode));
              return;
            }

            if (!text) {
              resolve(undefined as T);
              return;
            }

            try {
              resolve(JSON.parse(text) as T);
            } catch {
              reject(new SsyncApiError(`Invalid JSON response from ssync API: ${text.slice(0, 120)}`, statusCode));
            }
          });
        },
      );

      request.on("timeout", () => {
        request.destroy(new SsyncApiError("Request timed out"));
      });
      request.on("error", (error) => {
        reject(error instanceof SsyncApiError ? error : new SsyncApiError(error.message));
      });

      if (options.body !== undefined) request.write(JSON.stringify(options.body));
      request.end();
    });
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
