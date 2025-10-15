import Foundation
import Starscream
import Combine

class WebSocketManager: ObservableObject {
    static let shared = WebSocketManager()
    
    @Published var isConnected = false
    @Published var connectionStatus = "Disconnected"
    
    private var socket: WebSocket?
    private var reconnectTimer: Timer?
    private var reconnectAttempts = 0
    private let maxReconnectAttempts = 5
    private var subscribedJobs = Set<String>()
    
    private var baseURL: String {
        let httpURL = UserDefaults.standard.string(forKey: "api_base_url") ?? "https://localhost:8042"
        return httpURL.replacingOccurrences(of: "https://", with: "wss://")
            .replacingOccurrences(of: "http://", with: "ws://")
    }
    
    private var apiKey: String? {
        KeychainManager.shared.getAPIKey()
    }
    
    private init() {}
    
    func connect() {
        disconnect()
        
        var request = URLRequest(url: URL(string: "\(baseURL)/ws")!)
        request.timeoutInterval = 10
        
        // Add API key header if available
        if let apiKey = apiKey {
            request.setValue(apiKey, forHTTPHeaderField: "X-API-Key")
        }
        
        // Configure WebSocket with SSL settings for self-signed certificates
        let pinner = FoundationSecurity(allowSelfSignedCertificates: true)
        socket = WebSocket(request: request, certPinner: pinner)
        socket?.delegate = self
        socket?.connect()
        
        connectionStatus = "Connecting..."
    }
    
    func disconnect() {
        reconnectTimer?.invalidate()
        reconnectTimer = nil
        socket?.disconnect()
        socket = nil
        isConnected = false
        connectionStatus = "Disconnected"
        subscribedJobs.removeAll()
    }
    
    func subscribeToJob(_ jobId: String) {
        guard isConnected else {
            // Queue for when connected
            subscribedJobs.insert(jobId)
            return
        }
        
        let message = WebSocketMessage(
            type: .subscribe,
            jobId: jobId,
            data: nil
        )
        
        if let data = try? JSONEncoder().encode(message) {
            socket?.write(data: data)
            subscribedJobs.insert(jobId)
        }
    }
    
    func unsubscribeFromJob(_ jobId: String) {
        guard isConnected else {
            subscribedJobs.remove(jobId)
            return
        }
        
        let message = WebSocketMessage(
            type: .unsubscribe,
            jobId: jobId,
            data: nil
        )
        
        if let data = try? JSONEncoder().encode(message) {
            socket?.write(data: data)
            subscribedJobs.remove(jobId)
        }
    }
    
    private func handleMessage(_ text: String) {
        guard let data = text.data(using: .utf8),
              let update = try? JSONDecoder.slurmDecoder.decode(JobUpdate.self, from: data) else {
            return
        }
        
        // Post notification for job updates
        switch update.type {
        case .statusChange:
            if let job = update.job {
                NotificationCenter.default.post(
                    name: .jobStatusUpdated,
                    object: job
                )
                
                // Show local notification if job completed
                if job.state.isCompleted {
                    showJobCompletionNotification(job)
                }
            }
            
        case .outputUpdate:
            if let output = update.output {
                NotificationCenter.default.post(
                    name: .jobOutputUpdated,
                    object: output,
                    userInfo: ["jobId": update.jobId]
                )
            }
            
        case .error:
            if let error = update.error {
                print("WebSocket error: \(error)")
            }
        }
    }
    
    private func resubscribeToJobs() {
        for jobId in subscribedJobs {
            let message = WebSocketMessage(
                type: .subscribe,
                jobId: jobId,
                data: nil
            )
            
            if let data = try? JSONEncoder().encode(message) {
                socket?.write(data: data)
            }
        }
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
    
    private func showJobCompletionNotification(_ job: Job) {
        NotificationManager.shared.showJobNotification(
            title: "Job \(job.state.displayName)",
            body: "\(job.name) (\(job.id)) has \(job.state.displayName.lowercased())",
            jobId: job.id
        )
    }
}

// MARK: - WebSocketDelegate

extension WebSocketManager: WebSocketDelegate {
    func didReceive(event: WebSocketEvent, client: WebSocketClient) {
        switch event {
        case .connected(_):
            DispatchQueue.main.async {
                self.isConnected = true
                self.connectionStatus = "Connected"
                self.reconnectAttempts = 0
                self.resubscribeToJobs()
            }
            
        case .disconnected(let reason, let code):
            DispatchQueue.main.async {
                self.isConnected = false
                self.connectionStatus = "Disconnected"
                
                // Attempt reconnect if not intentional disconnect
                if code != 1000 {
                    self.scheduleReconnect()
                }
            }
            
        case .text(let text):
            handleMessage(text)
            
        case .binary(let data):
            if let text = String(data: data, encoding: .utf8) {
                handleMessage(text)
            }
            
        case .error(let error):
            DispatchQueue.main.async {
                self.connectionStatus = "Error"
                print("WebSocket error: \(error?.localizedDescription ?? "Unknown")")
                self.scheduleReconnect()
            }
            
        case .viabilityChanged(let viable):
            if !viable {
                DispatchQueue.main.async {
                    self.connectionStatus = "Connection unstable"
                }
            }
            
        case .reconnectSuggested(_):
            DispatchQueue.main.async {
                self.scheduleReconnect()
            }
            
        case .cancelled:
            DispatchQueue.main.async {
                self.isConnected = false
                self.connectionStatus = "Cancelled"
            }
            
        case .peerClosed:
            DispatchQueue.main.async {
                self.isConnected = false
                self.connectionStatus = "Connection closed"
                self.scheduleReconnect()
            }
            
        default:
            break
        }
    }
}

// MARK: - WebSocket Message Types

struct WebSocketMessage: Codable {
    enum MessageType: String, Codable {
        case subscribe
        case unsubscribe
        case ping
    }
    
    let type: MessageType
    let jobId: String?
    let data: String?
}

struct JobUpdate: Codable {
    enum UpdateType: String, Codable {
        case statusChange = "status_change"
        case outputUpdate = "output_update"
        case error
    }
    
    let type: UpdateType
    let jobId: String
    let job: Job?
    let output: JobOutput?
    let error: String?
    
    enum CodingKeys: String, CodingKey {
        case type
        case jobId = "job_id"
        case job
        case output
        case error
    }
}