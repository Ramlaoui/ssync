import Foundation
import Combine

final class WatcherManager: NSObject, ObservableObject {
    static let shared = WatcherManager()

    @Published var watchers: [Watcher] = []
    @Published var events: [WatcherEvent] = []
    @Published var stats: WatcherStats?
    @Published var isLoading = false
    @Published var isEventsLoading = false
    @Published var isStatsLoading = false
    @Published var lastError: String?
    @Published var isWebSocketConnected = false
    @Published var webSocketStatus = "Disconnected"

    private var cancellables = Set<AnyCancellable>()
    private var session: URLSession?
    private var socket: URLSessionWebSocketTask?
    private var reconnectTimer: Timer?
    private var reconnectAttempts = 0
    private let maxReconnectAttempts = 5

    private override init() {
        super.init()
    }

    func fetchAllWatchers(state: String? = nil, limit: Int = 100) -> AnyPublisher<[Watcher], Error> {
        isLoading = true
        lastError = nil

        return APIClient.shared.getAllWatchers(state: state, limit: limit)
            .map(\.watchers)
            .handleEvents(
                receiveOutput: { [weak self] watchers in
                    self?.watchers = watchers
                },
                receiveCompletion: { [weak self] completion in
                    self?.isLoading = false
                    if case .failure(let error) = completion {
                        self?.lastError = error.localizedDescription
                    }
                }
            )
            .eraseToAnyPublisher()
    }

    func fetchJobWatchers(jobId: String, host: String? = nil) -> AnyPublisher<[Watcher], Error> {
        isLoading = true
        lastError = nil

        return APIClient.shared.getJobWatchers(jobId: jobId, host: host)
            .map(\.watchers)
            .handleEvents(
                receiveOutput: { [weak self] watchers in
                    guard let self else { return }
                    let filtered = self.watchers.filter { $0.jobId != jobId }
                    self.watchers = filtered + watchers
                },
                receiveCompletion: { [weak self] completion in
                    self?.isLoading = false
                    if case .failure(let error) = completion {
                        self?.lastError = error.localizedDescription
                    }
                }
            )
            .eraseToAnyPublisher()
    }

    func fetchWatcherEvents(jobId: String? = nil, watcherId: Int? = nil, limit: Int = 50) -> AnyPublisher<[WatcherEvent], Error> {
        isEventsLoading = true

        return APIClient.shared.getWatcherEvents(jobId: jobId, watcherId: watcherId, limit: limit)
            .map(\.events)
            .handleEvents(
                receiveOutput: { [weak self] events in
                    self?.events = events
                },
                receiveCompletion: { [weak self] completion in
                    self?.isEventsLoading = false
                    if case .failure(let error) = completion {
                        self?.lastError = error.localizedDescription
                    }
                }
            )
            .eraseToAnyPublisher()
    }

    func fetchWatcherStats() -> AnyPublisher<WatcherStats, Error> {
        isStatsLoading = true

        return APIClient.shared.getWatcherStats()
            .handleEvents(
                receiveOutput: { [weak self] stats in
                    self?.stats = stats
                },
                receiveCompletion: { [weak self] completion in
                    self?.isStatsLoading = false
                    if case .failure(let error) = completion {
                        self?.lastError = error.localizedDescription
                    }
                }
            )
            .eraseToAnyPublisher()
    }

    func pauseWatcher(_ watcherId: Int) -> AnyPublisher<Bool, Error> {
        APIClient.shared.pauseWatcher(watcherId: watcherId)
            .map { _ in true }
            .handleEvents(receiveOutput: { [weak self] _ in
                self?.updateWatcherState(watcherId: watcherId, state: "paused")
            })
            .eraseToAnyPublisher()
    }

    func resumeWatcher(_ watcherId: Int) -> AnyPublisher<Bool, Error> {
        APIClient.shared.resumeWatcher(watcherId: watcherId)
            .map { _ in true }
            .handleEvents(receiveOutput: { [weak self] _ in
                self?.updateWatcherState(watcherId: watcherId, state: "active")
            })
            .eraseToAnyPublisher()
    }

