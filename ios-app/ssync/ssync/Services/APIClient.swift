import Foundation
import Combine

private typealias Parameters = [String: Any]

private enum HTTPMethod: String {
    case get = "GET"
    case post = "POST"
    case patch = "PATCH"
    case delete = "DELETE"
}

private enum APIClientError: LocalizedError {
    case invalidURL
    case invalidResponse
    case httpStatus(code: Int, detail: String?)

    var errorDescription: String? {
        switch self {
        case .invalidURL:
            return "Invalid server URL"
        case .invalidResponse:
            return "Invalid response from server"
        case .httpStatus(_, let detail):
            return detail ?? "Server request failed"
        }
    }
}

private final class APIClientSessionDelegate: NSObject, URLSessionDelegate {
    func urlSession(
        _ session: URLSession,
        didReceive challenge: URLAuthenticationChallenge,
        completionHandler: @escaping (URLSession.AuthChallengeDisposition, URLCredential?) -> Void
    ) {
        guard challenge.protectionSpace.authenticationMethod == NSURLAuthenticationMethodServerTrust,
              let trust = challenge.protectionSpace.serverTrust else {
            completionHandler(.performDefaultHandling, nil)
            return
        }

        if APIClient.isLocalHost(challenge.protectionSpace.host) {
            completionHandler(.useCredential, URLCredential(trust: trust))
        } else {
            completionHandler(.performDefaultHandling, nil)
        }
    }
}

class APIClient: ObservableObject {
    static let shared = APIClient()

    @Published var isConnected = false
    @Published var lastError: String?

    private var baseURL: String {
        UserDefaults.standard.string(forKey: "api_base_url") ?? "https://localhost:8042"
    }

    private var apiKey: String? {
        KeychainManager.shared.getAPIKey()
    }

    private var headers: [String: String] {
        var headers = ["Content-Type": "application/json"]
        if let apiKey, !apiKey.isEmpty {
            headers["X-API-Key"] = apiKey
        }
        return headers
    }

    private var session: URLSession
    private var sessionHost: String?

    private init() {
        let storedBaseURL = UserDefaults.standard.string(forKey: "api_base_url") ?? "https://localhost:8042"
        let host = URL(string: storedBaseURL)?.host
        sessionHost = host
        session = APIClient.makeSession()
    }

    func testConnection(serverURL: String? = nil, apiKey: String? = nil) -> AnyPublisher<Bool, Never> {
        request("/api/hosts", method: .get, baseURLOverride: serverURL, apiKeyOverride: apiKey)
            .map { _ in true }
            .catch { [weak self] error -> Just<Bool> in
                DispatchQueue.main.async {
                    self?.lastError = error.localizedDescription
                }
                return Just(false)
            }
            .receive(on: DispatchQueue.main)
            .handleEvents(receiveOutput: { [weak self] isConnected in
                self?.isConnected = isConnected
                if isConnected {
                    self?.lastError = nil
                }
            })
            .eraseToAnyPublisher()
    }

    func getHosts() -> AnyPublisher<[Host], Error> {
        request("/api/hosts", method: .get)
            .tryMap { data in
                try APIClient.decodeResponse([Host].self, data: data, endpoint: "/api/hosts")
            }
            .receive(on: DispatchQueue.main)
            .eraseToAnyPublisher()
    }

    func getJobs(
        host: String? = nil,
        user: String? = nil,
        state: JobState? = nil,
        page: Int = 1,
        pageSize: Int = 50
    ) -> AnyPublisher<JobStatusResponse, Error> {
        var parameters: Parameters = ["limit": min(page * pageSize, 1000)]
        if let host {
            parameters["host"] = host
        }
        if let user {
            parameters["user"] = user
        }
        if let state, let apiValue = state.apiValue {
            parameters["state"] = apiValue
        }

        return request("/api/status", method: .get, query: parameters)
            .tryMap { data in
                let responses = try APIClient.decodeResponse([JobStatusHostResponse].self, data: data, endpoint: "/api/status")
                let hosts = Array(Set(responses.map(\.hostname))).sorted()
                let mergedJobs = responses.flatMap { response in
                    let cached = response.cached ?? false
                    return response.jobs.map { job in
                        var updatedJob = job
                        updatedJob.cached = cached
                        return updatedJob
                    }
                }

                let sortedJobs = mergedJobs.sorted(by: Job.listSortComparator)

                let startIndex = max(0, (page - 1) * pageSize)
                let endIndex = min(startIndex + pageSize, sortedJobs.count)
                let pageJobs = startIndex < endIndex ? Array(sortedJobs[startIndex..<endIndex]) : []
                let fromCache = !responses.isEmpty && responses.allSatisfy { $0.cached == true }

                return JobStatusResponse(
                    jobs: pageJobs,
                    total: sortedJobs.count,
                    page: page,
                    pageSize: pageSize,
                    hosts: hosts,
                    fromCache: fromCache,
                    partialResults: false,
                    errors: nil
                )
            }
            .receive(on: DispatchQueue.main)
            .eraseToAnyPublisher()
    }

