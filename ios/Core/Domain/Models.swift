import Foundation

// Transport records retain the server's snake_case field names so their Codable
// representation can be compared directly with the Python API schema.

struct JobID: Codable, Hashable, Sendable, Identifiable {
  var host: String
  var number: String
  var id: String { "\(host)::\(number)" }
}

enum JobState: String, CaseIterable, Sendable {
  case running, pending, completed, failed, cancelled, timedOut, unknown
  init(_ raw: String) {
    switch raw.uppercased().split(separator: "+").first.map(String.init) ?? "" {
    case "R", "RUNNING", "CG", "COMPLETING": self = .running
    case "PD", "PENDING", "CF", "CONFIGURING": self = .pending
    case "CD", "COMPLETED": self = .completed
    case "F", "FAILED", "NF", "NODE_FAIL", "OOM", "OUT_OF_MEMORY", "BF", "BOOT_FAIL": self = .failed
    case "CA", "CANCELLED", "CANCELED": self = .cancelled
    case "TO", "TIMEOUT", "DEADLINE": self = .timedOut
    default: self = .unknown
    }
  }
  var label: String {
    switch self {
    case .timedOut: "Timed out"
    default: rawValue.capitalized
    }
  }
  var symbol: String {
    switch self {
    case .running: "play.circle.fill"
    case .pending: "clock"
    case .completed: "checkmark.circle.fill"
    case .failed: "exclamationmark.circle.fill"
    case .cancelled: "xmark.circle"
    case .timedOut: "hourglass"
    case .unknown: "questionmark.circle"
    }
  }
  var active: Bool { self == .running || self == .pending }
  var needsAttention: Bool { self == .failed || self == .timedOut }
  var order: Int { Self.allCases.firstIndex(of: self) ?? 6 }
}

struct Job: Codable, Hashable, Sendable, Identifiable {
  var fields: [String: JSONValue]
  init(_ fields: [String: JSONValue]) { self.fields = fields }
  init(from decoder: any Decoder) throws { fields = try [String: JSONValue](from: decoder) }
  func encode(to encoder: any Encoder) throws { try fields.encode(to: encoder) }
  var id: JobID { JobID(host: host, number: number) }
  var host: String { fields.text("hostname") }
  var number: String { fields.text("job_id") }
  var name: String { fields.text("name", fallback: "Job \(number)") }
  var rawState: String { fields.text("state", fallback: "UNKNOWN") }
  var state: JobState { JobState(rawState) }
  var partition: String { fields.text("partition") }
  var user: String { fields.text("user") }
  var runtime: String { fields.text("runtime") }
  var limit: String { fields.text("time_limit") }
  var cached: Bool { fields.flag("cached") }
  var stale: Bool { fields.flag("stale") }
  var arrayParent: String? {
    let value = fields.text("array_job_id")
    return value.isEmpty || value == number ? nil : value
  }
  var subtitle: String {
    if state == .pending { return fields.text("reason", fallback: "Waiting for scheduling") }
    return [
      runtime.isEmpty ? nil : "\(Format.duration(runtime)) elapsed",
      partition.isEmpty ? nil : partition,
    ].compactMap { $0 }.joined(separator: " · ")
  }
  var timeFraction: Double? {
    guard let elapsed = Format.seconds(runtime), let total = Format.seconds(limit), total > 0 else {
      return nil
    }
    return min(max(elapsed / total, 0), 1)
  }
}

struct Host: Codable, Identifiable, Hashable, Sendable {
  var hostname: String
  var slurm_defaults: [String: JSONValue]?
  var id: String { hostname }
}

struct JobStatusResponse: Codable, Sendable {
  var hostname: String
  var jobs: [Job]
  var total_jobs: Int?
  var query_time: String?
  var cached: Bool?
  var error: String?
  var array_groups: [ArrayGroup]?
  var allJobs: [Job] {
    var qualified: [JobID: Job] = [:]
    for var job in jobs + (array_groups ?? []).flatMap(\.tasks) {
      job.fields["hostname"] = .string(hostname)
      qualified[job.id] = job
    }
    return Array(qualified.values)
  }
}

struct ArrayGroup: Codable, Identifiable, Sendable {
  var array_job_id: String
  var hostname: String
  var job_name: String
  var total_tasks: Int
  var tasks: [Job]
  var pending_count: Int
  var running_count: Int
  var completed_count: Int
  var failed_count: Int
  var cancelled_count: Int
  var id: JobID { JobID(host: hostname, number: array_job_id) }
}

struct PartitionSnapshot: Codable, Sendable, Identifiable {
  var hostname: String
  var partitions: [Partition]
  var updated_at: String?
  var cached: Bool?
  var stale: Bool?
  var cache_age_seconds: Double?
  var error: String?
  var id: String { hostname }
  var observedAt: Date? { updated_at.flatMap(Format.date) }
}