    func triggerWatcher(_ watcherId: Int, testText: String? = nil) -> AnyPublisher<WatcherTriggerResponse, Error> {
        APIClient.shared.triggerWatcher(watcherId: watcherId, testText: testText)
            .handleEvents(receiveOutput: { [weak self] _ in
                guard let self else { return }
                self.fetchWatcherEvents(limit: 50)
                    .sink(receiveCompletion: { _ in }, receiveValue: { _ in })
                    .store(in: &self.cancellables)
            })
            .eraseToAnyPublisher()
    }

    func deleteWatcher(_ watcherId: Int) -> AnyPublisher<Bool, Error> {
        APIClient.shared.deleteWatcher(watcherId: watcherId)
            .map { _ in true }
            .handleEvents(receiveOutput: { [weak self] _ in
                self?.watchers.removeAll { $0.id == watcherId }
            })
            .eraseToAnyPublisher()
    }

    func attachWatchers(jobId: String, host: String, definitions: [WatcherDefinitionRequest]) -> AnyPublisher<WatcherAttachResponse, Error> {
        APIClient.shared.attachWatchers(jobId: jobId, host: host, definitions: definitions)
            .handleEvents(receiveOutput: { [weak self] _ in
                guard let self else { return }
                self.fetchJobWatchers(jobId: jobId, host: host)
                    .sink(receiveCompletion: { _ in }, receiveValue: { _ in })
                    .store(in: &self.cancellables)
            })
            .eraseToAnyPublisher()
    }

    func createWatcher(_ request: WatcherCreateRequest) -> AnyPublisher<Watcher, Error> {
        APIClient.shared.createWatcher(request)
            .handleEvents(receiveOutput: { [weak self] watcher in
                self?.watchers.append(watcher)
            })
            .eraseToAnyPublisher()
    }

