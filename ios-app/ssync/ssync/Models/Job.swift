import Foundation

// MARK: - Job Models

struct Job: Codable, Identifiable, Hashable {
    let id: String
    let name: String
    let user: String?
    let state: JobState
    let submitTime: Date?
    let startTime: Date?
    let endTime: Date?
    let partition: String?
    let nodes: String?
    let cpus: String?
    let memory: String?
    let timeLimit: String?
    let workDir: String?
    let stdoutFile: String?
    let stderrFile: String?
    let submitLine: String?
    let command: String?
    let array: String?
    let qos: String?
    let account: String?
    let host: String
    var cached: Bool = false
    
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
        case stdoutFile = "stdout_file"
        case stderrFile = "stderr_file"
        case submitLine = "submit_line"
        case command
        case array
        case qos
        case account
        case host = "hostname"
        case cached
    }

    init(
        id: String,
        name: String,
        user: String?,
        state: JobState,
        submitTime: Date?,
        startTime: Date?,
        endTime: Date?,
        partition: String?,
        nodes: String?,
        cpus: String?,
        memory: String?,
        timeLimit: String?,
        workDir: String?,
        stdoutFile: String? = nil,
        stderrFile: String? = nil,
        submitLine: String? = nil,
        command: String?,
        array: String?,
        qos: String?,
        account: String?,
        host: String,
        cached: Bool = false
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
        self.stdoutFile = stdoutFile
        self.stderrFile = stderrFile
        self.submitLine = submitLine
        self.command = command
        self.array = array
        self.qos = qos
        self.account = account
        self.host = host
        self.cached = cached
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)

        id = try container.decode(String.self, forKey: .id)
        name = try container.decode(String.self, forKey: .name)
        user = try container.decodeIfPresent(String.self, forKey: .user)
        state = try container.decode(JobState.self, forKey: .state)

        submitTime = Job.parseDate(from: container, key: .submitTime)
        startTime = Job.parseDate(from: container, key: .startTime)
        endTime = Job.parseDate(from: container, key: .endTime)

        partition = try container.decodeIfPresent(String.self, forKey: .partition)
        nodes = try container.decodeIfPresent(String.self, forKey: .nodes)
        cpus = try container.decodeIfPresent(String.self, forKey: .cpus)
        memory = try container.decodeIfPresent(String.self, forKey: .memory)
        timeLimit = try container.decodeIfPresent(String.self, forKey: .timeLimit)
        workDir = try container.decodeIfPresent(String.self, forKey: .workDir)
        stdoutFile = try container.decodeIfPresent(String.self, forKey: .stdoutFile)
        stderrFile = try container.decodeIfPresent(String.self, forKey: .stderrFile)
        submitLine = try container.decodeIfPresent(String.self, forKey: .submitLine)
        command = try container.decodeIfPresent(String.self, forKey: .command)
        array = try container.decodeIfPresent(String.self, forKey: .array)
        qos = try container.decodeIfPresent(String.self, forKey: .qos)
        account = try container.decodeIfPresent(String.self, forKey: .account)
        host = try container.decode(String.self, forKey: .host)
        cached = try container.decodeIfPresent(Bool.self, forKey: .cached) ?? false
    }

    func encode(to encoder: Encoder) throws {
        var container = encoder.container(keyedBy: CodingKeys.self)
        try container.encode(id, forKey: .id)
        try container.encode(name, forKey: .name)
        try container.encodeIfPresent(user, forKey: .user)
        try container.encode(state, forKey: .state)

        try container.encodeIfPresent(Job.formatDate(submitTime), forKey: .submitTime)
        try container.encodeIfPresent(Job.formatDate(startTime), forKey: .startTime)
        try container.encodeIfPresent(Job.formatDate(endTime), forKey: .endTime)

        try container.encodeIfPresent(partition, forKey: .partition)
        try container.encodeIfPresent(nodes, forKey: .nodes)
        try container.encodeIfPresent(cpus, forKey: .cpus)
        try container.encodeIfPresent(memory, forKey: .memory)
        try container.encodeIfPresent(timeLimit, forKey: .timeLimit)
        try container.encodeIfPresent(workDir, forKey: .workDir)
        try container.encodeIfPresent(stdoutFile, forKey: .stdoutFile)
        try container.encodeIfPresent(stderrFile, forKey: .stderrFile)
        try container.encodeIfPresent(submitLine, forKey: .submitLine)
        try container.encodeIfPresent(command, forKey: .command)
        try container.encodeIfPresent(array, forKey: .array)
        try container.encodeIfPresent(qos, forKey: .qos)
        try container.encodeIfPresent(account, forKey: .account)
        try container.encode(host, forKey: .host)
        try container.encode(cached, forKey: .cached)
    }

    private static func parseDate(from container: KeyedDecodingContainer<CodingKeys>, key: CodingKeys) -> Date? {
        if let raw = try? container.decodeIfPresent(String.self, forKey: key) {
            let trimmed = raw.trimmingCharacters(in: .whitespacesAndNewlines)
            if trimmed.isEmpty || trimmed == "N/A" || trimmed == "None" || trimmed == "UNKNOWN" {
                return nil
            }
            if let date = Job.isoFormatterWithFractionalSeconds.date(from: trimmed) {
                return date
            }
            if let date = Job.isoFormatter.date(from: trimmed) {
                return date
            }
            return nil
        }

        if let timestamp = try? container.decodeIfPresent(Double.self, forKey: key) {
            return Date(timeIntervalSince1970: timestamp)
        }

        return nil
    }

    private static func formatDate(_ date: Date?) -> String? {
        guard let date = date else { return nil }
        return isoFormatterWithFractionalSeconds.string(from: date)
    }

    private static let isoFormatterWithFractionalSeconds: ISO8601DateFormatter = {
        let formatter = ISO8601DateFormatter()
        formatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        return formatter
    }()

    private static let isoFormatter: ISO8601DateFormatter = {
        let formatter = ISO8601DateFormatter()
        formatter.formatOptions = [.withInternetDateTime]
        return formatter
    }()
    
    var isRunning: Bool {
        state == .running
    }
    
    var isPending: Bool {
        state == .pending
    }
    
    var isCompleted: Bool {
        state == .completed
            || state == .failed
            || state == .cancelled
            || state == .timeout
            || state == .nodeFailure
            || state == .outOfMemory
    }
    
    var statusColor: String {
        switch state {
        case .running: return "blue"
        case .pending: return "orange"
        case .completed: return "green"
        case .failed, .timeout, .nodeFailure, .outOfMemory: return "red"
        case .cancelled: return "gray"
        default: return "gray"
        }
    }
    
    var formattedDuration: String? {
        guard let start = startTime else { return nil }
        let end = endTime ?? Date()
        let duration = end.timeIntervalSince(start)
        return formatDuration(duration)
    }

    nonisolated var listSortDate: Date {
        submitTime ?? startTime ?? endTime ?? .distantPast
    }

    nonisolated static func listSortComparator(_ lhs: Job, _ rhs: Job) -> Bool {
        let lhsIsRunning = lhs.state == .running
        let rhsIsRunning = rhs.state == .running

        if lhsIsRunning != rhsIsRunning {
            return lhsIsRunning
        }

        if lhs.listSortDate != rhs.listSortDate {
            return lhs.listSortDate > rhs.listSortDate
        }

        return lhs.id > rhs.id
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
    case pending = "PD"
    case running = "R"
    case completed = "CD"
    case failed = "F"
    case cancelled = "CA"
    case timeout = "TO"
    case nodeFailure = "NF"
    case outOfMemory = "OOM"
    case unknown = "UNKNOWN"
    
    var displayName: String {
        switch self {
        case .pending: return "Pending"
        case .running: return "Running"
        case .completed: return "Completed"
        case .failed: return "Failed"
        case .cancelled: return "Cancelled"
        case .timeout: return "Timeout"
        case .nodeFailure: return "Node Failure"
        case .outOfMemory: return "Out of Memory"
        case .unknown: return "Unknown"
        }
    }

    var apiValue: String? {
        switch self {
        case .pending, .running, .completed, .failed, .cancelled, .timeout:
            return rawValue
        default:
            return nil
        }
    }

    static var filterOptions: [JobState] {
        allCases.filter { $0.apiValue != nil }
    }
}

