import Foundation

enum DemoData {
  static let hosts = [
    Host(hostname: "Atlas", slurm_defaults: ["partition": .string("gpu-a100")]),
    Host(hostname: "Boreal", slurm_defaults: ["partition": .string("cpu")]),
  ]
  static func job(
    _ number: String, name: String, host: String = "Atlas", state: String = "R",
    partition: String = "gpu-a100", runtime: String = "02:18:00"
  ) -> Job {
    Job([
      "job_id": .string(number), "hostname": .string(host), "name": .string(name),
      "state": .string(state), "partition": .string(partition), "runtime": .string(runtime),
      "time_limit": .string("08:00:00"), "cpus": .string("32"), "memory": .string("128G"),
      "nodes": .string("1"), "user": .string("alex"), "reason": .string("Resources"),
      "alloc_tres": .string("cpu=32,mem=128G,gres/gpu=4"),
      "work_dir": .string("/scratch/alex/folding"),
      "stdout_file": .string("/scratch/alex/folding/slurm-\(number).out"),
      "stderr_file": .string("/scratch/alex/folding/slurm-\(number).err"),
      "start_time": .string(Date.now.addingTimeInterval(-8280).ISO8601Format()),
    ])
  }
  static var jobs: [Job] {
    [
      job("48192", name: "protein-fold-v3"),
      job("48194", name: "structure-refinement", runtime: "00:46:00"),
      job("48196", name: "embedding-sweep", state: "PD", runtime: "00:00:00"),
      job("48198", name: "sequence-design", state: "PD", runtime: "00:00:00"),
      job("82013", name: "eval-baseline", host: "Boreal", partition: "cpu", runtime: "00:12:00"),
      job("47981", name: "protein-fold-v2", state: "CD", runtime: "05:32:00"),
      job(
        "47990", name: "dataset-validation", host: "Boreal", state: "F", partition: "cpu",
        runtime: "00:03:12"),
    ]
  }
  static var partitions: [PartitionSnapshot] {
    [
      PartitionSnapshot(
        hostname: "Atlas",
        partitions: [
          Partition(
            partition: "gpu-a100", availability: "up", states: ["mixed"], nodes_total: 8,
            cpus_alloc: 192, cpus_idle: 64, cpus_other: 0, cpus_total: 256, gpus_total: 32,
            gpus_used: 24, gpus_idle: 8, gpu_types: ["A100": .init(total: 32, used: 24)]),
          Partition(
            partition: "compute", availability: "up", states: ["mixed", "drained"], nodes_total: 16,
            cpus_alloc: 192, cpus_idle: 48, cpus_other: 16, cpus_total: 256),
        ], updated_at: Date.now.addingTimeInterval(-40).ISO8601Format()),
      PartitionSnapshot(
        hostname: "Boreal",
        partitions: [
          Partition(
            partition: "cpu", availability: "up", states: ["mixed"], nodes_total: 8, cpus_alloc: 64,
            cpus_idle: 64, cpus_other: 0, cpus_total: 128)
        ], updated_at: Date.now.addingTimeInterval(-60).ISO8601Format()),
    ]
  }
  static let watchers = [
    Watcher([
      "id": .number(1), "name": .string("Resume from checkpoint"), "hostname": .string("Atlas"),
      "job_id": .string("48192"), "job_name": .string("protein-fold-v3"),
      "state": .string("active"), "pattern": .string("checkpoint saved: (.+)"),
      "captures": .array([.string("resume_run_dir")]), "trigger_on_job_end": .bool(true),
      "trigger_job_states": .array([.string("timeout")]), "interval_seconds": .number(60),
      "trigger_count": .number(0),
      "actions": .array([.object(["type": .string("resubmit"), "params": .object([:])])]),
    ]),
    Watcher([
      "id": .number(2), "name": .string("Stop on invalid loss"), "hostname": .string("Atlas"),
      "job_id": .string("48196"), "state": .string("active"), "pattern": .string("loss: nan"),
      "interval_seconds": .number(30), "trigger_count": .number(0),
      "actions": .array([.object(["type": .string("cancel_job"), "params": .object([:])])]),
    ]),
  ]
  static func output(_ source: String) -> String {
    if source == "stderr" {
      return
        "09:35:01 WARNING: Using default precision.\n09:36:22 WARNING: Data loader has fewer workers than CPUs.\n"
    }
    return (1...160).map { i in
      if i % 40 == 0 {
        return "09:\(String(format: "%02d", 35+i/40)):35 checkpoint saved: epoch-\(20+i/40).ckpt"
      }
      return "step \(1100+i)  loss \(String(format: "%.4f", 0.4-Double(i)/1500))"
    }.joined(separator: "\n")
  }
  static func events(_ id: Int) -> [WatcherEvent] {
    [
      .init(
        id: 1, watcher_id: id, hostname: "Atlas", job_id: "48192",
        timestamp: Date.now.addingTimeInterval(-120).ISO8601Format(),
        matched_text: "checkpoint saved: epoch-24.ckpt",
        captured_vars: ["resume_run_dir": .string("epoch-24.ckpt")], action_type: "log_event",
        action_result: "Checkpoint captured; waiting for job end.", success: true)
    ]
  }
}
