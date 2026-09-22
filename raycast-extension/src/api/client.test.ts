import { beforeEach, describe, expect, it, vi } from "vitest";
import { connection, job } from "../test/fixtures";
import { SsyncClient } from "./client";

const wire = vi.hoisted(() => ({
  requests: [] as Array<{
    url: string;
    options: Record<string, unknown>;
    body: string;
  }>,
  status: 200,
  body: {} as unknown,
}));
vi.mock("node:https", async () => {
  const { EventEmitter } = await import("node:events");
  return {
    default: {
      request: (
        url: URL,
        options: Record<string, unknown>,
        callback: (response: InstanceType<typeof EventEmitter>) => void,
      ) => {
        const entry = { url: url.toString(), options, body: "" };
        wire.requests.push(entry);
        const request = new EventEmitter() as InstanceType<
          typeof EventEmitter
        > & {
          write: (data: string) => void;
          end: () => void;
          destroy: (error: Error) => void;
        };
        request.write = (data) => {
          entry.body += data;
        };
        request.destroy = (error) => {
          request.emit("error", error);
        };
        request.end = () =>
          queueMicrotask(() => {
            const response = Object.assign(new EventEmitter(), {
              statusCode: wire.status,
              headers: {},
            });
            callback(response);
            response.emit("data", Buffer.from(JSON.stringify(wire.body)));
            response.emit("end");
          });
        return request;
      },
    },
  };
});
beforeEach(() => {
  wire.requests.length = 0;
  wire.status = 200;
  wire.body = {};
});
describe("API wire contracts", () => {
  it("keeps the API prefix and scoped status query", async () => {
    wire.body = [];
    await new SsyncClient({
      ...connection,
      apiUrl: "https://api.test/ssync",
    }).getStatus({ since: "7d", limit: 100, forceRefresh: true });
    const request = wire.requests[0];
    const url = new URL(request.url);
    expect(url.pathname).toBe("/ssync/api/status");
    expect(Object.fromEntries(url.searchParams)).toEqual({
      since: "7d",
      limit: "100",
      group_array_jobs: "false",
      force_refresh: "true",
    });
    expect(request.options.headers).toMatchObject({
      "X-API-Key": connection.apiKey,
    });
  });
  it("verifies remote TLS and supports explicit self-signed connections", async () => {
    for (const profile of [
      { ...connection, apiUrl: "https://remote.test" },
      connection,
      { ...connection, apiUrl: "https://remote.test", allowSelfSigned: true },
    ])
      await new SsyncClient(profile).testConnection();
    expect(
      wire.requests.map((request) => request.options.rejectUnauthorized),
    ).toEqual([true, false, false]);
  });
  it("filters job events by host as well as job ID", async () => {
    wire.body = {
      count: 3,
      events: [
        { id: 1, job_id: job.job_id, hostname: job.hostname },
        { id: 2, job_id: job.job_id, hostname: "boreal" },
        { id: 3, job_id: "456", hostname: job.hostname },
      ],
    };
    const response = await new SsyncClient(connection).getWatcherEvents({
      job,
    });
    expect(response.events.map((event) => event.id)).toEqual([1]);
  });
  it("sends the host revision and preserves the selected target", async () => {
    await new SsyncClient(connection).updateHostSettings("atlas", {
      revision: "a".repeat(64),
      slurm_defaults: { account: "project", cpus: 8 },
    });
    expect(new URL(wire.requests[0].url).pathname).toBe(
      "/api/hosts/atlas/settings",
    );
    expect(wire.requests[0].options.method).toBe("PUT");
    expect(JSON.parse(wire.requests[0].body)).toEqual({
      revision: "a".repeat(64),
      slurm_defaults: { account: "project", cpus: 8 },
    });
  });
  it("cancels only the requested job on its host", async () => {
    await new SsyncClient(connection).cancelJob(job);
    expect(new URL(wire.requests[0].url).pathname).toBe("/api/jobs/123/cancel");
    expect(new URL(wire.requests[0].url).searchParams.get("host")).toBe(
      "atlas",
    );
    expect(wire.requests[0].options.method).toBe("POST");
  });
  it("surfaces authentication failures and does not follow redirects with a key", async () => {
    wire.status = 401;
    wire.body = { detail: "Invalid API key" };
    await expect(
      new SsyncClient(connection).testConnection(),
    ).rejects.toMatchObject({ statusCode: 401 });
    wire.status = 302;
    await expect(
      new SsyncClient(connection).testConnection(),
    ).rejects.toMatchObject({ statusCode: 302 });
    expect(wire.requests).toHaveLength(2);
  });
});
