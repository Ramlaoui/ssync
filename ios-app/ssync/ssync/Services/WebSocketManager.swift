import Foundation
import Combine

class WebSocketManager: NSObject, ObservableObject {
    static let shared = WebSocketManager()

    @Published var isConnected = false
    @Published var connectionStatus = "Disconnected"

    private var session: URLSession?
    private var socket: URLSessionWebSocketTask?
    private var reconnectTimer: Timer?
    private var reconnectAttempts = 0
    private let maxReconnectAttempts = 5
    private var subscribedJobs = Set<String>()

    private var baseURL: String {
        let httpURL = UserDefaults.standard.string(forKey: "api_base_url") ?? "https://localhost:8042"
        var wsURL = httpURL.replacingOccurrences(of: "https://", with: "wss://")
            .replacingOccurrences(of: "http://", with: "ws://")
        while wsURL.hasSuffix("/") {
            wsURL.removeLast()
        }
        return wsURL
    }

    private var apiKey: String? {
        KeychainManager.shared.getAPIKey()
    }

    private override init() {
        super.init()
    }

    func connect() {
        disconnect()

        var components = URLComponents(string: "\(baseURL)/ws/jobs")
        if let apiKey, !apiKey.isEmpty {
            components?.queryItems = [URLQueryItem(name: "api_key", value: apiKey)]
        }
        guard let url = components?.url else {
            connectionStatus = "Invalid WebSocket URL"
            return
        }

        var request = URLRequest(url: url)
        request.timeoutInterval = 10
        if let apiKey {
            request.setValue(apiKey, forHTTPHeaderField: "X-API-Key")
        }

        let configuration = URLSessionConfiguration.default
        configuration.waitsForConnectivity = true
        session = URLSession(configuration: configuration, delegate: self, delegateQueue: OperationQueue())
        socket = session?.webSocketTask(with: request)
        socket?.resume()
        connectionStatus = "Connecting..."
        listen()
    }

    func disconnect() {
        reconnectTimer?.invalidate()
        reconnectTimer = nil
        socket?.cancel(with: .normalClosure, reason: nil)
        socket = nil
        session?.invalidateAndCancel()
        session = nil
        isConnected = false
        connectionStatus = "Disconnected"
        subscribedJobs.removeAll()
    }

    func subscribeToJob(_ jobId: String) {
        subscribedJobs.insert(jobId)
    }

    func unsubscribeFromJob(_ jobId: String) {
        subscribedJobs.remove(jobId)
    }

    private func listen() {
        socket?.receive { [weak self] result in
            guard let self else { return }
            switch result {
            case .success(let message):
                self.handle(message)
                self.listen()
            case .failure(let error):
                DispatchQueue.main.async {
                    self.isConnected = false
                    self.connectionStatus = "Error"
                    print("WebSocket error: \(error.localizedDescription)")
                    self.scheduleReconnect()
                }
            }
        }
    }

    private func handle(_ message: URLSessionWebSocketTask.Message) {
        let data: Data?
        switch message {
        case .string(let text):
            data = text.data(using: .utf8)
        case .data(let payload):
            data = payload
        @unknown default:
            data = nil
        }

        guard let data,
              let envelope = decode(WebSocketEnvelope.self, from: data, label: "envelope") else {
            return
        }

        switch envelope.type {
        case "batch_update":
            guard let batch = decode(WebSocketBatchUpdate.self, from: data, label: "batch_update") else {
                return
            }
            for update in batch.updates {
                handleJobUpdate(update)
            }
        case "state_change", "job_update", "job_completed":
            guard let update = decode(WebSocketJobUpdate.self, from: data, label: "job_update") else {
                return
            }
            handleJobUpdate(update)
        case "output_update":
            guard let update = decode(WebSocketJobUpdate.self, from: data, label: "output_update") else {
                return
            }
            handleOutputUpdate(update)
        case "initial":
            break
        default:
            break
        }
    }

    private func decode<T: Decodable>(_ type: T.Type, from data: Data, label: String) -> T? {
        do {
            return try JSONDecoder.slurmDecoder.decode(T.self, from: data)
        } catch {
            #if DEBUG
            let raw = String(data: data, encoding: .utf8) ?? "<non-utf8 data>"
            print("[WebSocket] Decode failed (\(label))")
            print("[WebSocket] Target type: \(String(describing: T.self))")
            print("[WebSocket] Error: \(error.localizedDescription)")
            print("[WebSocket] Raw message: \(raw)")
            #endif
            return nil
        }
    }

    private func handleJobUpdate(_ update: WebSocketJobUpdate) {
        guard let job = update.job else { return }

        NotificationCenter.default.post(name: .jobStatusUpdated, object: job)

        Task { @MainActor in
            LiveActivityManager.shared.handleJobUpdate(job)
        }

        if job.state.isCompleted {
            Task { @MainActor in
                NotificationManager.shared.showJobNotification(job: job)
            }
        }
    }

    private func handleOutputUpdate(_ update: WebSocketJobUpdate) {
        guard let jobId = update.jobId, let content = update.content else { return }
        NotificationCenter.default.post(
            name: .jobOutputUpdated,
            object: content,
            userInfo: ["jobId": jobId]
        )
    }

    private func scheduleReconnect() {
        guard reconnectAttempts < maxReconnectAttempts else {
            connectionStatus = "Connection failed"
            return
        }

        reconnectAttempts += 1
        let delay = min(pow(2.0, Double(reconnectAttempts)), 30.0)
        connectionStatus = "Reconnecting in \(Int(delay))s..."

        reconnectTimer?.invalidate()
        reconnectTimer = Timer.scheduledTimer(withTimeInterval: delay, repeats: false) { _ in
            self.connect()
        }
    }
}

extension WebSocketManager: URLSessionDelegate, URLSessionWebSocketDelegate {
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

    func urlSession(_ session: URLSession, webSocketTask: URLSessionWebSocketTask, didOpenWithProtocol protocol: String?) {
        DispatchQueue.main.async {
            self.isConnected = true
            self.connectionStatus = "Connected"
            self.reconnectAttempts = 0
        }
    }

    func urlSession(
        _ session: URLSession,
        webSocketTask: URLSessionWebSocketTask,
        didCloseWith closeCode: URLSessionWebSocketTask.CloseCode,
        reason: Data?
    ) {
        DispatchQueue.main.async {
            self.isConnected = false
            self.connectionStatus = "Disconnected"
            if closeCode != .normalClosure {
                self.scheduleReconnect()
            }
        }
    }
}

private struct WebSocketEnvelope: Codable {
    let type: String
}

private struct WebSocketBatchUpdate: Codable {
    let type: String
    let updates: [WebSocketJobUpdate]
}

private struct WebSocketJobUpdate: Codable {
    let type: String
    let jobId: String?
    let hostname: String?
    let job: Job?
    let content: String?
    let stdout: String?
    let stderr: String?

    enum CodingKeys: String, CodingKey {
        case type
        case jobId = "job_id"
        case hostname
        case job
        case content
        case stdout
        case stderr
    }
}
