import { act, create, type ReactTestRenderer } from "react-test-renderer";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { SsyncApiError, SsyncClient } from "../api/client";
import { connection } from "../test/fixtures";
import { LaunchReview } from "./LaunchView";
import type { LaunchRequest, LaunchResponse } from "../types/ssync";
const request: LaunchRequest = {
  host: "atlas",
  script_content: "echo ready",
  source_dir: "/work/project",
  exclude: [],
  include: [],
  no_gitignore: false,
};
let tree: ReactTestRenderer;
beforeEach(() => vi.restoreAllMocks());
afterEach(async () => {
  if (tree) await act(async () => tree.unmount());
});
it("submits only after explicit review and ignores repeated presses while submitting", async () => {
  let finish!: (response: LaunchResponse) => void;
  const launch = vi
    .spyOn(SsyncClient.prototype, "launchJob")
    .mockImplementation(
      () =>
        new Promise((resolve) => {
          finish = resolve;
        }),
    );
  vi.spyOn(SsyncClient.prototype, "getLaunchStatus").mockResolvedValue({
    launch_id: "launch-1",
    hostname: "atlas",
    stage: "submitted",
    terminal: true,
    success: true,
    job_id: "456",
    events: [],
  });
  await act(async () => {
    tree = create(<LaunchReview connection={connection} request={request} />);
  });
  expect(launch).not.toHaveBeenCalled();
  const action = tree.root.findByProps({ title: "Launch Job" }).props.onAction;
  let submitted: Promise<void>;
  await act(async () => {
    submitted = action();
    void action();
  });
  expect(launch).toHaveBeenCalledTimes(1);
  expect(launch).toHaveBeenCalledWith(request);
  await act(async () => {
    finish({
      success: true,
      launch_id: "launch-1",
      hostname: "atlas",
      message: "Accepted",
    });
    await submitted;
  });
  expect(tree.root.findAllByProps({ title: "Launch Job" })).toHaveLength(0);
});
it("does not expose an automatic retry after an ambiguous submission failure", async () => {
  const launch = vi
    .spyOn(SsyncClient.prototype, "launchJob")
    .mockRejectedValue(new Error("Connection interrupted"));
  await act(async () => {
    tree = create(<LaunchReview connection={connection} request={request} />);
  });
  await act(async () => {
    await tree.root.findByProps({ title: "Launch Job" }).props.onAction();
  });
  expect(launch).toHaveBeenCalledTimes(1);
  expect(tree.root.findAllByProps({ title: "Launch Job" })).toHaveLength(0);
  expect(
    tree.root.findByProps({ navigationTitle: "Review Launch" }).props.markdown,
  ).toContain("Submission status unknown");
});

it.each([200, 408, 500, 502])(
  "does not retry an ambiguous launch response with status %s",
  async (status) => {
    vi.spyOn(SsyncClient.prototype, "launchJob").mockRejectedValue(
      new SsyncApiError("Uncertain response", status),
    );
    await act(async () => {
      tree = create(<LaunchReview connection={connection} request={request} />);
    });
    await act(async () => {
      await tree.root.findByProps({ title: "Launch Job" }).props.onAction();
    });
    expect(tree.root.findAllByProps({ title: "Launch Job" })).toHaveLength(0);
    expect(
      tree.root.findByProps({ navigationTitle: "Review Launch" }).props
        .markdown,
    ).toContain("Submission status unknown");
  },
);
