import { act, create, type ReactTestRenderer } from "react-test-renderer";
import { afterEach, expect, it, vi } from "vitest";
import { SsyncClient } from "../api/client";
import { connection, job } from "../test/fixtures";
import { WatchersView } from "./WatchersView";
let tree: ReactTestRenderer;
afterEach(async () => {
  if (tree) await act(async () => tree.unmount());
  vi.restoreAllMocks();
});
it("creates a valid event watcher once, attached to the selected host and job", async () => {
  vi.spyOn(SsyncClient.prototype, "getWatchers").mockResolvedValue({
    job_id: job.job_id,
    watchers: [],
    count: 0,
  });
  vi.spyOn(SsyncClient.prototype, "getWatcherEvents").mockResolvedValue({
    events: [],
    count: 0,
  });
  let finish!: () => void;
  const createWatcher = vi
    .spyOn(SsyncClient.prototype, "createWatcher")
    .mockImplementation(
      () =>
        new Promise((resolve) => {
          finish = () =>
            resolve({
              id: 7,
              hostname: job.hostname,
              job_id: job.job_id,
              name: "Job result",
              pattern: "",
              interval_seconds: 30,
              captures: [],
              actions: [],
              state: "active",
              trigger_count: 0,
            });
        }),
    );
  await act(async () => {
    tree = create(<WatchersView connection={connection} job={job} />);
  });
  const target = tree.root.findAllByProps({ title: "Create Watcher" })[0].props
    .target;
  await act(async () => {
    tree.update(target);
  });
  const submit = tree.root.findByProps({ title: "Create Watcher" }).props
    .onSubmit;
  const values = {
    name: "Job result",
    pattern: "",
    intervalSeconds: "30",
    captures: "",
    condition: "",
    timerModeEnabled: false,
    timerIntervalSeconds: "30",
    triggerOnJobEnd: true,
    triggerJobStates: "CD, F",
    actionMessage: "Finished",
  };
  let pending: Promise<void>;
  await act(async () => {
    pending = submit(values);
    void submit(values);
  });
  expect(createWatcher).toHaveBeenCalledTimes(1);
  expect(createWatcher).toHaveBeenCalledWith(
    job,
    expect.objectContaining({
      actions: [{ type: "log_event", config: { message: "Finished" } }],
      trigger_on_job_end: true,
      trigger_job_states: ["CD", "F"],
    }),
  );
  await act(async () => {
    finish();
    await pending;
  });
});
