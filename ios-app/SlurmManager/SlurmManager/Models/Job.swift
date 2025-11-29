import Foundation

// MARK: - Job Models

struct Job: Codable, Identifiable, Hashable {
    let id: String
    let name: String
    let user: String
    let state: JobState
    let submitTime: Date?
    let startTime: Date?
    let endTime: Date?
    let partition: String?
    let nodes: String?
    let cpus: Int?
    let memory: String?
    let timeLimit: String?
    let workDir: String?
    let command: String?
    let array: String?
    let qos: String?
    let account: String?
    let host: String
    let cached: Bool

    // Additional fields from backend
    let runtime: String?
    let gpus: Int?
    let exitCode: Int?
    let reason: String?
    let arrayJobId: String?
    let arrayTaskId: String?

    enum CodingKeys: String, CodingKey {
        case id = "job_id"
        case name
        case user
        case state
        case submitTime = "submit_time"
        case startTime = "start_time"
        case endTime = "end_time"
        case partition
        case nodes
        case cpus
        case memory
        case timeLimit = "time_limit"
        case workDir = "work_dir"
        case command
        case array
        case qos
        case account
        case host = "hostname"
        case cached
        case runtime
        case gpus = "gpus_per_node"
        case exitCode = "exit_code"
        case reason
        case arrayJobId = "array_job_id"
        case arrayTaskId = "array_task_id"
    }

    // Custom decoder to handle missing fields and flexible state parsing
    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)

        id = try container.decode(String.self, forKey: .id)
        name = try container.decodeIfPresent(String.self, forKey: .name) ?? "Unknown"
        user = try container.decodeIfPresent(String.self, forKey: .user) ?? "Unknown"

        // Flexible state decoding
        if let stateStr = try container.decodeIfPresent(String.self, forKey: .state) {
            state = JobState(rawValue: stateStr) ?? .unknown
        } else {
            state = .unknown
        }

        // Date parsing with multiple formats
        submitTime = try Self.decodeDate(container: container, key: .submitTime)
        startTime = try Self.decodeDate(container: container, key: .startTime)
        endTime = try Self.decodeDate(container: container, key: .endTime)

        partition = try container.decodeIfPresent(String.self, forKey: .partition)
        nodes = try container.decodeIfPresent(String.self, forKey: .nodes)
        cpus = try container.decodeIfPresent(Int.self, forKey: .cpus)
        memory = try container.decodeIfPresent(String.self, forKey: .memory)
        timeLimit = try container.decodeIfPresent(String.self, forKey: .timeLimit)
        workDir = try container.decodeIfPresent(String.self, forKey: .workDir)
        command = try container.decodeIfPresent(String.self, forKey: .command)
        array = try container.decodeIfPresent(String.self, forKey: .array)
        qos = try container.decodeIfPresent(String.self, forKey: .qos)
        account = try container.decodeIfPresent(String.self, forKey: .account)
        host = try container.decodeIfPresent(String.self, forKey: .host) ?? "unknown"
        cached = try container.decodeIfPresent(Bool.self, forKey: .cached) ?? false
        runtime = try container.decodeIfPresent(String.self, forKey: .runtime)
        gpus = try container.decodeIfPresent(Int.self, forKey: .gpus)
        exitCode = try container.decodeIfPresent(Int.self, forKey: .exitCode)
        reason = try container.decodeIfPresent(String.self, forKey: .reason)
        arrayJobId = try container.decodeIfPresent(String.self, forKey: .arrayJobId)
        arrayTaskId = try container.decodeIfPresent(String.self, forKey: .arrayTaskId)
    }

    private static func decodeDate(container: KeyedDecodingContainer<CodingKeys>, key: CodingKeys) throws -> Date? {
        if let dateStr = try container.decodeIfPresent(String.self, forKey: key) {
            // Try ISO 8601 format first
            let iso8601 = ISO8601DateFormatter()
            iso8601.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
            if let date = iso8601.date(from: dateStr) {
                return date
            }

            // Try without fractional seconds
            iso8601.formatOptions = [.withInternetDateTime]
            if let date = iso8601.date(from: dateStr) {
                return date
            }

            // Try custom format
            let formatter = DateFormatter()
            formatter.dateFormat = "yyyy-MM-dd'T'HH:mm:ss"
            if let date = formatter.date(from: dateStr) {
                return date
            }
        }
        return nil
    }

    // Manual initializer for previews and testing
    init(
        id: String,
        name: String,
        user: String,
        state: JobState,
        submitTime: Date?,
        startTime: Date?,
        endTime: Date?,
        partition: String?,
        nodes: String?,
        cpus: Int?,
        memory: String?,
        timeLimit: String?,
        workDir: String?,
        command: String?,
        array: String?,
        qos: String?,
        account: String?,
        host: String,
        cached: Bool,
        runtime: String? = nil,
        gpus: Int? = nil,
        exitCode: Int? = nil,
        reason: String? = nil,
        arrayJobId: String? = nil,
        arrayTaskId: String? = nil
    ) {
        self.id = id
        self.name = name
        self.user = user
        self.state = state
        self.submitTime = submitTime
        self.startTime = startTime
        self.endTime = endTime
        self.partition = partition
        self.nodes = nodes
        self.cpus = cpus
        self.memory = memory
        self.timeLimit = timeLimit
        self.workDir = workDir
        self.command = command
        self.array = array
        self.qos = qos
        self.account = account
        self.host = host
        self.cached = cached
        self.runtime = runtime
        self.gpus = gpus
        self.exitCode = exitCode
        self.reason = reason
        self.arrayJobId = arrayJobId
        self.arrayTaskId = arrayTaskId
    }

    var isRunning: Bool {
        state == .running
    }

    var isPending: Bool {
        state == .pending
    }

    var isCompleted: Bool {
        state == .completed || state == .failed || state == .cancelled
    }

    var isTerminal: Bool {
        switch state {
        case .completed, .failed, .cancelled, .timeout, .nodeFailure, .outOfMemory, .bootFail, .deadline:
            return true
        default:
            return false
        }
    }

    var statusColor: String {
        switch state {
        case .running: return "blue"
        case .pending: return "orange"
        case .completed: return "green"
        case .failed: return "red"
        case .cancelled: return "gray"
        default: return "gray"
        }
    }

    var formattedDuration: String? {
        // First try runtime from server
        if let runtime = runtime, !runtime.isEmpty {
            return runtime
        }

        // Otherwise calculate
        guard let start = startTime else { return nil }
        let end = endTime ?? Date()
        let duration = end.timeIntervalSince(start)
        return formatDuration(duration)
    }

    private func formatDuration(_ duration: TimeInterval) -> String {
        let hours = Int(duration) / 3600
        let minutes = (Int(duration) % 3600) / 60
        let seconds = Int(duration) % 60

        if hours > 0 {
            return String(format: "%02d:%02d:%02d", hours, minutes, seconds)
        } else {
            return String(format: "%02d:%02d", minutes, seconds)
        }
    }
}

