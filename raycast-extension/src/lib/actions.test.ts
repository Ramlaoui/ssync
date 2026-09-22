import { afterEach, expect, it, vi } from "vitest";
import { SsyncClient } from "../api/client";
import { confirmAlert } from "../test/raycast";
import { connection, job } from "../test/fixtures";
import { cancelJob } from "./actions";
afterEach(() => vi.restoreAllMocks());
it("does not cancel when confirmation is dismissed", async () => {
  confirmAlert.mockResolvedValueOnce(false);
  const cancel = vi.spyOn(SsyncClient.prototype, "cancelJob");
  expect(await cancelJob(connection, job)).toBe(false);
  expect(cancel).not.toHaveBeenCalled();
});
it("confirms the target host and reports a failed cancellation accurately", async () => {
  const cancel = vi
    .spyOn(SsyncClient.prototype, "cancelJob")
    .mockRejectedValue(new Error("Rejected"));
  expect(await cancelJob(connection, job)).toBe(false);
  expect(confirmAlert).toHaveBeenLastCalledWith(
    expect.objectContaining({ message: expect.stringContaining("atlas") }),
  );
  expect(cancel).toHaveBeenCalledWith(job);
});
