import { act, create, type ReactTestRenderer } from "react-test-renderer";
import { afterEach, expect, it, vi } from "vitest";
import { SsyncClient } from "../api/client";
import { connection, job } from "../test/fixtures";
import type { JobOutputResponse } from "../types/ssync";
import { OutputView } from "./OutputView";
let tree: ReactTestRenderer;
afterEach(async () => {
  if (tree) await act(async () => tree.unmount());
  vi.restoreAllMocks();
});
const output: JobOutputResponse = {
  job_id: job.job_id,
  hostname: job.hostname,
  output_type: "stdout",
  stdout: "Useful progress",
  stderr: null,
  stdout_metadata: null,
  stderr_metadata: null,
};
it("keeps useful output visible when a refresh fails", async () => {
  vi.spyOn(SsyncClient.prototype, "getOutput")
    .mockResolvedValueOnce(output)
    .mockRejectedValueOnce(new Error("Server offline"));
  await act(async () => {
    tree = create(<OutputView connection={connection} job={job} />);
  });
  await act(async () => {
    await tree.root.findByProps({ title: "Refresh Output" }).props.onAction();
  });
  const markdown = tree.root.findByProps({
    navigationTitle: "stdout · 123 · atlas",
  }).props.markdown;
  expect(markdown).toContain("Useful progress");
  expect(markdown).toContain("Refresh failed");
});
it("never renders a late stdout response over the selected stderr stream", async () => {
  let finish!: (value: JobOutputResponse) => void;
  const load = vi
    .spyOn(SsyncClient.prototype, "getOutput")
    .mockImplementationOnce(
      () =>
        new Promise((resolve) => {
          finish = resolve;
        }),
    )
    .mockResolvedValueOnce({
      ...output,
      output_type: "stderr",
      stdout: null,
      stderr: "Selected stderr",
    });
  await act(async () => {
    tree = create(<OutputView connection={connection} job={job} />);
  });
  expect(load).toHaveBeenCalledTimes(1);
  await act(async () => {
    tree.root.findByProps({ title: "Show stderr" }).props.onAction();
  });
  await act(async () => {
    finish(output);
  });
  const markdown = tree.root.findByProps({
    navigationTitle: "stderr · 123 · atlas",
  }).props.markdown;
  expect(markdown).toContain("Selected stderr");
  expect(markdown).not.toContain("Useful progress");
});