enum JobState: String, Codable, CaseIterable {
    case pending = "PENDING"
    case running = "RUNNING"
    case completed = "COMPLETED"
    case failed = "FAILED"
    case cancelled = "CANCELLED"
    case completing = "COMPLETING"
    case configuring = "CONFIGURING"
    case suspended = "SUSPENDED"
    case timeout = "TIMEOUT"
    case nodeFailure = "NODE_FAIL"
    case preempted = "PREEMPTED"
    case bootFail = "BOOT_FAIL"
    case deadline = "DEADLINE"
    case outOfMemory = "OUT_OF_MEMORY"
    case unknown = "UNKNOWN"

    // Handle short state codes from SLURM
    init(rawValue: String) {
        switch rawValue.uppercased() {
        case "PD", "PENDING": self = .pending
        case "R", "RUNNING": self = .running
        case "CD", "COMPLETED": self = .completed
        case "F", "FAILED": self = .failed
        case "CA", "CANCELLED": self = .cancelled
        case "CG", "COMPLETING": self = .completing
        case "CF", "CONFIGURING": self = .configuring
        case "S", "SUSPENDED": self = .suspended
        case "TO", "TIMEOUT": self = .timeout
        case "NF", "NODE_FAIL": self = .nodeFailure
        case "PR", "PREEMPTED": self = .preempted
        case "BF", "BOOT_FAIL": self = .bootFail
        case "DL", "DEADLINE": self = .deadline
        case "OOM", "OUT_OF_MEMORY": self = .outOfMemory
        default: self = .unknown
        }
    }

    var displayName: String {
        switch self {
        case .pending: return "Pending"
        case .running: return "Running"
        case .completed: return "Completed"
        case .failed: return "Failed"
        case .cancelled: return "Cancelled"
        case .completing: return "Completing"
        case .configuring: return "Configuring"
        case .suspended: return "Suspended"
        case .timeout: return "Timeout"
        case .nodeFailure: return "Node Failure"
        case .preempted: return "Preempted"
        case .bootFail: return "Boot Fail"
        case .deadline: return "Deadline"
        case .outOfMemory: return "Out of Memory"
        case .unknown: return "Unknown"
        }
    }
}