struct Partition: Codable, Hashable, Sendable, Identifiable {
  var partition: String
  var availability: String?
  var states: [String]
  var nodes_total: Int
  var cpus_alloc: Int
  var cpus_idle: Int
  var cpus_other: Int
  var cpus_total: Int
  var gpus_total: Int?
  var gpus_used: Int?
  var gpus_idle: Int?
  var gpu_types: [String: GPUType]?
  var id: String { partition }
  var hasGPUs: Bool { (gpus_total ?? 0) > 0 }
  struct GPUType: Codable, Hashable, Sendable {
    var total: Int
    var used: Int
  }
}

struct Watcher: Codable, Hashable, Sendable, Identifiable {
  var fields: [String: JSONValue]
  init(_ fields: [String: JSONValue]) { self.fields = fields }
  init(from decoder: any Decoder) throws { fields = try [String: JSONValue](from: decoder) }
  func encode(to encoder: any Encoder) throws { try fields.encode(to: encoder) }
  var id: Int { fields.integer("id") }
  var name: String { fields.text("name", fallback: "Watcher \(id)") }
  var host: String { fields.text("hostname") }
  var jobID: JobID { JobID(host: host, number: fields.text("job_id")) }
  var state: String { fields.text("state", fallback: "unknown") }
  var actions: [JSONValue] { fields["actions"]?.array ?? [] }
  var trigger: String {
    if fields.flag("trigger_on_job_end") {
      let states =
        fields["trigger_job_states"]?.array.compactMap(\.string).joined(separator: ", ")
        ?? "terminal state"
      return "Job ends: \(states)"
    }
    return fields.text("pattern", fallback: "Manual trigger")
  }
  var actionSummary: String {
    actions.map { $0.object.text("type").replacingOccurrences(of: "_", with: " ") }.joined(
      separator: ", ")
  }
}
struct WatchersResponse: Codable, Sendable {
  var watchers: [Watcher]
  var count: Int?
}
struct WatcherEvent: Codable, Hashable, Sendable, Identifiable {
  var id: Int
  var watcher_id: Int
  var hostname: String
  var job_id: String
  var timestamp: String
  var matched_text: String?
  var captured_vars: [String: JSONValue]?
  var action_type: String
  var action_result: String?
  var success: Bool
}
struct WatcherEventsResponse: Codable, Sendable { var events: [WatcherEvent] }

struct OutputResponse: Codable, Sendable {
  var stdout: String?
  var stderr: String?
  var content_truncated: Bool?
  var cached: Bool?
  var stale: Bool?
  var stdout_metadata: [String: JSONValue]?
  var stderr_metadata: [String: JSONValue]?
}

struct Connection: Codable, Identifiable, Hashable, Sendable {
  var id = UUID()
  var name: String
  var baseURL: String
  var demo = false
  static let demoID = UUID(uuidString: "00000000-0000-0000-0000-000000000001")!
  static let sample = Connection(id: demoID, name: "Research workstation", baseURL: "", demo: true)
}

enum Format {
  static func seconds(_ value: String) -> Double? {
    let parts = value.split(separator: "-", maxSplits: 1, omittingEmptySubsequences: false)
    guard !parts.isEmpty else { return nil }
    let days: Double
    let time: Substring
    if parts.count == 2 {
      guard let d = Double(parts[0]), d >= 0, d.isFinite else { return nil }
      days = d
      time = parts[1]
    } else {
      days = 0
      time = parts[0]
    }
    let pieces = time.split(separator: ":")
    let numbers = pieces.compactMap { Double($0) }
    guard numbers.count == pieces.count, (1...3).contains(numbers.count),
      numbers.allSatisfy({ $0 >= 0 && $0.isFinite })
    else { return nil }
    let result =
      days * 86400
      + numbers.reversed().enumerated().reduce(0) { $0 + $1.element * pow(60, Double($1.offset)) }
    return result.isFinite && result < Double(Int.max) ? result : nil
  }
  static func duration(_ raw: String) -> String {
    guard let value = seconds(raw) else { return raw.isEmpty ? "Unavailable" : raw }
    let minutes = Int(value / 60)
    if minutes >= 60 { return "\(minutes / 60) h \(minutes % 60) m" }
    if minutes > 0 { return "\(minutes) m" }
    return "\(Int(value)) s"
  }
  static func date(_ value: String) -> Date? {
    if let d = try? Date(value, strategy: .iso8601) { return d }
    let fractional = ISO8601DateFormatter()
    fractional.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
    if let d = fractional.date(from: value) { return d }
    let f = DateFormatter()
    f.locale = Locale(identifier: "en_US_POSIX")
    f.timeZone = .gmt
    f.dateFormat = "yyyy-MM-dd'T'HH:mm:ss"
    return f.date(from: value)
  }
  static func age(_ date: Date?, now: Date = .now) -> String {
    guard let date else { return "Not updated" }
    let seconds = max(0, Int(now.timeIntervalSince(date)))
    if seconds < 10 { return "Just now" }
    if seconds < 60 { return "\(seconds) s ago" }
    if seconds < 3600 { return "\(seconds / 60) min ago" }
    if seconds < 86400 { return "\(seconds / 3600) h ago" }
    return "\(seconds / 86400) d ago"
  }
}
