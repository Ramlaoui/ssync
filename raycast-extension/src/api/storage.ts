import { LocalStorage, OAuth } from "@raycast/api";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { homedir } from "node:os";
import { randomUUID } from "node:crypto";
import {
  connectionScope,
  DEFAULT_HISTORY_WINDOW,
  DEFAULT_JOB_LIMIT,
  normalizeApiUrl,
  validateJobLimit,
} from "../lib/connections";
import type {
  ConnectionInput,
  ConnectionSettings,
  JobCache,
  WorkspaceSettings,
} from "../types/ssync";

export {
  DEFAULT_API_URL,
  DEFAULT_HISTORY_WINDOW,
  DEFAULT_JOB_LIMIT,
} from "../lib/connections";
export const STALE_JOB_CACHE_MS = 60_000;
const LEGACY_CONNECTION_KEY = "ssync.connection.v1";
const PROFILES_KEY = "ssync.connections.v2";
const CACHE_PREFIX = "ssync.jobs.cache.v2:";
const WORKSPACE_PREFIX = "ssync.workspace.v2:";
type Profile = Omit<ConnectionSettings, "apiKey"> & { credentialId?: string };
type Profiles = { activeId?: string; profiles: Profile[] };

function credentialStore(id?: string) {
  return new OAuth.PKCEClient({
    redirectMethod: OAuth.RedirectMethod.App,
    providerName: "ssync",
    providerId: id ? "ssync-api-key-" + id : "ssync-api-key",
  });
}

async function readProfiles(): Promise<Profiles> {
  const raw = await LocalStorage.getItem<string>(PROFILES_KEY);
  if (raw) {
    const parsed = JSON.parse(raw) as Profiles;
    if (!Array.isArray(parsed.profiles))
      throw new Error("Saved connections could not be read.");
    return parsed;
  }
  const legacy = await LocalStorage.getItem<string>(LEGACY_CONNECTION_KEY);
  if (!legacy) return { profiles: [] };
  const old = JSON.parse(legacy) as Partial<ConnectionSettings>;
  if (!old.apiUrl) return { profiles: [] };
  const apiKey =
    old.apiKey || (await credentialStore().getTokens())?.accessToken || "";
  const profile: Profile = {
    id: "legacy",
    name: new URL(old.apiUrl).host,
    apiUrl: normalizeApiUrl(old.apiUrl),
    historyWindow: old.historyWindow || DEFAULT_HISTORY_WINDOW,
    jobLimit: Number(old.jobLimit) || DEFAULT_JOB_LIMIT,
    updatedAt: old.updatedAt || Date.now(),
  };
  if (apiKey)
    await credentialStore(profile.id).setTokens({ accessToken: apiKey });
  const migrated = { activeId: profile.id, profiles: [profile] };
  await LocalStorage.setItem(PROFILES_KEY, JSON.stringify(migrated));
  await LocalStorage.removeItem(LEGACY_CONNECTION_KEY);
  await LocalStorage.removeItem("ssync.jobs.cache.v1");
  await credentialStore().removeTokens();
  return migrated;
}

export async function getConnections(): Promise<{
  activeId?: string;
  profiles: Profile[];
}> {
  return readProfiles();
}

export async function getConnection(
  id?: string,
): Promise<ConnectionSettings | undefined> {
  const stored = await readProfiles();
  const profile = stored.profiles.find(
    (item) => item.id === (id || stored.activeId),
  );
  if (!profile) return undefined;
  const { credentialId, ...settings } = profile;
  return {
    ...settings,
    apiKey:
      (await credentialStore(credentialId || profile.id).getTokens())
        ?.accessToken || "",
  };
}

export async function saveConnection(
  input: ConnectionInput,
): Promise<ConnectionSettings> {
  const stored = await readProfiles();
  const next: ConnectionSettings = {
    ...input,
    id: input.id || randomUUID(),
    name: input.name.trim(),
    apiUrl: normalizeApiUrl(input.apiUrl),
    apiKey: input.apiKey?.trim() || "",
    historyWindow: input.historyWindow || DEFAULT_HISTORY_WINDOW,
    jobLimit: validateJobLimit(input.jobLimit),
    updatedAt: Date.now(),
  };
  if (!next.name) next.name = new URL(next.apiUrl).host;
  const index = stored.profiles.findIndex((item) => item.id === next.id);
  const previous = stored.profiles[index];
  const previousCredential = previous?.credentialId || previous?.id;
  const previousKey = previousCredential
    ? (await credentialStore(previousCredential).getTokens())?.accessToken || ""
    : "";
  const credentialChanged =
    !previous || previous.apiUrl !== next.apiUrl || previousKey !== next.apiKey;
  // Publish a new credential reference together with its URL. Readers never see
  // a new URL paired with the old connection's key, even if persistence fails.
  const credentialId = credentialChanged ? randomUUID() : previousCredential!;
  const vault = credentialStore(credentialId);
  if (credentialChanged && next.apiKey)
    await vault.setTokens({ accessToken: next.apiKey });
  const { apiKey: _secret, ...nonSecret } = next;
  const profile = { ...nonSecret, credentialId };
  if (index < 0) stored.profiles.push(profile);
  else stored.profiles[index] = profile;
  stored.activeId ||= next.id;
  try {
    await LocalStorage.setItem(PROFILES_KEY, JSON.stringify(stored));
  } catch (error) {
    if (credentialChanged) await vault.removeTokens();
    throw error;
  }
  if (credentialChanged && previousCredential)
    await credentialStore(previousCredential)
      .removeTokens()
      .catch(() => undefined);
  if (
    !previous ||
    connectionScope({ ...previous, apiKey: previousKey }) !==
      connectionScope(next)
  )
    await clearJobCache(next.id);
  if (previous && previous.apiUrl !== next.apiUrl)
    await LocalStorage.removeItem(WORKSPACE_PREFIX + next.id);
  else if (previous && previous.defaultHost !== next.defaultHost) {
    const workspace = await getWorkspace(next);
    await saveWorkspace(next, { ...workspace, host: next.defaultHost || "" });
  }
  return next;
}

