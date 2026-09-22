import { describe, expect, it } from "vitest";
import {
  normalizeApiUrl,
  connectionScope,
  isLoopback,
  validateJobLimit,
} from "./connections";
import { jobKey, jobStatus, gpuCount, visibleJobs, togglePinned } from "./jobs";
import { parseHostDefaults } from "./hosts";
import { buildLaunchRequest, emptyDraft } from "./launch";
import { codeBlock } from "./markdown";
import { connection, job } from "../test/fixtures";
import { defaultWorkspace } from "../api/storage";

describe("connection identity", () => {
  it("normalizes URLs while retaining reverse proxy paths", () => {
    expect(normalizeApiUrl(" https://example.test/ssync/// ")).toBe(
      "https://example.test/ssync",
    );
    expect(isLoopback("https://localhost:8042")).toBe(true);
    expect(isLoopback("https://localhost.example.test")).toBe(false);
  });
  it.each([
    "ftp://host",
    "host:8042",
    "https://key:secret@host",
    "https://host/?key=secret",
    "https://host/#/jobs",
  ])("rejects invalid endpoint %s", (value) =>
    expect(() => normalizeApiUrl(value)).toThrow(),
  );
  it.each([0, -1, 1.5, 1001, "abc"])("rejects invalid job limit %s", (value) =>
    expect(() => validateJobLimit(value)).toThrow(),
  );
  it("separates snapshots by server, key, history, and limit", () => {
    const original = connectionScope(connection);
    for (const change of [
      { apiUrl: "https://other.test" },
      { apiKey: "different-test-key" },
      { historyWindow: "7d" },
      { jobLimit: 100 },
      { id: "other" },
    ]) {
      expect(connectionScope({ ...connection, ...change })).not.toBe(original);
    }
    expect(original).not.toContain(connection.apiKey);
  });
});

describe("job presentation", () => {
  it.each([
    ["RUNNING", "running", "running"],
    ["CG", "running", "running"],
    ["CONFIGURING", "pending", "warning"],
    ["CD", "historical", "success"],
    ["OUT_OF_MEMORY", "historical", "danger"],
    ["TIMEOUT+", "historical", "warning"],
  ])("handles %s", (state, category, tone) =>
    expect(jobStatus(state)).toMatchObject({ category, tone }),
  );
  it("filters attention without mixing hosts or identities", () => {
    const failed = { ...job, state: "F" },
      other = { ...job, hostname: "boreal", state: "F" };
    expect(
      visibleJobs([job, failed, other], {
        ...defaultWorkspace,
        host: "atlas",
        view: "attention",
      }),
    ).toEqual([failed]);
    const pins = togglePinned([], job);
    expect(pins).toEqual([jobKey(job)]);
    expect(
      visibleJobs([job, other], {
        ...defaultWorkspace,
        view: "pinned",
        pinnedJobs: pins,
      }),
    ).toEqual([job]);
    expect(togglePinned(pins, job)).toEqual([]);
  });
  it("does not double count typed and total GPU allocations", () => {
    expect(
      gpuCount({ ...job, alloc_tres: "cpu=8,gres/gpu=2,gres/gpu:a100=2" }),
    ).toBe(2);
    expect(gpuCount({ ...job, gres: "gpu:a100:2,gpu:h100:1" })).toBe(3);
    expect(gpuCount(job)).toBeUndefined();
  });
});

describe("reviewed changes", () => {
  it("preserves directives and script text while applying only explicit overrides", () => {
    const script =
      "#!/bin/bash\n#SBATCH --exclude=node07\n#SBATCH --array=1-8\npython train.py\n";
    const request = buildLaunchRequest({
      ...emptyDraft,
      host: "atlas",
      script,
      sourceDir: " /work/project ",
      cpus: "8",
      gpus: "0",
    });
    expect(request).toMatchObject({
      script_content: script,
      host: "atlas",
      source_dir: "/work/project",
      cpus: 8,
      gpus_per_node: 0,
    });
    expect(request).not.toHaveProperty("partition");
    expect(request).not.toHaveProperty("mem");
  });
  it("requires an explicit script-only choice to omit source synchronization", () => {
    const draft = { ...emptyDraft, host: "atlas", script: "echo ready" };
    expect(() => buildLaunchRequest(draft)).toThrow("source directory");
    expect(buildLaunchRequest({ ...draft, sync: false })).not.toHaveProperty(
      "source_dir",
    );
  });
  it("rejects fractional resources instead of silently changing them", () => {
    expect(() =>
      buildLaunchRequest({
        ...emptyDraft,
        host: "atlas",
        script: "echo ready",
        sync: false,
        cpus: "1.5",
      }),
    ).toThrow("whole number");
  });
  it("clears host defaults explicitly and accepts zero GPUs", () => {
    expect(
      parseHostDefaults({ cpus: "8", gpus_per_node: "0", account: "" }),
    ).toMatchObject({ cpus: 8, gpus_per_node: 0, account: null });
    expect(() => parseHostDefaults({ mem: "-1" })).toThrow();
  });
  it("keeps untrusted output inside a code fence", () => {
    const content = "~~~\n# Not a heading\n~~~~";
    const markdown = codeBlock(content);
    expect(markdown.startsWith("~~~~~\n")).toBe(true);
    expect(markdown.endsWith("\n~~~~~")).toBe(true);
  });
});
