import { describe, expect, it } from "vitest";
import { credentials, LocalStorage, storage } from "../test/raycast";
import { connection } from "../test/fixtures";
import {
  clearJobCache,
  getConnection,
  getConnections,
  getJobCache,
  removeConnection,
  saveConnection,
  saveJobCache,
  setActiveConnection,
  saveWorkspace,
  getWorkspace,
  defaultWorkspace,
} from "./storage";

describe("saved connections", () => {
  it("migrates the old connection without leaving its key in LocalStorage", async () => {
    storage.set(
      "ssync.connection.v1",
      JSON.stringify({
        apiUrl: connection.apiUrl,
        apiKey: "migration-test-key",
        historyWindow: "7d",
        jobLimit: 25,
      }),
    );
    storage.set(
      "ssync.jobs.cache.v1",
      JSON.stringify({ loadedAt: 1, responses: [] }),
    );
    const restored = await getConnection();
    expect(restored).toMatchObject({
      id: "legacy",
      apiKey: "migration-test-key",
      historyWindow: "7d",
      jobLimit: 25,
    });
    expect(JSON.stringify(Object.fromEntries(storage))).not.toContain(
      "migration-test-key",
    );
    expect(storage.has("ssync.jobs.cache.v1")).toBe(false);
  });
  it("migrates a credential already kept in the encrypted store", async () => {
    storage.set(
      "ssync.connection.v1",
      JSON.stringify({ apiUrl: connection.apiUrl }),
    );
    credentials.set("ssync-api-key", { accessToken: "encrypted-test-key" });
    expect(await getConnection()).toMatchObject({
      apiKey: "encrypted-test-key",
    });
    expect(credentials.has("ssync-api-key")).toBe(false);
  });
  it("keeps each connection's API key separate when switching", async () => {
    const first = await saveConnection(connection);
    const second = await saveConnection({
      ...connection,
      id: "other",
      apiUrl: "https://other.test",
      apiKey: "other-test-key",
    });
    expect((await getConnection())?.id).toBe(first.id);
    await setActiveConnection(second.id);
    expect(await getConnection()).toMatchObject({
      id: "other",
      apiKey: "other-test-key",
    });
    expect(await getConnection(first.id)).toMatchObject({
      apiKey: connection.apiKey,
    });
    expect(JSON.stringify(Object.fromEntries(storage))).not.toContain(
      "test-key",
    );
  });
  it("does not replace the old credential if publishing the edited profile fails", async () => {
    await saveConnection(connection);
    LocalStorage.setItem.mockRejectedValueOnce(
      new Error("Storage unavailable"),
    );
    await expect(
      saveConnection({
        ...connection,
        apiUrl: "https://replacement.test",
        apiKey: "replacement-test-key",
      }),
    ).rejects.toThrow();
    expect(await getConnection()).toMatchObject({
      apiUrl: connection.apiUrl,
      apiKey: connection.apiKey,
    });
    expect(
      [...credentials.values()].some(
        (value) => value.accessToken === "replacement-test-key",
      ),
    ).toBe(false);
  });
  it("can clear an API key and remove one profile without harming another", async () => {
    await saveConnection(connection);
    await saveConnection({
      ...connection,
      id: "other",
      apiKey: "other-test-key",
    });
    await saveConnection({ ...connection, apiKey: "" });
    expect((await getConnection(connection.id))?.apiKey).toBe("");
    await removeConnection(connection.id);
    expect(await getConnections()).toMatchObject({ activeId: "other" });
    expect((await getConnection())?.apiKey).toBe("other-test-key");
  });
  it("uses scoped caches, including credential and history changes", async () => {
    const cache = { loadedAt: Date.now(), responses: [] };
    await saveJobCache(connection, cache);
    expect(await getJobCache(connection)).toEqual(cache);
    expect(
      await getJobCache({ ...connection, apiKey: "different" }),
    ).toBeUndefined();
    expect(
      await getJobCache({ ...connection, historyWindow: "30d" }),
    ).toBeUndefined();
    await saveJobCache({ ...connection, id: "other" }, cache);
    await clearJobCache(connection.id);
    expect(await getJobCache(connection)).toBeUndefined();
    expect(await getJobCache({ ...connection, id: "other" })).toEqual(cache);
  });
  it("updates the default host filter without dropping pins", async () => {
    await saveConnection(connection);
    await saveWorkspace(connection, {
      ...defaultWorkspace,
      pinnedJobs: ["pin"],
    });
    const updated = await saveConnection({
      ...connection,
      defaultHost: "boreal",
    });
    expect(await getWorkspace(updated)).toMatchObject({
      host: "boreal",
      pinnedJobs: ["pin"],
    });
  });
  it("discards workspace identities when a profile changes API server", async () => {
    await saveConnection(connection);
    await saveWorkspace(connection, {
      ...defaultWorkspace,
      pinnedJobs: ["old-server-job"],
    });
    const updated = await saveConnection({
      ...connection,
      apiUrl: "https://other.test",
    });
    expect((await getWorkspace(updated)).pinnedJobs).toEqual([]);
  });
});
