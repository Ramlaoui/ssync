import Foundation

/// A labelled value shown in job detail. Empty or placeholder scheduler values are dropped.
struct JobFact: Hashable, Sendable, Identifiable {
  var label: String
  var value: String
  var monospaced = false
  var id: String { label }
}

/// The job's queue standing, when the server has ranked it among pending jobs.
struct QueuePosition: Hashable, Sendable {
  var rank: Int
  var ahead: Int
  var size: Int
  var partition: String
}

extension Job {
  /// Scheduler placeholders that mean "no value".
  private static let placeholders: Set<String> = [
    "", "none", "unknown", "n/a", "(null)", "null", "invalid", "0:0:0",
  ]
  func value(_ key: String) -> String? {
    let raw = fields.text(key).trimmingCharacters(in: .whitespacesAndNewlines)
    return Self.placeholders.contains(raw.lowercased()) ? nil : raw
  }
  private func facts(_ pairs: [(String, String?)], monospaced: Set<String> = []) -> [JobFact] {
    pairs.compactMap { label, value in
      guard let value, !value.isEmpty else { return nil }
      return JobFact(label: label, value: value, monospaced: monospaced.contains(label))
    }
  }

  var submitted: Date? { value("submit_time").flatMap(Format.date) }
  var started: Date? { value("start_time").flatMap(Format.date) }
  var ended: Date? { value("end_time").flatMap(Format.date) }
  var exitCode: String? { value("exit_code") }
  var succeeded: Bool { exitCode.map { $0 == "0" || $0 == "0:0" } ?? (state == .completed) }

  var queuePosition: QueuePosition? {
    guard let rank = value("priority_rank").flatMap(Int.init),
      let size = value("priority_queue_size").flatMap(Int.init)
    else { return nil }
    return QueuePosition(
      rank: rank, ahead: value("priority_jobs_ahead").flatMap(Int.init) ?? max(0, rank - 1),
      size: size, partition: partition)
  }

  /// When things happened, including how long the job waited and how long it has left.
  func timeline(now: Date = .now) -> [JobFact] {
    var waited: String?
    if let submitted, let started, started >= submitted {
      waited = Format.span(started.timeIntervalSince(submitted))
    } else if let submitted, state == .pending {
      waited = Format.span(now.timeIntervalSince(submitted)) + " so far"
    }
    var remaining: String?
    if state == .running, let elapsed = Format.seconds(runtime),
      let total = Format.seconds(limit), total > elapsed
    {
      remaining = Format.span(total - elapsed)
    }
    return facts([
      ("Submitted", submitted.map(Format.moment) ?? value("submit_time")),
      ("Waited", waited),
      ("Started", started.map(Format.moment) ?? (state == .pending ? nil : value("start_time"))),
      ("Ended", ended.map(Format.moment) ?? (state.active ? nil : value("end_time"))),
      ("Elapsed", value("runtime").map(Format.duration)),
      ("Time limit", value("time_limit").map(Format.duration)),
      ("Time left", remaining),
    ])
  }

  /// Priority standing for queued jobs.
  var queue: [JobFact] {
    var pairs: [(String, String?)] = [("Priority", value("priority"))]
    if let position = queuePosition {
      pairs += [
        ("Position", "\(position.rank) of \(position.size)"),
        ("Jobs ahead", "\(position.ahead)"),
      ]
      if let percentile = value("priority_percentile").flatMap(Double.init) {
        pairs.append(("Ahead of", "\(Int(percentile.rounded()))% of the queue"))
      }
      if let snapshot = value("priority_snapshot_at").flatMap(Format.date) {
        pairs.append(("Ranked", Format.age(snapshot).lowercased()))
      }
    }
    return facts(pairs)
  }

  var resources: [JobFact] {
    facts(
      [
        ("CPUs", value("cpus")), ("Memory", value("memory")), ("Nodes", value("nodes")),
        ("GRES", value("gres") ?? value("tres_per_node")),
        ("Requested", value("req_tres")), ("Allocated", value("alloc_tres")),
        ("Node list", value("node_list")), ("Batch host", value("batch_host")),
      ], monospaced: ["Requested", "Allocated", "Node list"])
  }

  /// Accounting figures, usually only present once the job has run.
  var usage: [JobFact] {
    facts([
      ("CPU time", value("cpu_time")), ("Total CPU", value("total_cpu")),
      ("User CPU", value("user_cpu")), ("System CPU", value("system_cpu")),
      ("Average CPU", value("ave_cpu")), ("Peak memory", value("max_rss")),
      ("Average memory", value("ave_rss")), ("Peak virtual memory", value("max_vmsize")),
      ("Disk read", value("max_disk_read")), ("Disk written", value("max_disk_write")),
      ("Energy", value("consumed_energy")),
    ])
  }

  var scheduling: [JobFact] {
    let array = value("array_task_id").map { task in
      "\(value("array_job_id") ?? "?")_\(task)"
    }
    return facts(
      [
        ("User", value("user")), ("Account", value("account")), ("QoS", value("qos")),
        ("Array task", array), ("Exit code", exitCode), ("Scheduler state", value("state")),
        ("Working directory", value("work_dir")), ("stdout", value("stdout_file")),
        ("stderr", value("stderr_file")), ("Submitted with", value("submit_line")),
      ], monospaced: ["Working directory", "stdout", "stderr", "Submitted with"])
  }
}

extension Format {
  /// A compact absolute time: "14:05" today, "Mon 14:05" this week, otherwise "Sep 3, 14:05".
  static func moment(_ date: Date) -> String {
    let calendar = Calendar.current
    if calendar.isDateInToday(date) {
      return date.formatted(date: .omitted, time: .shortened)
    }
    if let days = calendar.dateComponents([.day], from: date, to: .now).day, days < 7, days >= 0 {
      return date.formatted(.dateTime.weekday(.abbreviated).hour().minute())
    }
    return date.formatted(.dateTime.month(.abbreviated).day().hour().minute())
  }
  /// A duration in seconds as "2 h 5 m", "4 m", or "12 s".
  static func span(_ seconds: TimeInterval) -> String {
    let total = max(0, Int(seconds))
    if total >= 86400 { return "\(total / 86400) d \(total % 86400 / 3600) h" }
    if total >= 3600 { return "\(total / 3600) h \(total % 3600 / 60) m" }
    if total >= 60 { return "\(total / 60) m" }
    return "\(total) s"
  }
}
