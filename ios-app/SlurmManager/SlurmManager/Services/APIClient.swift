import Foundation
import Alamofire
import Combine

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
    
    private var headers: HTTPHeaders {
        var headers = HTTPHeaders()
        if let apiKey = apiKey {
            headers.add(.init(name: "X-API-Key", value: apiKey))
        }
        headers.add(.contentType("application/json"))
        return headers
    }
    
    private let session: Session
    
    private init() {
        // Configure Alamofire to accept self-signed certificates for development
        let evaluators: [String: ServerTrustEvaluating] = [
            "localhost": DisabledTrustEvaluator()
        ]
        
        let serverTrustManager = ServerTrustManager(evaluators: evaluators)
        
        let configuration = URLSessionConfiguration.default
        configuration.timeoutIntervalForRequest = 30
        configuration.timeoutIntervalForResource = 300
        
        self.session = Session(
            configuration: configuration,
            serverTrustManager: serverTrustManager
        )
    }
    
    // MARK: - Connection Test
    
    func testConnection() -> AnyPublisher<Bool, Never> {
        Future { promise in
            self.session.request("\(self.baseURL)/health")
                .validate()
                .response { response in
                    promise(.success(response.error == nil))
                }
        }
        .receive(on: DispatchQueue.main)
        .handleEvents(receiveOutput: { [weak self] isConnected in
            self?.isConnected = isConnected
        })
        .eraseToAnyPublisher()
    }
    
    // MARK: - Hosts
    
    func getHosts() -> AnyPublisher<[Host], Error> {
        request("/api/hosts", method: .get)
            .decode(type: [Host].self, decoder: JSONDecoder.slurmDecoder)
            .receive(on: DispatchQueue.main)
            .eraseToAnyPublisher()
    }
    
    // MARK: - Jobs
    
    func getJobs(
        host: String? = nil,
        user: String? = nil,
        state: JobState? = nil,
        page: Int = 1,
        pageSize: Int = 50
    ) -> AnyPublisher<JobStatusResponse, Error> {
        var parameters: Parameters = [
            "page": page,
            "page_size": pageSize
        ]
        
        if let host = host {
            parameters["host"] = host
        }
        if let user = user {
            parameters["user"] = user
        }
        if let state = state {
            parameters["state"] = state.rawValue
        }
        
        return request("/api/jobs", method: .get, parameters: parameters)
            .decode(type: JobStatusResponse.self, decoder: JSONDecoder.slurmDecoder)
            .receive(on: DispatchQueue.main)
            .eraseToAnyPublisher()
    }
    
    func getJobDetail(jobId: String, host: String? = nil) -> AnyPublisher<JobDetail, Error> {
        var parameters: Parameters = [:]
        if let host = host {
            parameters["host"] = host
        }
        
        return request("/api/jobs/\(jobId)", method: .get, parameters: parameters)
            .decode(type: JobDetail.self, decoder: JSONDecoder.slurmDecoder)
            .receive(on: DispatchQueue.main)
            .eraseToAnyPublisher()
    }
    
    func getJobOutput(
        jobId: String,
        host: String? = nil,
        outputType: OutputType = .both
    ) -> AnyPublisher<JobOutput, Error> {
        var parameters: Parameters = [
            "output_type": outputType.rawValue
        ]
        if let host = host {
            parameters["host"] = host
        }
        
        return request("/api/jobs/\(jobId)/output", method: .get, parameters: parameters)
            .decode(type: JobOutput.self, decoder: JSONDecoder.slurmDecoder)
            .receive(on: DispatchQueue.main)
            .eraseToAnyPublisher()
    }
    
    func cancelJob(jobId: String, host: String? = nil) -> AnyPublisher<CancelJobResponse, Error> {
        var parameters: Parameters = [:]
        if let host = host {
            parameters["host"] = host
        }
        
        return request("/api/jobs/\(jobId)/cancel", method: .post, parameters: parameters)
            .decode(type: CancelJobResponse.self, decoder: JSONDecoder.slurmDecoder)
            .receive(on: DispatchQueue.main)
            .eraseToAnyPublisher()
    }
    
    func launchJob(_ request: LaunchJobRequest) -> AnyPublisher<LaunchJobResponse, Error> {
        self.request("/api/jobs/launch", method: .post, parameters: request, encoder: JSONParameterEncoder.default)
            .decode(type: LaunchJobResponse.self, decoder: JSONDecoder.slurmDecoder)
            .receive(on: DispatchQueue.main)
            .eraseToAnyPublisher()
    }
    
    // MARK: - File Browser
    
    func browseFiles(path: String, showHidden: Bool = false) -> AnyPublisher<FileBrowserResponse, Error> {
        let parameters: Parameters = [
            "path": path,
            "show_hidden": showHidden,
            "dirs_only": false
        ]
        
        return request("/api/browse", method: .get, parameters: parameters)
            .decode(type: FileBrowserResponse.self, decoder: JSONDecoder.slurmDecoder)
            .receive(on: DispatchQueue.main)
            .eraseToAnyPublisher()
    }
    
    // MARK: - Private Methods
    
    private func request(
        _ path: String,
        method: HTTPMethod,
        parameters: Parameters? = nil,
        encoder: ParameterEncoder = URLEncodedFormParameterEncoder.default
    ) -> DataPublisher {
        let url = baseURL + path
        
        return session.request(
            url,
            method: method,
            parameters: parameters,
            encoder: encoder,
            headers: headers
        )
        .validate()
        .publishData()
    }
    
    private func request<T: Encodable>(
        _ path: String,
        method: HTTPMethod,
        parameters: T,
        encoder: ParameterEncoder = JSONParameterEncoder.default
    ) -> DataPublisher {
        let url = baseURL + path
        
        return session.request(
            url,
            method: method,
            parameters: parameters,
            encoder: encoder,
            headers: headers
        )
        .validate()
        .publishData()
    }
}

// MARK: - Supporting Types

enum OutputType: String {
    case stdout = "stdout"
    case stderr = "stderr"
    case both = "both"
}

struct JobOutput: Codable {
    let output: String?
    let error: String?
    let outputPath: String?
    let errorPath: String?
    
    enum CodingKeys: String, CodingKey {
        case output
        case error
        case outputPath = "output_path"
        case errorPath = "error_path"
    }
}

struct CancelJobResponse: Codable {
    let success: Bool
    let message: String
    let jobId: String
    let host: String
    
    enum CodingKeys: String, CodingKey {
        case success
        case message
        case jobId = "job_id"
        case host
    }
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

// MARK: - JSON Decoder Extension

extension JSONDecoder {
    static var slurmDecoder: JSONDecoder {
        let decoder = JSONDecoder()
        decoder.dateDecodingStrategy = .custom { decoder in
            let container = try decoder.singleValueContainer()
            let dateString = try container.decode(String.self)
            
            // Try ISO8601 with fractional seconds
            let formatter = ISO8601DateFormatter()
            formatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
            if let date = formatter.date(from: dateString) {
                return date
            }
            
            // Try without fractional seconds
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