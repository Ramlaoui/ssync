import { LocalStorage, OAuth } from "@raycast/api";
import { existsSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { homedir } from "node:os";
import type { ConnectionSettings, JobCache } from "../types/ssync";

const CONNECTION_KEY = "ssync.connection.v1";
const JOB_CACHE_KEY = "ssync.jobs.cache.v1";
const oauthClient = new OAuth.PKCEClient({
  redirectMethod: OAuth.RedirectMethod.App,
  providerName: "ssync",
  providerId: "ssync-api-key",
});

export const DEFAULT_API_URL = "https://localhost:8042";
export const DEFAULT_HISTORY_WINDOW = "3d";
export const DEFAULT_JOB_LIMIT = 50;
export const STALE_JOB_CACHE_MS = 60_000;

export async function getConnection(): Promise<ConnectionSettings | undefined> {
  const raw = await LocalStorage.getItem<string>(CONNECTION_KEY);
  if (!raw) return undefined;
  try {
    const parsed = JSON.parse(raw) as ConnectionSettings;
    if (!parsed.apiUrl) return undefined;
    if (parsed.apiKey) {
      await saveApiKey(parsed.apiKey);
      delete parsed.apiKey;
      await LocalStorage.setItem(CONNECTION_KEY, JSON.stringify(parsed));
    }
    return {
      apiUrl: parsed.apiUrl,
      apiKey: await getStoredApiKey(),
      historyWindow: parsed.historyWindow || DEFAULT_HISTORY_WINDOW,
      jobLimit: Number(parsed.jobLimit) || DEFAULT_JOB_LIMIT,
      updatedAt: parsed.updatedAt || Date.now(),
    };
  } catch {
    return undefined;
  }
}

export async function saveConnection(settings: Omit<ConnectionSettings, "updatedAt">): Promise<ConnectionSettings> {
  const next: ConnectionSettings = {
    ...settings,
    apiUrl: settings.apiUrl.trim().replace(/\/+$/, ""),
    apiKey: settings.apiKey?.trim() || "",
    historyWindow: settings.historyWindow || DEFAULT_HISTORY_WINDOW,
    jobLimit: Number(settings.jobLimit) || DEFAULT_JOB_LIMIT,
    updatedAt: Date.now(),
  };
  if (next.apiKey) {
    await saveApiKey(next.apiKey);
  } else {
    await clearApiKey();
  }
  const { apiKey: _apiKey, ...nonSecretSettings } = next;
  await LocalStorage.setItem(CONNECTION_KEY, JSON.stringify(nonSecretSettings));
  return next;
}

export async function clearConnection(): Promise<void> {
  await LocalStorage.removeItem(CONNECTION_KEY);
  await clearApiKey();
}

export async function getJobCache(): Promise<JobCache | undefined> {
  const raw = await LocalStorage.getItem<string>(JOB_CACHE_KEY);
  if (!raw) return undefined;
  try {
    const parsed = JSON.parse(raw) as JobCache;
    if (!Array.isArray(parsed.responses) || typeof parsed.loadedAt !== "number") return undefined;
    return parsed;
  } catch {
    return undefined;
  }
}

export async function saveJobCache(cache: JobCache): Promise<void> {
  await LocalStorage.setItem(JOB_CACHE_KEY, JSON.stringify(cache));
}

export async function clearJobCache(): Promise<void> {
  await LocalStorage.removeItem(JOB_CACHE_KEY);
}

export function readLocalApiKey(): string {
  const keyPath = join(homedir(), ".config", "ssync", ".api_key");
  if (!existsSync(keyPath)) return "";

  try {
    const raw = readFileSync(keyPath, "utf8").trim();
    if (!raw) return "";

    try {
      const parsed = JSON.parse(raw) as unknown;
      if (typeof parsed === "string") return parsed;
      if (parsed && typeof parsed === "object") {
        const record = parsed as Record<string, unknown>;
        const values = Object.values(record);
        const stringValue = values.find((value): value is string => typeof value === "string" && value.length > 0);
        if (stringValue) return stringValue;
        const firstKey = Object.keys(record)[0];
        if (firstKey) return firstKey;
      }
    } catch {
      return raw;
    }

    return raw;
  } catch {
    return "";
  }
}

async function getStoredApiKey(): Promise<string> {
  const tokenSet = await oauthClient.getTokens();
  return tokenSet?.accessToken || "";
}

async function saveApiKey(apiKey: string): Promise<void> {
  await oauthClient.setTokens({ accessToken: apiKey });
}

async function clearApiKey(): Promise<void> {
  await oauthClient.removeTokens();
}