    func getJobDetail(jobId: String, host: String? = nil) -> AnyPublisher<JobDetail, Error> {
        var parameters: Parameters = [:]
        if let host {
            parameters["host"] = host
        }

        return request("/api/jobs/\(jobId)", method: .get, query: parameters)
            .tryMap { data in
                let job = try APIClient.decodeResponse(Job.self, data: data, endpoint: "/api/jobs/\(jobId)")
                return JobDetail(job: job, script: nil, output: nil, error: nil, outputPath: nil, errorPath: nil)
            }
            .receive(on: DispatchQueue.main)
            .eraseToAnyPublisher()
    }

    func getJobOutput(
        jobId: String,
        host: String? = nil,
        outputType: OutputType = .both,
        lines: Int? = 400,
        metadataOnly: Bool = false,
        forceRefresh: Bool = false
    ) -> AnyPublisher<JobOutput, Error> {
        var parameters: Parameters = [:]
        if let host {
            parameters["host"] = host
        }
        parameters["output_type"] = outputType.rawValue
        if let lines {
            parameters["lines"] = lines
        }
        if metadataOnly {
            parameters["metadata_only"] = true
        }
        if forceRefresh {
            parameters["force_refresh"] = true
        }

        return request("/api/jobs/\(jobId)/output", method: .get, query: parameters)
            .tryMap { data in
                try APIClient.decodeResponse(JobOutput.self, data: data, endpoint: "/api/jobs/\(jobId)/output")
            }
            .receive(on: DispatchQueue.main)
            .eraseToAnyPublisher()
    }

    func cancelJob(jobId: String, host: String? = nil) -> AnyPublisher<CancelJobResponse, Error> {
        var parameters: Parameters = [:]
        if let host {
            parameters["host"] = host
        }

        return request("/api/jobs/\(jobId)/cancel", method: .post, query: parameters)
            .tryMap { data in
                try APIClient.decodeResponse(CancelJobResponse.self, data: data, endpoint: "/api/jobs/\(jobId)/cancel")
            }
            .receive(on: DispatchQueue.main)
            .eraseToAnyPublisher()
    }

    func launchJob(_ launchRequest: LaunchJobRequest) -> AnyPublisher<LaunchJobResponse, Error> {
        request("/api/jobs/launch", method: .post, body: launchRequest)
            .tryMap { data in
                try APIClient.decodeResponse(LaunchJobResponse.self, data: data, endpoint: "/api/jobs/launch")
            }
            .receive(on: DispatchQueue.main)
            .eraseToAnyPublisher()
    }

    func getJobWatchers(jobId: String, host: String? = nil) -> AnyPublisher<WatchersResponse, Error> {
        var parameters: Parameters = [:]
        if let host {
            parameters["host"] = host
        }
        let encodedJobId = jobId.addingPercentEncoding(withAllowedCharacters: .urlPathAllowed) ?? jobId

        return request("/api/jobs/\(encodedJobId)/watchers", method: .get, query: parameters)
            .tryMap { data in
                try APIClient.decodeResponse(WatchersResponse.self, data: data, endpoint: "/api/jobs/\(encodedJobId)/watchers")
            }
            .receive(on: DispatchQueue.main)
            .eraseToAnyPublisher()
    }

