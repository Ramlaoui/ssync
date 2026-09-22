import type { ConnectionSettings, JobInfo } from "../types/ssync";
export const connection: ConnectionSettings = {
  id: "test",
  name: "Test Connection",
  apiUrl: "https://localhost:8042",
  apiKey: "test-only-key",
  historyWindow: "3d",
  jobLimit: 50,
  updatedAt: 1,
};
export const job: JobInfo = {
  job_id: "123",
  hostname: "atlas",
  name: "Training",
  state: "R",
  cpus: "8",
  runtime: "00:20:00",
};
