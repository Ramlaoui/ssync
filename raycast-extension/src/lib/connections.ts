import { createHash } from "node:crypto";
import type { ConnectionSettings } from "../types/ssync";

export const DEFAULT_API_URL = "https://localhost:8042";
export const DEFAULT_HISTORY_WINDOW = "3d";
export const DEFAULT_JOB_LIMIT = 50;
export const HISTORY_WINDOWS = ["1d", "3d", "7d", "14d", "30d"];

export function normalizeApiUrl(value: string): string {
  let url: URL;
  try {
    url = new URL(value.trim());
  } catch {
    throw new Error("Enter a complete http:// or https:// ssync API URL.");
  }
  if (!["http:", "https:"].includes(url.protocol) || !url.hostname)
    throw new Error("The ssync API URL must use HTTP or HTTPS.");
  if (url.username || url.password || url.search || url.hash)
    throw new Error(
      "Use an ssync API URL without credentials, a query, or a fragment.",
    );
  return url.toString().replace(/\/+$/, "");
}

export function isLoopback(apiUrl: string): boolean {
  try {
    return ["localhost", "127.0.0.1", "[::1]"].includes(
      new URL(apiUrl).hostname,
    );
  } catch {
    return false;
  }
}

export function validateJobLimit(value: string | number): number {
  const limit = Number(value);
  if (!Number.isInteger(limit) || limit < 1 || limit > 1000)
    throw new Error("Choose a whole number between 1 and 1,000.");
  return limit;
}

// Cache identity includes credentials and query scope, without storing either in its key.
export function connectionScope(connection: ConnectionSettings): string {
  return createHash("sha256")
    .update(
      JSON.stringify([
        connection.id,
        normalizeApiUrl(connection.apiUrl),
        connection.apiKey || "",
        connection.historyWindow,
        connection.jobLimit,
      ]),
    )
    .digest("hex");
}

export function connectionLabel(
  connection: Pick<ConnectionSettings, "name" | "apiUrl">,
): string {
  return connection.name || new URL(connection.apiUrl).host;
}