    func getAllWatchers(state: String? = nil, limit: Int = 100) -> AnyPublisher<WatchersResponse, Error> {
        var parameters: Parameters = ["limit": limit]
        if let state {
            parameters["state"] = state
        }

        return request("/api/watchers", method: .get, query: parameters)
            .tryMap { data in
                try APIClient.decodeResponse(WatchersResponse.self, data: data, endpoint: "/api/watchers")
            }
            .receive(on: DispatchQueue.main)
            .eraseToAnyPublisher()
    }

    func getWatcherEvents(jobId: String? = nil, watcherId: Int? = nil, limit: Int = 50) -> AnyPublisher<WatcherEventsResponse, Error> {
        var parameters: Parameters = ["limit": limit]
        if let jobId {
            parameters["job_id"] = jobId
        }
        if let watcherId {
            parameters["watcher_id"] = watcherId
        }

        return request("/api/watchers/events", method: .get, query: parameters)
            .tryMap { data in
                try APIClient.decodeResponse(WatcherEventsResponse.self, data: data, endpoint: "/api/watchers/events")
            }
            .receive(on: DispatchQueue.main)
            .eraseToAnyPublisher()
    }

    func getWatcherStats() -> AnyPublisher<WatcherStats, Error> {
        request("/api/watchers/stats", method: .get)
            .tryMap { data in
                try APIClient.decodeResponse(WatcherStats.self, data: data, endpoint: "/api/watchers/stats")
            }
            .receive(on: DispatchQueue.main)
            .eraseToAnyPublisher()
    }

    func pauseWatcher(watcherId: Int) -> AnyPublisher<WatcherMessageResponse, Error> {
        request("/api/watchers/\(watcherId)/pause", method: .post)
            .tryMap { data in
                try APIClient.decodeResponse(WatcherMessageResponse.self, data: data, endpoint: "/api/watchers/\(watcherId)/pause")
            }
            .receive(on: DispatchQueue.main)
            .eraseToAnyPublisher()
    }

    func resumeWatcher(watcherId: Int) -> AnyPublisher<WatcherMessageResponse, Error> {
        request("/api/watchers/\(watcherId)/resume", method: .post)
            .tryMap { data in
                try APIClient.decodeResponse(WatcherMessageResponse.self, data: data, endpoint: "/api/watchers/\(watcherId)/resume")
            }
            .receive(on: DispatchQueue.main)
            .eraseToAnyPublisher()
    }

    func triggerWatcher(watcherId: Int, testText: String? = nil) -> AnyPublisher<WatcherTriggerResponse, Error> {
        if let testText, !testText.isEmpty {
            return request("/api/watchers/\(watcherId)/trigger", method: .post, body: WatcherTriggerRequest(testText: testText))
                .tryMap { data in
                    try APIClient.decodeResponse(WatcherTriggerResponse.self, data: data, endpoint: "/api/watchers/\(watcherId)/trigger")
                }
                .receive(on: DispatchQueue.main)
                .eraseToAnyPublisher()
        }

        return request("/api/watchers/\(watcherId)/trigger", method: .post)
            .tryMap { data in
                try APIClient.decodeResponse(WatcherTriggerResponse.self, data: data, endpoint: "/api/watchers/\(watcherId)/trigger")
            }
            .receive(on: DispatchQueue.main)
            .eraseToAnyPublisher()
    }

    func deleteWatcher(watcherId: Int) -> AnyPublisher<WatcherMessageResponse, Error> {
        request("/api/watchers/\(watcherId)", method: .delete)
            .tryMap { data in
                try APIClient.decodeResponse(WatcherMessageResponse.self, data: data, endpoint: "/api/watchers/\(watcherId)")
            }
            .receive(on: DispatchQueue.main)
            .eraseToAnyPublisher()
    }

    func attachWatchers(jobId: String, host: String, definitions: [WatcherDefinitionRequest]) -> AnyPublisher<WatcherAttachResponse, Error> {
        let encodedJobId = jobId.addingPercentEncoding(withAllowedCharacters: .urlPathAllowed) ?? jobId
        let encodedHost = host.addingPercentEncoding(withAllowedCharacters: .urlQueryAllowed) ?? host
        let path = "/api/jobs/\(encodedJobId)/watchers?host=\(encodedHost)"

        return request(path, method: .post, body: definitions)
            .tryMap { data in
                try APIClient.decodeResponse(WatcherAttachResponse.self, data: data, endpoint: path)
            }
            .receive(on: DispatchQueue.main)
            .eraseToAnyPublisher()
    }