// MARK: - Job Detail

struct JobDetail: Codable {
    let job: Job?
    let script: String?
    let output: String?
    let error: String?
    let outputPath: String?
    let errorPath: String?
    let cached: Bool?

    enum CodingKeys: String, CodingKey {
        case job = "job_info"
        case script = "script_content"
        case output = "stdout"
        case error = "stderr"
        case outputPath = "stdout_metadata"
        case errorPath = "stderr_metadata"
        case cached = "cached_at"
    }
}

// MARK: - Job Output Response

struct JobOutputResponse: Codable {
    let output: String?
    let error: String?
    let jobId: String
    let host: String

    enum CodingKeys: String, CodingKey {
        case output = "stdout"
        case error = "stderr"
        case jobId = "job_id"
        case host = "hostname"
    }
}

// MARK: - Job Status Response

struct JobStatusResponse: Codable {
    let jobs: [Job]
    let total: Int?
    let page: Int?
    let pageSize: Int?
    let hosts: [String]
    let fromCache: Bool?
    let partialResults: Bool?
    let errors: [String: String]?
    let queryTime: Double?

    enum CodingKeys: String, CodingKey {
        case jobs
        case total = "total_jobs"
        case page
        case pageSize = "page_size"
        case hosts
        case fromCache = "cached"
        case partialResults = "partial_results"
        case errors
        case queryTime = "query_time"
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)

        // Handle nested jobs array or direct array
        if let jobsArray = try? container.decode([Job].self, forKey: .jobs) {
            jobs = jobsArray
        } else {
            jobs = []
        }

        total = try container.decodeIfPresent(Int.self, forKey: .total)
        page = try container.decodeIfPresent(Int.self, forKey: .page)
        pageSize = try container.decodeIfPresent(Int.self, forKey: .pageSize)
        hosts = try container.decodeIfPresent([String].self, forKey: .hosts) ?? []
        fromCache = try container.decodeIfPresent(Bool.self, forKey: .fromCache)
        partialResults = try container.decodeIfPresent(Bool.self, forKey: .partialResults)
        errors = try container.decodeIfPresent([String: String].self, forKey: .errors)
        queryTime = try container.decodeIfPresent(Double.self, forKey: .queryTime)
    }
}

// MARK: - Launch Job Models

struct LaunchJobRequest: Codable {
    let scriptPath: String?
    let scriptContent: String?
    let sourceDir: String?
    let host: String
    let jobName: String
    let slurmParams: SlurmParameters?
    let syncSettings: SyncSettings?

    enum CodingKeys: String, CodingKey {
        case scriptPath = "script_path"
        case scriptContent = "script_content"
        case sourceDir = "source_dir"
        case host
        case jobName = "job_name"
        case slurmParams = "slurm_params"
        case syncSettings = "sync_settings"
    }
}

struct LaunchJobResponse: Codable {
    let success: Bool
    let jobId: String
    let message: String?
    let host: String?
    let directoryWarning: String?
    let requiresConfirmation: Bool?

    enum CodingKeys: String, CodingKey {
        case success
        case jobId = "job_id"
        case message
        case host = "hostname"
        case directoryWarning = "directory_warning"
        case requiresConfirmation = "requires_confirmation"
    }
}

struct SlurmParameters: Codable {
    let partition: String?
    let nodes: Int?
    let cpus: Int?
    let memory: String?
    let time: String?
    let gpus: Int?
    let account: String?
    let qos: String?
    let array: String?
    let exclusive: Bool?

    enum CodingKeys: String, CodingKey {
        case partition
        case nodes
        case cpus
        case memory = "mem"
        case time
        case gpus = "gpus_per_node"
        case account
        case qos
        case array
        case exclusive
    }
}

struct SyncSettings: Codable {
    let excludePatterns: [String]?
    let includePatterns: [String]?
    let dryRun: Bool?

    enum CodingKeys: String, CodingKey {
        case excludePatterns = "exclude"
        case includePatterns = "include"
        case dryRun = "no_gitignore"
    }
}

// MARK: - Array Job Group

struct ArrayJobGroup: Codable, Identifiable {
    var id: String { arrayJobId }
    let arrayJobId: String
    let jobName: String
    let hostname: String
    let totalTasks: Int
    let stateCounts: [String: Int]

    enum CodingKeys: String, CodingKey {
        case arrayJobId = "array_job_id"
        case jobName = "job_name"
        case hostname
        case totalTasks = "total_tasks"
        case stateCounts = "state_counts"
    }
}

// MARK: - Output Type

enum OutputType: String {
    case stdout
    case stderr
    case both
}
