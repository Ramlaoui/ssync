import Foundation
import Combine

// MARK: - Persistent Cache Manager
/// High-performance caching layer with disk persistence for offline support and fast load times
actor CacheManager {
    static let shared = CacheManager()

    // MARK: - Configuration
    private let cacheDirectory: URL
    private let jobCacheFile: URL
    private let hostCacheFile: URL
    private let metadataCacheFile: URL

    // Cache expiration times (in seconds)
    private let activeJobExpiration: TimeInterval = 60        // 1 minute for active jobs
    private let completedJobExpiration: TimeInterval = 3600   // 1 hour for completed jobs
    private let hostExpiration: TimeInterval = 300            // 5 minutes for hosts

    // In-memory cache for immediate access
    private var jobCache: [String: CachedJob] = [:]
    private var hostCache: [String: CachedHost] = [:]
    private var lastSyncTime: Date?

    // MARK: - Cache Entry Types
    struct CachedJob: Codable {
        let job: Job
        let cachedAt: Date
        let expiresAt: Date

        var isExpired: Bool {
            Date() > expiresAt
        }

        var isStale: Bool {
            // Stale after half the expiration time
            Date() > cachedAt.addingTimeInterval((expiresAt.timeIntervalSince(cachedAt)) / 2)
        }
    }

    struct CachedHost: Codable {
        let host: Host
        let cachedAt: Date
        let expiresAt: Date

        var isExpired: Bool {
            Date() > expiresAt
        }
    }

    struct CacheMetadata: Codable {
        var lastFullSync: Date?
        var totalJobsCached: Int
        var cacheVersion: Int
        var appVersion: String

        static let currentVersion = 1
    }

    // MARK: - Initialization
    private init() {
        let fileManager = FileManager.default
        let cachePath = fileManager.urls(for: .cachesDirectory, in: .userDomainMask).first!
        cacheDirectory = cachePath.appendingPathComponent("SlurmManager", isDirectory: true)

        jobCacheFile = cacheDirectory.appendingPathComponent("jobs.json")
        hostCacheFile = cacheDirectory.appendingPathComponent("hosts.json")
        metadataCacheFile = cacheDirectory.appendingPathComponent("metadata.json")

        // Create cache directory if needed
        try? fileManager.createDirectory(at: cacheDirectory, withIntermediateDirectories: true)

        // Load persisted cache on init
        Task {
            await loadPersistedCache()
        }
    }

    // MARK: - Job Cache Operations

    /// Cache a job with automatic expiration based on state
    func cacheJob(_ job: Job) {
        let expiration = job.state.isTerminal ? completedJobExpiration : activeJobExpiration
        let cached = CachedJob(
            job: job,
            cachedAt: Date(),
            expiresAt: Date().addingTimeInterval(expiration)
        )
        jobCache[job.id] = cached

        // Debounced persist
        schedulePersist()
    }

    /// Cache multiple jobs efficiently
    func cacheJobs(_ jobs: [Job]) {
        for job in jobs {
            let expiration = job.state.isTerminal ? completedJobExpiration : activeJobExpiration
            let cached = CachedJob(
                job: job,
                cachedAt: Date(),
                expiresAt: Date().addingTimeInterval(expiration)
            )
            jobCache[job.id] = cached
        }

        // Single persist after batch
        schedulePersist()
    }

    /// Get a cached job if not expired
    func getJob(id: String) -> Job? {
        guard let cached = jobCache[id], !cached.isExpired else {
            return nil
        }
        return cached.job
    }

    /// Get a cached job even if stale (for immediate display while refreshing)
    func getJobStaleAllowed(id: String) -> (job: Job, isStale: Bool)? {
        guard let cached = jobCache[id] else {
            return nil
        }

        if cached.isExpired {
            return nil
        }

        return (cached.job, cached.isStale)
    }

    /// Get all cached jobs, optionally including stale ones
    func getAllJobs(includeStale: Bool = false) -> [Job] {
        let now = Date()
        return jobCache.values
            .filter { includeStale ? $0.expiresAt > now : !$0.isStale }
            .map { $0.job }
            .sorted { ($0.submitTime ?? .distantPast) > ($1.submitTime ?? .distantPast) }
    }

    /// Get jobs by state
    func getJobs(byState state: JobState) -> [Job] {
        return jobCache.values
            .filter { !$0.isExpired && $0.job.state == state }
            .map { $0.job }
    }

    /// Get jobs by host
    func getJobs(byHost host: String) -> [Job] {
        return jobCache.values
            .filter { !$0.isExpired && $0.job.host == host }
            .map { $0.job }
    }

    /// Update a job in cache
    func updateJob(_ job: Job) {
        if jobCache[job.id] != nil {
            cacheJob(job)
        }
    }

    /// Remove a job from cache
    func removeJob(id: String) {
        jobCache.removeValue(forKey: id)
        schedulePersist()
    }

    // MARK: - Host Cache Operations

    func cacheHost(_ host: Host) {
        let cached = CachedHost(
            host: host,
            cachedAt: Date(),
            expiresAt: Date().addingTimeInterval(hostExpiration)
        )
        hostCache[host.id] = cached
        schedulePersist()
    }

    func cacheHosts(_ hosts: [Host]) {
        for host in hosts {
            let cached = CachedHost(
                host: host,
                cachedAt: Date(),
                expiresAt: Date().addingTimeInterval(hostExpiration)
            )
            hostCache[host.id] = cached
        }
        schedulePersist()
    }

    func getHost(id: String) -> Host? {
        guard let cached = hostCache[id], !cached.isExpired else {
            return nil
        }
        return cached.host
    }

    func getAllHosts() -> [Host] {
        return hostCache.values
            .filter { !$0.isExpired }
            .map { $0.host }
    }

    // MARK: - Cache Metadata

    func getLastSyncTime() -> Date? {
        return lastSyncTime
    }

    func setLastSyncTime(_ date: Date) {
        lastSyncTime = date
        schedulePersist()
    }

    func getCacheStats() -> (jobs: Int, hosts: Int, lastSync: Date?) {
        let validJobs = jobCache.values.filter { !$0.isExpired }.count
        let validHosts = hostCache.values.filter { !$0.isExpired }.count
        return (validJobs, validHosts, lastSyncTime)
    }

    // MARK: - Cache Maintenance

    /// Clear expired entries to free memory
    func pruneExpired() {
        let now = Date()
        jobCache = jobCache.filter { !$0.value.isExpired }
        hostCache = hostCache.filter { !$0.value.isExpired }
        schedulePersist()
    }

    /// Clear all cache
    func clearAll() {
        jobCache.removeAll()
        hostCache.removeAll()
        lastSyncTime = nil

        // Delete persisted files
        try? FileManager.default.removeItem(at: jobCacheFile)
        try? FileManager.default.removeItem(at: hostCacheFile)
        try? FileManager.default.removeItem(at: metadataCacheFile)
    }

    /// Clear only job cache
    func clearJobs() {
        jobCache.removeAll()
        try? FileManager.default.removeItem(at: jobCacheFile)
    }

    // MARK: - Persistence

    private var persistTask: Task<Void, Never>?

    private func schedulePersist() {
        persistTask?.cancel()
        persistTask = Task {
            try? await Task.sleep(nanoseconds: 500_000_000) // 500ms debounce
            if !Task.isCancelled {
                await persistCache()
            }
        }
    }

    private func persistCache() {
        let encoder = JSONEncoder()
        encoder.dateEncodingStrategy = .iso8601

        // Persist jobs
        if let jobData = try? encoder.encode(Array(jobCache.values)) {
            try? jobData.write(to: jobCacheFile)
        }

        // Persist hosts
        if let hostData = try? encoder.encode(Array(hostCache.values)) {
            try? hostData.write(to: hostCacheFile)
        }

        // Persist metadata
        let metadata = CacheMetadata(
            lastFullSync: lastSyncTime,
            totalJobsCached: jobCache.count,
            cacheVersion: CacheMetadata.currentVersion,
            appVersion: Bundle.main.infoDictionary?["CFBundleShortVersionString"] as? String ?? "1.0"
        )
        if let metaData = try? encoder.encode(metadata) {
            try? metaData.write(to: metadataCacheFile)
        }
    }

    private func loadPersistedCache() {
        let decoder = JSONDecoder()
        decoder.dateDecodingStrategy = .iso8601

        // Load metadata first to check version
        if let metaData = try? Data(contentsOf: metadataCacheFile),
           let metadata = try? decoder.decode(CacheMetadata.self, from: metaData) {

            // Check cache version compatibility
            if metadata.cacheVersion != CacheMetadata.currentVersion {
                // Cache version mismatch, clear all
                clearAll()
                return
            }

            lastSyncTime = metadata.lastFullSync
        }

        // Load jobs
        if let jobData = try? Data(contentsOf: jobCacheFile),
           let cachedJobs = try? decoder.decode([CachedJob].self, from: jobData) {
            for cached in cachedJobs where !cached.isExpired {
                jobCache[cached.job.id] = cached
            }
        }

        // Load hosts
        if let hostData = try? Data(contentsOf: hostCacheFile),
           let cachedHosts = try? decoder.decode([CachedHost].self, from: hostData) {
            for cached in cachedHosts where !cached.isExpired {
                hostCache[cached.host.id] = cached
            }
        }
    }
}

