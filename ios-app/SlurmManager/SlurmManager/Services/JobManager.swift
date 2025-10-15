import Foundation
import Combine

class JobManager: ObservableObject {
    static let shared = JobManager()
    
    @Published var jobs: [Job] = []
    @Published var isLoading = false
    @Published var lastError: String?
    
    private var cancellables = Set<AnyCancellable>()
    private let jobCache = NSCache<NSString, JobCacheEntry>()
    
    private init() {
        setupWebSocketUpdates()
    }
    
    func fetchJobs(
        host: String? = nil,
        user: String? = nil,
        state: JobState? = nil,
        page: Int = 1,
        pageSize: Int = 50
    ) -> AnyPublisher<JobStatusResponse, Error> {
        isLoading = true
        
        return APIClient.shared.getJobs(
            host: host,
            user: user,
            state: state,
            page: page,
            pageSize: pageSize
        )
        .handleEvents(
            receiveOutput: { [weak self] response in
                if page == 1 {
                    self?.jobs = response.jobs
                } else {
                    self?.jobs.append(contentsOf: response.jobs)
                }
                self?.cacheJobs(response.jobs)
            },
            receiveCompletion: { [weak self] _ in
                self?.isLoading = false
            }
        )
        .eraseToAnyPublisher()
    }
    
    func fetchJobDetail(jobId: String, host: String? = nil) -> AnyPublisher<JobDetail, Error> {
        // Check cache first
        if let cached = getCachedJob(jobId: jobId) {
            return Just(JobDetail(
                job: cached,
                script: nil,
                output: nil,
                error: nil,
                outputPath: nil,
                errorPath: nil
            ))
            .setFailureType(to: Error.self)
            .eraseToAnyPublisher()
        }
        
        return APIClient.shared.getJobDetail(jobId: jobId, host: host)
            .handleEvents(receiveOutput: { [weak self] detail in
                self?.cacheJob(detail.job)
                self?.updateJobInList(detail.job)
            })
            .eraseToAnyPublisher()
    }
    
    func cancelJob(jobId: String, host: String? = nil) -> AnyPublisher<Bool, Error> {
        APIClient.shared.cancelJob(jobId: jobId, host: host)
            .map { $0.success }
            .handleEvents(receiveOutput: { [weak self] success in
                if success {
                    self?.updateJobState(jobId: jobId, state: .cancelled)
                }
            })
            .eraseToAnyPublisher()
    }
    
    func refreshJob(jobId: String, host: String? = nil) {
        fetchJobDetail(jobId: jobId, host: host)
            .sink(
                receiveCompletion: { _ in },
                receiveValue: { _ in }
            )
            .store(in: &cancellables)
    }
    
    // MARK: - Cache Management
    
    private func cacheJobs(_ jobs: [Job]) {
        for job in jobs {
            cacheJob(job)
        }
    }
    
    private func cacheJob(_ job: Job) {
        let entry = JobCacheEntry(job: job, timestamp: Date())
        jobCache.setObject(entry, forKey: job.id as NSString)
    }
    
    private func getCachedJob(jobId: String) -> Job? {
        guard let entry = jobCache.object(forKey: jobId as NSString) else {
            return nil
        }
        
        // Check if cache is still valid (5 minutes)
        if Date().timeIntervalSince(entry.timestamp) > 300 {
            jobCache.removeObject(forKey: jobId as NSString)
            return nil
        }
        
        return entry.job
    }
    
    func clearCache() {
        jobCache.removeAllObjects()
        jobs.removeAll()
    }
    
    // MARK: - WebSocket Updates
    
    private func setupWebSocketUpdates() {
        NotificationCenter.default.publisher(for: .jobStatusUpdated)
            .compactMap { $0.object as? Job }
            .sink { [weak self] updatedJob in
                self?.updateJobInList(updatedJob)
                self?.cacheJob(updatedJob)
            }
            .store(in: &cancellables)
    }
    
    private func updateJobInList(_ job: Job) {
        if let index = jobs.firstIndex(where: { $0.id == job.id }) {
            jobs[index] = job
        }
    }
    
    private func updateJobState(jobId: String, state: JobState) {
        if let index = jobs.firstIndex(where: { $0.id == jobId }) {
            var updatedJob = jobs[index]
            // Create a new job with updated state (Job is a struct)
            let newJob = Job(
                id: updatedJob.id,
                name: updatedJob.name,
                user: updatedJob.user,
                state: state,
                submitTime: updatedJob.submitTime,
                startTime: updatedJob.startTime,
                endTime: state.isCompleted ? Date() : updatedJob.endTime,
                partition: updatedJob.partition,
                nodes: updatedJob.nodes,
                cpus: updatedJob.cpus,
                memory: updatedJob.memory,
                timeLimit: updatedJob.timeLimit,
                workDir: updatedJob.workDir,
                command: updatedJob.command,
                array: updatedJob.array,
                qos: updatedJob.qos,
                account: updatedJob.account,
                host: updatedJob.host,
                cached: updatedJob.cached
            )
            jobs[index] = newJob
            cacheJob(newJob)
        }
    }
}

// MARK: - Cache Entry

private class JobCacheEntry {
    let job: Job
    let timestamp: Date
    
    init(job: Job, timestamp: Date) {
        self.job = job
        self.timestamp = timestamp
    }
}

// MARK: - Notification Names

extension Notification.Name {
    static let jobStatusUpdated = Notification.Name("jobStatusUpdated")
    static let jobOutputUpdated = Notification.Name("jobOutputUpdated")
}

// MARK: - JobState Extension

extension JobState {
    var isCompleted: Bool {
        switch self {
        case .completed, .failed, .cancelled, .timeout, .nodeFailure, .outOfMemory:
            return true
        default:
            return false
        }
    }
}