    func createWatcher(_ request: WatcherCreateRequest) -> AnyPublisher<Watcher, Error> {
        self.request("/api/watchers", method: .post, body: request)
            .tryMap { data in
                try APIClient.decodeResponse(Watcher.self, data: data, endpoint: "/api/watchers")
            }
            .receive(on: DispatchQueue.main)
            .eraseToAnyPublisher()
    }

    func browseFiles(path: String, showHidden: Bool = false, dirsOnly: Bool = true) -> AnyPublisher<FileBrowserResponse, Error> {
        let parameters: Parameters = [
            "path": path,
            "show_hidden": showHidden,
            "dirs_only": dirsOnly,
        ]

        return request("/api/local/list", method: .get, query: parameters)
            .tryMap { data in
                try APIClient.decodeResponse(FileBrowserResponse.self, data: data, endpoint: "/api/local/list")
            }
            .receive(on: DispatchQueue.main)
            .eraseToAnyPublisher()
    }

    func getJobScript(jobId: String, host: String? = nil) -> AnyPublisher<JobScriptResponse, Error> {
        var parameters: Parameters = [:]
        if let host {
            parameters["host"] = host
        }

        return request("/api/jobs/\(jobId)/script", method: .get, query: parameters)
            .tryMap { data in
                try APIClient.decodeResponse(JobScriptResponse.self, data: data, endpoint: "/api/jobs/\(jobId)/script")
            }
            .receive(on: DispatchQueue.main)
            .eraseToAnyPublisher()
    }

    func registerNotificationDevice(_ payload: NotificationDeviceRegistrationRequest) -> AnyPublisher<NotificationDeviceRegistrationResponse, Error> {
        request("/api/notifications/devices", method: .post, body: payload)
            .tryMap { data in
                try APIClient.decodeResponse(
                    NotificationDeviceRegistrationResponse.self,
                    data: data,
                    endpoint: "/api/notifications/devices"
                )
            }
            .receive(on: DispatchQueue.main)
            .eraseToAnyPublisher()
    }

    func unregisterNotificationDevice(token: String, apiKeyOverride: String? = nil) -> AnyPublisher<NotificationDeviceRemovalResponse, Error> {
        let encodedToken = token.addingPercentEncoding(withAllowedCharacters: .urlPathAllowed) ?? token
        return request(
            "/api/notifications/devices/\(encodedToken)",
            method: .delete,
            apiKeyOverride: apiKeyOverride
        )
        .tryMap { data in
            try APIClient.decodeResponse(
                NotificationDeviceRemovalResponse.self,
                data: data,
                endpoint: "/api/notifications/devices/\(encodedToken)"
            )
        }
        .receive(on: DispatchQueue.main)
        .eraseToAnyPublisher()
    }

    func getNotificationPreferences() -> AnyPublisher<NotificationPreferencesResponse, Error> {
        request("/api/notifications/preferences", method: .get)
            .tryMap { data in
                try APIClient.decodeResponse(
                    NotificationPreferencesResponse.self,
                    data: data,
                    endpoint: "/api/notifications/preferences"
                )
            }
            .receive(on: DispatchQueue.main)
            .eraseToAnyPublisher()
    }

    func updateNotificationPreferences(_ payload: NotificationPreferencesPatchRequest) -> AnyPublisher<NotificationPreferencesResponse, Error> {
        request("/api/notifications/preferences", method: .patch, body: payload)
            .tryMap { data in
                try APIClient.decodeResponse(
                    NotificationPreferencesResponse.self,
                    data: data,
                    endpoint: "/api/notifications/preferences"
                )
            }
            .receive(on: DispatchQueue.main)
            .eraseToAnyPublisher()
    }

    func sendTestNotification(_ payload: NotificationTestRequest) -> AnyPublisher<NotificationTestResponse, Error> {
        request("/api/notifications/test", method: .post, body: payload)
            .tryMap { data in
                try APIClient.decodeResponse(
                    NotificationTestResponse.self,
                    data: data,
                    endpoint: "/api/notifications/test"
                )
            }
            .receive(on: DispatchQueue.main)
            .eraseToAnyPublisher()
    }