    func connectWebSocket() {
        disconnectWebSocket()

        var components = URLComponents(string: "\(baseWebSocketURL)/ws/watchers")
        if let apiKey, !apiKey.isEmpty {
            components?.queryItems = [URLQueryItem(name: "api_key", value: apiKey)]
        }
        guard let url = components?.url else {
            webSocketStatus = "Invalid WebSocket URL"
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
        webSocketStatus = "Connecting..."
        listen()
    }

    func disconnectWebSocket() {
        reconnectTimer?.invalidate()
        reconnectTimer = nil
        socket?.cancel(with: .normalClosure, reason: nil)
        socket = nil
        session?.invalidateAndCancel()
        session = nil
        isWebSocketConnected = false
        webSocketStatus = "Disconnected"
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
                    self.isWebSocketConnected = false
                    self.webSocketStatus = "Error"
                    print("Watcher WebSocket error: \(error.localizedDescription)")
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
              let envelope = decode(WatcherWebSocketEnvelope.self, from: data, label: "envelope") else {
            return
        }

        switch envelope.type {
        case "initial":
            guard let payload = decode(WatcherWebSocketInitial.self, from: data, label: "initial") else {
                return
            }
            DispatchQueue.main.async {
                self.events = payload.events
            }
        case "watcher_event":
            guard let payload = decode(WatcherWebSocketEvent.self, from: data, label: "watcher_event") else {
                return
            }
            DispatchQueue.main.async {
                self.events.insert(payload.event, at: 0)
                self.incrementTriggerCount(watcherId: payload.event.watcherId)
            }
        case "watcher_state_change":
            guard let payload = decode(WatcherWebSocketStateChange.self, from: data, label: "watcher_state_change") else {
                return
            }
            DispatchQueue.main.async {
                self.updateWatcherState(watcherId: payload.watcherId, state: payload.state)
            }
        case "watcher_update":
            guard let payload = decode(WatcherWebSocketUpdate.self, from: data, label: "watcher_update") else {
                return
            }
            DispatchQueue.main.async {
                self.upsertWatcher(payload.watcher)
            }
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
            print("[WatcherWebSocket] Decode failed (\(label)): \(error)")
            print("[WatcherWebSocket] Raw message: \(raw)")
            #endif
            return nil
        }
    }

    private func scheduleReconnect() {
        guard reconnectAttempts < maxReconnectAttempts else {
            webSocketStatus = "Connection failed"
            return
        }

        reconnectAttempts += 1
        let delay = min(pow(2.0, Double(reconnectAttempts)), 30.0)
        webSocketStatus = "Reconnecting in \(Int(delay))s..."

        reconnectTimer?.invalidate()
        reconnectTimer = Timer.scheduledTimer(withTimeInterval: delay, repeats: false) { _ in
            self.connectWebSocket()
        }
    }

    private func updateWatcherState(watcherId: Int, state: String) {
        watchers = watchers.map { watcher in
            guard watcher.id == watcherId else { return watcher }
            return Watcher(
                id: watcher.id,
                jobId: watcher.jobId,
                hostname: watcher.hostname,
                name: watcher.name,
                pattern: watcher.pattern,
                intervalSeconds: watcher.intervalSeconds,
                captures: watcher.captures,
                condition: watcher.condition,
                actions: watcher.actions,
                state: state,
                triggerCount: watcher.triggerCount,
                lastCheck: watcher.lastCheck,
                lastPosition: watcher.lastPosition,
                createdAt: watcher.createdAt,
                timerModeEnabled: watcher.timerModeEnabled,
                timerIntervalSeconds: watcher.timerIntervalSeconds,
                timerModeActive: watcher.timerModeActive,
                variables: watcher.variables,
                isArrayTemplate: watcher.isArrayTemplate,
                arraySpec: watcher.arraySpec,
                parentWatcherId: watcher.parentWatcherId,
                discoveredTaskCount: watcher.discoveredTaskCount,
                expectedTaskCount: watcher.expectedTaskCount
            )
        }
    }

    private func incrementTriggerCount(watcherId: Int) {
        watchers = watchers.map { watcher in
            guard watcher.id == watcherId else { return watcher }
            return Watcher(
                id: watcher.id,
                jobId: watcher.jobId,
                hostname: watcher.hostname,
                name: watcher.name,
                pattern: watcher.pattern,
                intervalSeconds: watcher.intervalSeconds,
                captures: watcher.captures,
                condition: watcher.condition,
                actions: watcher.actions,
                state: watcher.state,
                triggerCount: (watcher.triggerCount ?? 0) + 1,
                lastCheck: watcher.lastCheck,
                lastPosition: watcher.lastPosition,
                createdAt: watcher.createdAt,
                timerModeEnabled: watcher.timerModeEnabled,
                timerIntervalSeconds: watcher.timerIntervalSeconds,
                timerModeActive: watcher.timerModeActive,
                variables: watcher.variables,
                isArrayTemplate: watcher.isArrayTemplate,
                arraySpec: watcher.arraySpec,
                parentWatcherId: watcher.parentWatcherId,
                discoveredTaskCount: watcher.discoveredTaskCount,
                expectedTaskCount: watcher.expectedTaskCount
            )
        }
    }

    private func upsertWatcher(_ watcher: Watcher) {
        if let index = watchers.firstIndex(where: { $0.id == watcher.id }) {
            watchers[index] = watcher
        } else {
            watchers.append(watcher)
        }
    }

    private var baseWebSocketURL: String {
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
}

extension WatcherManager: URLSessionDelegate, URLSessionWebSocketDelegate {
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
            self.isWebSocketConnected = true
            self.webSocketStatus = "Connected"
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
            self.isWebSocketConnected = false
            self.webSocketStatus = "Disconnected"
            if closeCode != .normalClosure {
                self.scheduleReconnect()
            }
        }
    }
}

private struct WatcherWebSocketEnvelope: Decodable {
    let type: String
}

private struct WatcherWebSocketInitial: Decodable {
    let type: String
    let events: [WatcherEvent]
}

private struct WatcherWebSocketEvent: Decodable {
    let type: String
    let event: WatcherEvent
}

private struct WatcherWebSocketStateChange: Decodable {
    let type: String
    let watcherId: Int
    let state: String

    enum CodingKeys: String, CodingKey {
        case type
        case watcherId = "watcher_id"
        case state
    }
}

private struct WatcherWebSocketUpdate: Decodable {
    let type: String
    let watcher: Watcher
}