export async function setActiveConnection(id: string): Promise<void> {
  const stored = await readProfiles();
  if (!stored.profiles.some((item) => item.id === id))
    throw new Error("Connection no longer exists.");
  stored.activeId = id;
  await LocalStorage.setItem(PROFILES_KEY, JSON.stringify(stored));
}

export async function removeConnection(id: string): Promise<void> {
  const stored = await readProfiles();
  const profile = stored.profiles.find((item) => item.id === id);
  stored.profiles = stored.profiles.filter((item) => item.id !== id);
  if (stored.activeId === id) stored.activeId = stored.profiles[0]?.id;
  await LocalStorage.setItem(PROFILES_KEY, JSON.stringify(stored));
  await credentialStore(profile?.credentialId || id).removeTokens();
  await clearJobCache(id);
  await LocalStorage.removeItem(WORKSPACE_PREFIX + id);
}

function cacheKey(connection: ConnectionSettings) {
  return CACHE_PREFIX + connection.id + ":" + connectionScope(connection);
}

export async function getJobCache(
  connection: ConnectionSettings,
): Promise<JobCache | undefined> {
  const raw = await LocalStorage.getItem<string>(cacheKey(connection));
  if (!raw) return undefined;
  try {
    const cache = JSON.parse(raw) as JobCache;
    return Array.isArray(cache.responses) && Number.isFinite(cache.loadedAt)
      ? cache
      : undefined;
  } catch {
    return undefined;
  }
}

export async function saveJobCache(
  connection: ConnectionSettings,
  cache: JobCache,
): Promise<void> {
  await LocalStorage.setItem(cacheKey(connection), JSON.stringify(cache));
}

export async function clearJobCache(connectionId: string): Promise<void> {
  const items = await LocalStorage.allItems();
  await Promise.all(
    Object.keys(items)
      .filter((key) => key.startsWith(CACHE_PREFIX + connectionId + ":"))
      .map((key) => LocalStorage.removeItem(key)),
  );
}

export const defaultWorkspace: WorkspaceSettings = {
  host: "",
  view: "all",
  showDetail: true,
  pinnedJobs: [],
};
export async function getWorkspace(
  connection: ConnectionSettings,
): Promise<WorkspaceSettings> {
  const fallback = { ...defaultWorkspace, host: connection.defaultHost || "" };
  const raw = await LocalStorage.getItem<string>(
    WORKSPACE_PREFIX + connection.id,
  );
  if (!raw) return fallback;
  try {
    const value = JSON.parse(raw) as WorkspaceSettings;
    return {
      ...fallback,
      ...value,
      pinnedJobs: Array.isArray(value.pinnedJobs) ? value.pinnedJobs : [],
    };
  } catch {
    return fallback;
  }
}
export async function saveWorkspace(
  connection: ConnectionSettings,
  workspace: WorkspaceSettings,
): Promise<void> {
  await LocalStorage.setItem(
    WORKSPACE_PREFIX + connection.id,
    JSON.stringify(workspace),
  );
}

// Called only by the explicit "Use Local ssync API Key" action on a loopback connection.
export function readLocalApiKey(): string {
  try {
    const raw = readFileSync(
      join(homedir(), ".config", "ssync", ".api_key"),
      "utf8",
    ).trim();
    if (!raw) return "";
    try {
      const parsed: unknown = JSON.parse(raw);
      if (typeof parsed === "string") return parsed;
      if (parsed && typeof parsed === "object") {
        const value = Object.values(parsed).find(
          (item): item is string => typeof item === "string" && item.length > 0,
        );
        return value || Object.keys(parsed)[0] || "";
      }
    } catch {
      return raw;
    }
    return "";
  } catch {
    return "";
  }
}