    private func request(
        _ path: String,
        method: HTTPMethod,
        query: Parameters? = nil,
        baseURLOverride: String? = nil,
        apiKeyOverride: String? = nil
    ) -> AnyPublisher<Data, Error> {
        refreshSessionIfNeeded(baseURLOverride: baseURLOverride)
        guard let request = makeRequest(
            path: path,
            method: method,
            query: query,
            baseURLOverride: baseURLOverride,
            apiKeyOverride: apiKeyOverride
        ) else {
            return Fail(error: APIClientError.invalidURL).eraseToAnyPublisher()
        }
        return execute(request)
    }

    private func request<T: Encodable>(
        _ path: String,
        method: HTTPMethod,
        body: T,
        query: Parameters? = nil,
        baseURLOverride: String? = nil,
        apiKeyOverride: String? = nil
    ) -> AnyPublisher<Data, Error> {
        refreshSessionIfNeeded(baseURLOverride: baseURLOverride)
        guard var request = makeRequest(
            path: path,
            method: method,
            query: query,
            baseURLOverride: baseURLOverride,
            apiKeyOverride: apiKeyOverride
        ) else {
            return Fail(error: APIClientError.invalidURL).eraseToAnyPublisher()
        }

        do {
            request.httpBody = try JSONEncoder().encode(body)
        } catch {
            return Fail(error: error).eraseToAnyPublisher()
        }

        return execute(request)
    }

    private func makeRequest(
        path: String,
        method: HTTPMethod,
        query: Parameters?,
        baseURLOverride: String?,
        apiKeyOverride: String?
    ) -> URLRequest? {
        let effectiveBaseURL = (baseURLOverride?.isEmpty == false ? baseURLOverride : nil) ?? baseURL
        guard var components = URLComponents(string: effectiveBaseURL + path) else {
            return nil
        }

        let extraItems = APIClient.makeQueryItems(from: query ?? [:])
        if !extraItems.isEmpty {
            components.queryItems = (components.queryItems ?? []) + extraItems
        }

        guard let url = components.url else { return nil }

        var request = URLRequest(url: url)
        request.httpMethod = method.rawValue
        request.timeoutInterval = 30
        var requestHeaders = headers
        if let apiKeyOverride, !apiKeyOverride.isEmpty {
            requestHeaders["X-API-Key"] = apiKeyOverride
        }
        requestHeaders.forEach { request.setValue($1, forHTTPHeaderField: $0) }
        return request
    }

    private func execute(_ request: URLRequest) -> AnyPublisher<Data, Error> {
        session.dataTaskPublisher(for: request)
            .tryMap { output in
                guard let response = output.response as? HTTPURLResponse else {
                    throw APIClientError.invalidResponse
                }
                guard (200...299).contains(response.statusCode) else {
                    throw APIClientError.httpStatus(
                        code: response.statusCode,
                        detail: APIClient.parseErrorDetail(from: output.data)
                    )
                }
                return output.data
            }
            .eraseToAnyPublisher()
    }

    private static func decodeResponse<T: Decodable>(_ type: T.Type, data: Data, endpoint: String) throws -> T {
        do {
            return try JSONDecoder.slurmDecoder.decode(T.self, from: data)
        } catch {
            #if DEBUG
            let raw = String(data: data, encoding: .utf8) ?? "<non-utf8 data>"
            let details = decodingErrorDetails(error)
            print("[APIClient] Decode failed for \(endpoint)")
            print("[APIClient] Target type: \(String(describing: T.self))")
            print("[APIClient] Error: \(details)")
            print("[APIClient] Raw response: \(raw)")
            #endif
            throw error
        }
    }

