import { createElement } from "react";
import { act, create, type ReactTestRenderer } from "react-test-renderer";
import { afterEach, expect, it, vi } from "vitest";
import { SsyncClient } from "../api/client";
import * as storage from "../api/storage";
import { connection, job } from "../test/fixtures";
import type {
  ConnectionSettings,
  JobCache,
  JobStatusResponse,
} from "../types/ssync";
import { useJobs } from "./useJobs";
let tree: ReactTestRenderer;
afterEach(async () => {
  if (tree) await act(async () => tree.unmount());
  vi.restoreAllMocks();
});
function Probe({ settings = connection }: { settings?: ConnectionSettings }) {
  return createElement("div", useJobs(settings));
}
const responses: JobStatusResponse[] = [
  { hostname: job.hostname, jobs: [job], total_jobs: 1, query_time: "now" },
];
it("does not let a slow disk read replace a newer manual refresh", async () => {
  let finishCache!: (cache: JobCache) => void;
  vi.spyOn(storage, "getJobCache").mockImplementation(
    () =>
      new Promise((resolve) => {
        finishCache = resolve;
      }),
  );
  const status = vi
    .spyOn(SsyncClient.prototype, "getStatus")
    .mockResolvedValue(responses);
  await act(async () => {
    tree = create(<Probe />);
  });
  await act(async () => {
    await tree.root.findByType("div").props.refresh(true);
  });
  await act(async () => {
    finishCache({ loadedAt: Date.now(), responses: [] });
  });
  expect(tree.root.findByType("div").props.cache.responses).toEqual(responses);
  expect(status).toHaveBeenCalledTimes(1);
  expect(status).toHaveBeenCalledWith(
    expect.objectContaining({ forceRefresh: true }),
  );
});
it("discards a request when switching connections", async () => {
  vi.spyOn(storage, "getJobCache").mockResolvedValue(undefined);
  let finishFirst!: (value: JobStatusResponse[]) => void;
  const status = vi
    .spyOn(SsyncClient.prototype, "getStatus")
    .mockImplementationOnce(
      () =>
        new Promise((resolve) => {
          finishFirst = resolve;
        }),
    )
    .mockResolvedValueOnce([]);
  await act(async () => {
    tree = create(<Probe />);
  });
  await act(async () => {
    tree.update(<Probe settings={{ ...connection, id: "other" }} />);
  });
  await act(async () => {
    finishFirst(responses);
  });
  expect(status).toHaveBeenCalledTimes(2);
  expect(tree.root.findByType("div").props.cache.responses).toEqual([]);
});
