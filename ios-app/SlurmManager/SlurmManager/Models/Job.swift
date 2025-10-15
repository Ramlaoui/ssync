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
        case host
        case cached
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
        }
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

// MARK: - Launch Job Models

struct LaunchJobRequest: Codable {
    let scriptPath: String
    let sourceDir: String
    let host: String
    let jobName: String?
    let slurmParams: SlurmParameters?
    let syncSettings: SyncSettings?
    
    enum CodingKeys: String, CodingKey {
        case scriptPath = "script_path"
        case sourceDir = "source_dir"
        case host
        case jobName = "job_name"
        case slurmParams = "slurm_params"
        case syncSettings = "sync_settings"
    }
}

struct LaunchJobResponse: Codable {
    let jobId: String
    let host: String
    let jobName: String
    let submitDir: String
    let syncResult: SyncResult?
    
    enum CodingKeys: String, CodingKey {
        case jobId = "job_id"
        case host
        case jobName = "job_name"
        case submitDir = "submit_dir"
        case syncResult = "sync_result"
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