    private static func decodingErrorDetails(_ error: Error) -> String {
        guard let decodingError = error as? DecodingError else {
            return error.localizedDescription
        }

        switch decodingError {
        case .typeMismatch(let type, let context):
            return "Type mismatch (\(type)) at \(codingPath(context.codingPath)): \(context.debugDescription)"
        case .valueNotFound(let type, let context):
            return "Value not found (\(type)) at \(codingPath(context.codingPath)): \(context.debugDescription)"
        case .keyNotFound(let key, let context):
            return "Key '\(key.stringValue)' not found at \(codingPath(context.codingPath)): \(context.debugDescription)"
        case .dataCorrupted(let context):
            return "Data corrupted at \(codingPath(context.codingPath)): \(context.debugDescription)"
        @unknown default:
            return "Unknown decoding error: \(decodingError)"
        }
    }

    private static func codingPath(_ path: [CodingKey]) -> String {
        guard !path.isEmpty else { return "<root>" }
        return path.map { $0.stringValue }.joined(separator: ".")
    }

    private func refreshSessionIfNeeded(baseURLOverride: String? = nil) {
        let effectiveBaseURL = (baseURLOverride?.isEmpty == false ? baseURLOverride : nil) ?? baseURL
        let host = URL(string: effectiveBaseURL)?.host
        guard host != sessionHost else { return }
        sessionHost = host
        session = APIClient.makeSession()
    }

    private static func makeSession() -> URLSession {
        let configuration = URLSessionConfiguration.default
        configuration.timeoutIntervalForRequest = 30
        configuration.timeoutIntervalForResource = 300
        configuration.waitsForConnectivity = true
        return URLSession(configuration: configuration, delegate: APIClientSessionDelegate(), delegateQueue: nil)
    }

    private static func makeQueryItems(from parameters: Parameters) -> [URLQueryItem] {
        parameters.flatMap { key, value in
            switch value {
            case let string as String:
                return [URLQueryItem(name: key, value: string)]
            case let int as Int:
                return [URLQueryItem(name: key, value: String(int))]
            case let bool as Bool:
                return [URLQueryItem(name: key, value: bool ? "true" : "false")]
            case let double as Double:
                return [URLQueryItem(name: key, value: String(double))]
            case let array as [String]:
                return array.map { URLQueryItem(name: key, value: $0) }
            default:
                return [URLQueryItem(name: key, value: String(describing: value))]
            }
        }
    }

    private static func parseErrorDetail(from data: Data) -> String? {
        if let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
           let detail = json["detail"] as? String {
            return detail
        }

        let raw = String(data: data, encoding: .utf8)?.trimmingCharacters(in: .whitespacesAndNewlines)
        return raw?.isEmpty == false ? raw : nil
    }

    static func isLocalHost(_ host: String) -> Bool {
        if host == "localhost" || host == "127.0.0.1" || host == "::1" {
            return true
        }
        if host.hasSuffix(".local") {
            return true
        }
        if host.hasPrefix("10.") || host.hasPrefix("192.168.") {
            return true
        }
        if host.hasPrefix("172.") {
            let parts = host.split(separator: ".")
            if parts.count > 1, let second = Int(parts[1]) {
                return (16...31).contains(second)
            }
        }
        return false
    }
}

private struct WatcherTriggerRequest: Encodable {
    let testText: String

    enum CodingKeys: String, CodingKey {
        case testText = "test_text"
    }
}

// MARK: - Supporting Types

enum OutputType: String {
    case stdout = "stdout"
    case stderr = "stderr"
    case both = "both"
}

struct JobOutput: Codable {
    let stdout: String?
    let stderr: String?
    let stdoutMetadata: FileMetadata?
    let stderrMetadata: FileMetadata?

    enum CodingKeys: String, CodingKey {
        case stdout
        case stderr
        case stdoutMetadata = "stdout_metadata"
        case stderrMetadata = "stderr_metadata"
    }

    var output: String? { stdout }
    var error: String? { stderr }
}

struct JobScriptResponse: Codable {
    let jobId: String
    let hostname: String
    let scriptContent: String?
    let contentLength: Int?
    let localSourceDir: String?

    enum CodingKeys: String, CodingKey {
        case jobId = "job_id"
        case hostname
        case scriptContent = "script_content"
        case contentLength = "content_length"
        case localSourceDir = "local_source_dir"
    }
}

struct FileMetadata: Codable {
    let path: String?
    let exists: Bool?
    let sizeBytes: Int64?
    let lastModified: String?
    let accessPath: String?

