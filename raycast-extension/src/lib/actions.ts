import { Alert, Toast, confirmAlert, showToast } from "@raycast/api";
import { SsyncClient } from "../api/client";
import type { ConnectionSettings, JobInfo } from "../types/ssync";

export async function cancelJob(
  connection: ConnectionSettings,
  job: JobInfo,
): Promise<boolean> {
  if (
    !(await confirmAlert({
      title: "Cancel job " + job.job_id + "?",
      message:
        (job.name || "This job") +
        " on " +
        job.hostname +
        " will be cancelled.",
      primaryAction: {
        title: "Cancel Job",
        style: Alert.ActionStyle.Destructive,
      },
    }))
  )
    return false;
  const toast = await showToast({
    style: Toast.Style.Animated,
    title: "Cancelling job",
    message: job.job_id + " · " + job.hostname,
  });
  try {
    await new SsyncClient(connection).cancelJob(job);
    toast.style = Toast.Style.Success;
    toast.title = "Job cancelled";
    return true;
  } catch (error) {
    toast.style = Toast.Style.Failure;
    toast.title = "Job could not be cancelled";
    toast.message = error instanceof Error ? error.message : String(error);
    return false;
  }
}