// MARK: - JobState Extension
extension JobState {
    var isTerminal: Bool {
        switch self {
        case .completed, .failed, .cancelled, .timeout, .nodeFailure, .outOfMemory, .bootFail, .deadline:
            return true
        default:
            return false
        }
    }
}

// MARK: - Cache-Aware Job Manager Extension
extension JobManager {
    /// Fetch jobs with cache-first strategy for instant display
    @MainActor
    func fetchJobsCached(
        host: String? = nil,
        forceRefresh: Bool = false
    ) async throws -> [Job] {
        // Immediately return cached data if available
        if !forceRefresh {
            let cachedJobs = await CacheManager.shared.getAllJobs(includeStale: true)
            if !cachedJobs.isEmpty {
                // Update UI immediately with cached data
                self.jobs = cachedJobs

                // Check if we need to refresh
                let stats = await CacheManager.shared.getCacheStats()
                if let lastSync = stats.lastSync,
                   Date().timeIntervalSince(lastSync) < 30 { // Within 30 seconds
                    return cachedJobs
                }
            }
        }

        // Fetch fresh data in background
        let response = try await fetchJobsFromAPI(host: host)

        // Cache the results
        await CacheManager.shared.cacheJobs(response.jobs)
        await CacheManager.shared.setLastSyncTime(Date())

        // Update main job list
        self.jobs = response.jobs

        return response.jobs
    }

    private func fetchJobsFromAPI(host: String?) async throws -> JobStatusResponse {
        return try await withCheckedThrowingContinuation { continuation in
            var cancellable: AnyCancellable?
            cancellable = APIClient.shared.getJobs(host: host)
                .sink(
                    receiveCompletion: { completion in
                        if case .failure(let error) = completion {
                            continuation.resume(throwing: error)
                        }
                        cancellable?.cancel()
                    },
                    receiveValue: { response in
                        continuation.resume(returning: response)
                        cancellable?.cancel()
                    }
                )
        }
    }
}