    enum CodingKeys: String, CodingKey {
        case path
        case exists
        case sizeBytes = "size_bytes"
        case lastModified = "last_modified"
        case accessPath = "access_path"
    }
}

struct CompleteJobDataResponse: Codable {
    let jobId: String
    let hostname: String
    let jobInfo: Job
    let scriptContent: String?
    let scriptLength: Int?
    let stdout: String?
    let stderr: String?
    let stdoutMetadata: FileMetadata?
    let stderrMetadata: FileMetadata?
    let cachedAt: String?
    let dataCompleteness: [String: Bool]?

    enum CodingKeys: String, CodingKey {
        case jobId = "job_id"
        case hostname
        case jobInfo = "job_info"
        case scriptContent = "script_content"
        case scriptLength = "script_length"
        case stdout
        case stderr
        case stdoutMetadata = "stdout_metadata"
        case stderrMetadata = "stderr_metadata"
        case cachedAt = "cached_at"
        case dataCompleteness = "data_completeness"
    }
}

struct CancelJobResponse: Codable {
    let message: String?

    var success: Bool { true }
}

struct FileBrowserResponse: Codable {
    let path: String
    let entries: [FileEntry]
    let parent: String?
}

struct FileEntry: Codable, Identifiable {
    let name: String
    let path: String
    let isDir: Bool
    let size: Int64?
    let modified: Date?

    var id: String { path }

    enum CodingKeys: String, CodingKey {
        case name
        case path
        case isDir = "is_dir"
        case size
        case modified
    }
}

struct NotificationDeviceRegistrationRequest: Codable {
    let token: String
    let platform: String
    let environment: String?
    let bundleId: String?
    let deviceId: String?
    let enabled: Bool

    enum CodingKeys: String, CodingKey {
        case token
        case platform
        case environment
        case bundleId = "bundle_id"
        case deviceId = "device_id"
        case enabled
    }
}

struct NotificationDeviceRegistrationResponse: Codable {
    let success: Bool
    let token: String
}

struct NotificationDeviceRemovalResponse: Codable {
    let success: Bool
    let deleted: Int?
}

struct NotificationPreferencesResponse: Codable {
    let enabled: Bool
    let allowedStates: [String]?
    let mutedJobIds: [String]
    let mutedHosts: [String]
    let mutedJobNamePatterns: [String]
    let allowedUsers: [String]

    enum CodingKeys: String, CodingKey {
        case enabled
        case allowedStates = "allowed_states"
        case mutedJobIds = "muted_job_ids"
        case mutedHosts = "muted_hosts"
        case mutedJobNamePatterns = "muted_job_name_patterns"
        case allowedUsers = "allowed_users"
    }
}

struct NotificationPreferencesPatchRequest: Codable {
    let enabled: Bool?
    let allowedStates: [String]?
    let mutedJobIds: [String]?
    let mutedHosts: [String]?
    let mutedJobNamePatterns: [String]?
    let allowedUsers: [String]?

    enum CodingKeys: String, CodingKey {
        case enabled
        case allowedStates = "allowed_states"
        case mutedJobIds = "muted_job_ids"
        case mutedHosts = "muted_hosts"
        case mutedJobNamePatterns = "muted_job_name_patterns"
        case allowedUsers = "allowed_users"
    }
}

struct NotificationTestRequest: Codable {
    let title: String
    let body: String
    let token: String?
}

struct NotificationTestResponse: Codable {
    let success: Bool
    let sent: Int
}

// MARK: - JSON Decoder Extension

extension JSONDecoder {
    static var slurmDecoder: JSONDecoder {
        let decoder = JSONDecoder()
        decoder.dateDecodingStrategy = .custom { decoder in
            let container = try decoder.singleValueContainer()
            let dateString = try container.decode(String.self)

            let formatter = ISO8601DateFormatter()
            formatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
            if let date = formatter.date(from: dateString) {
                return date
            }

            formatter.formatOptions = [.withInternetDateTime]
            if let date = formatter.date(from: dateString) {
                return date
            }

            throw DecodingError.dataCorruptedError(
                in: container,
                debugDescription: "Cannot decode date string \(dateString)"
            )
        }
        return decoder
    }
}