// MARK: - Job Detail

struct JobDetail: Codable {
    let job: Job
    let script: String?
    let output: String?
    let error: String?
    let outputPath: String?
    let errorPath: String?
    
    enum CodingKeys: String, CodingKey {
        case job
        case script
        case output
        case error
        case outputPath = "output_path"
        case errorPath = "error_path"
    }
}

// MARK: - Job Status Response

struct JobStatusResponse: Codable {
    let jobs: [Job]
    let total: Int
    let page: Int
    let pageSize: Int
    let hosts: [String]
    let fromCache: Bool
    let partialResults: Bool
    let errors: [String: String]?
    
    enum CodingKeys: String, CodingKey {
        case jobs
        case total
        case page
        case pageSize = "page_size"
        case hosts
        case fromCache = "from_cache"
        case partialResults = "partial_results"
        case errors
    }
}

// MARK: - Job Status (per-host) Response

struct JobStatusHostResponse: Codable {
    let hostname: String
    let jobs: [Job]
    let totalJobs: Int
    let queryTime: String?
    let cached: Bool?
    let groupArrayJobs: Bool?
    
    enum CodingKeys: String, CodingKey {
        case hostname
        case jobs
        case totalJobs = "total_jobs"
        case queryTime = "query_time"
        case cached
        case groupArrayJobs = "group_array_jobs"
    }
}

// MARK: - Launch Job Models

struct LaunchJobRequest: Codable {
    let scriptContent: String
    let sourceDir: String?
    let host: String
    let jobName: String?
    let cpus: Int?
    let mem: Int?
    let time: Int?
    let partition: String?
    let nodes: Int?
    let gpusPerNode: Int?
    let account: String?
    let exclude: [String]
    let include: [String]
    let noGitignore: Bool
    
    enum CodingKeys: String, CodingKey {
        case scriptContent = "script_content"
        case sourceDir = "source_dir"
        case host
        case jobName = "job_name"
        case cpus
        case mem
        case time
        case partition
        case nodes
        case gpusPerNode = "gpus_per_node"
        case account
        case exclude
        case include
        case noGitignore = "no_gitignore"
    }

    init(
        scriptContent: String,
        sourceDir: String?,
        host: String,
        jobName: String?,
        slurmParams: SlurmParameters?,
        syncSettings: SyncSettings?
    ) {
        self.scriptContent = scriptContent
        let trimmedSource = sourceDir?.trimmingCharacters(in: .whitespacesAndNewlines)
        self.sourceDir = trimmedSource?.isEmpty == false ? trimmedSource : nil
        self.host = host
        self.jobName = jobName
        self.cpus = slurmParams?.cpus
        self.mem = LaunchJobRequest.parseMemoryGB(slurmParams?.memory)
        self.time = LaunchJobRequest.parseMinutes(slurmParams?.time)
        self.partition = slurmParams?.partition
        self.nodes = slurmParams?.nodes
        self.gpusPerNode = slurmParams?.gpus
        self.account = slurmParams?.account
        self.exclude = syncSettings?.excludePatterns ?? []
        self.include = syncSettings?.includePatterns ?? []
        self.noGitignore = false
    }

    private static func parseMemoryGB(_ value: String?) -> Int? {
        guard let value else { return nil }
        let trimmed = value.trimmingCharacters(in: .whitespacesAndNewlines).uppercased()
        guard !trimmed.isEmpty else { return nil }

        if let intValue = Int(trimmed) {
            return intValue
        }

        if trimmed.hasSuffix("GB"), let intValue = Int(trimmed.dropLast(2)) {
            return intValue
        }

        if trimmed.hasSuffix("G"), let intValue = Int(trimmed.dropLast()) {
            return intValue
        }

        if trimmed.hasSuffix("MB"), let intValue = Int(trimmed.dropLast(2)) {
            return max(1, intValue / 1024)
        }

        if trimmed.hasSuffix("M"), let intValue = Int(trimmed.dropLast()) {
            return max(1, intValue / 1024)
        }

        return nil
    }

    private static func parseMinutes(_ value: String?) -> Int? {
        guard let value else { return nil }
        let trimmed = value.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else { return nil }

        if let intValue = Int(trimmed) {
            return intValue
        }

        let parts = trimmed.split(separator: ":").compactMap { Int($0) }
        switch parts.count {
        case 3:
            return (parts[0] * 60) + parts[1] + (parts[2] > 0 ? 1 : 0)
        case 2:
            return parts[0] + (parts[1] > 0 ? 1 : 0)
        default:
            return nil
        }
    }
}

struct LaunchJobResponse: Codable {
    let success: Bool
    let jobId: String?
    let message: String
    let hostname: String
    let directoryWarning: String?
    let requiresConfirmation: Bool
    
    enum CodingKeys: String, CodingKey {
        case jobId = "job_id"
        case success
        case message
        case hostname
        case directoryWarning = "directory_warning"
        case requiresConfirmation = "requires_confirmation"
    }

    var host: String {
        hostname
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
}

struct SyncSettings: Codable {
    let excludePatterns: [String]?
    let includePatterns: [String]?
    let dryRun: Bool?
    
    enum CodingKeys: String, CodingKey {
        case excludePatterns = "exclude_patterns"
        case includePatterns = "include_patterns"
        case dryRun = "dry_run"
    }
}

struct SyncResult: Codable {
    let filesTransferred: Int
    let bytesTransferred: Int
    let duration: Double
    
    enum CodingKeys: String, CodingKey {
        case filesTransferred = "files_transferred"
        case bytesTransferred = "bytes_transferred"
        case duration
    }
}
