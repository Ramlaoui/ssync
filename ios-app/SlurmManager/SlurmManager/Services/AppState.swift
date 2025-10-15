import Foundation
import Combine
import SwiftUI

// MARK: - Global App State Manager
@MainActor
class AppState: ObservableObject {
    static let shared = AppState()
    
    // MARK: - Published State
    @Published var isLoading = false
    @Published var currentError: AppError?
    @Published var isConnected = false
    @Published var connectionStatus = ConnectionStatus.disconnected
    @Published var syncStatus = SyncStatus.idle
    @Published var selectedJob: Job?
    @Published var selectedHost: Host?
    
    // MARK: - State Types
    enum ConnectionStatus {
        case connected
        case connecting
        case disconnected
        case error(String)
        
        var displayText: String {
            switch self {
            case .connected: return "Connected"
            case .connecting: return "Connecting..."
            case .disconnected: return "Disconnected"
            case .error(let message): return message
            }
        }
        
        var color: Color {
            switch self {
            case .connected: return .green
            case .connecting: return .orange
            case .disconnected: return .gray
            case .error: return .red
            }
        }
    }
    
    enum SyncStatus {
        case idle
        case syncing
        case success(Date)
        case failed(Error)
        
        var displayText: String {
            switch self {
            case .idle: return "Ready"
            case .syncing: return "Syncing..."
            case .success(let date):
                let formatter = RelativeDateTimeFormatter()
                return "Updated \(formatter.localizedString(for: date, relativeTo: Date()))"
            case .failed: return "Sync failed"
            }
        }
    }
    
    // MARK: - Reactive Publishers
    private var cancellables = Set<AnyCancellable>()
    
    // Loading state combiner
    var isAnyLoading: AnyPublisher<Bool, Never> {
        Publishers.CombineLatest3(
            JobManager.shared.$isLoading,
            APIClient.shared.$isConnected,
            $isLoading
        )
        .map { jobLoading, apiConnected, appLoading in
            jobLoading || !apiConnected || appLoading
        }
        .eraseToAnyPublisher()
    }
    
    private init() {
        setupBindings()
        setupNotifications()
    }
    
    private func setupBindings() {
        // Monitor API connection
        APIClient.shared.$isConnected
            .sink { [weak self] connected in
                self?.isConnected = connected
                self?.connectionStatus = connected ? .connected : .disconnected
            }
            .store(in: &cancellables)
        
        // Monitor WebSocket connection
        WebSocketManager.shared.$isConnected
            .combineLatest(WebSocketManager.shared.$connectionStatus)
            .sink { [weak self] (connected, status) in
                if connected {
                    self?.connectionStatus = .connected
                } else if status.contains("Connecting") {
                    self?.connectionStatus = .connecting
                } else if status.contains("Error") {
                    self?.connectionStatus = .error(status)
                } else {
                    self?.connectionStatus = .disconnected
                }
            }
            .store(in: &cancellables)
    }
    
    private func setupNotifications() {
        // Listen for job updates
        NotificationCenter.default.publisher(for: .jobStatusUpdated)
            .compactMap { $0.object as? Job }
            .sink { [weak self] job in
                self?.handleJobUpdate(job)
            }
            .store(in: &cancellables)
    }
    
    // MARK: - State Management
    func setLoading(_ loading: Bool, message: String? = nil) {
        withAnimation(.easeInOut(duration: 0.2)) {
            isLoading = loading
        }
    }
    
    func setError(_ error: AppError?) {
        withAnimation {
            currentError = error
        }
        
        if error != nil {
            HapticManager.notification(.error)
        }
    }
    
    func clearError() {
        withAnimation {
            currentError = nil
        }
    }
    
    private func handleJobUpdate(_ job: Job) {
        // Update selected job if it matches
        if selectedJob?.id == job.id {
            withAnimation {
                selectedJob = job
            }
        }
        
        // Show notification for job completion
        if job.state.isCompleted {
            ToastManager.shared.show(
                "Job \(job.name) \(job.state.displayName.lowercased())",
                type: job.state == .completed ? .success : .error
            )
        }
    }
    
    // MARK: - Actions
    func refreshAll() async {
        setLoading(true)
        
        do {
            // Refresh hosts
            _ = try await withThrowingTaskGroup(of: Void.self) { group in
                group.addTask {
                    _ = try await APIClient.shared.getHosts().async()
                }
                
                group.addTask {
                    _ = try await JobManager.shared.fetchJobs().async()
                }
                
                try await group.waitForAll()
            }
            
            syncStatus = .success(Date())
        } catch {
            syncStatus = .failed(error)
            setError(AppError.unknown(error))
        }
        
        setLoading(false)
    }
}

// MARK: - Combine Extensions for Async/Await
extension Publisher {
    func async() async throws -> Output {
        try await withCheckedThrowingContinuation { continuation in
            var cancellable: AnyCancellable?
            
            cancellable = first()
                .sink(
                    receiveCompletion: { completion in
                        switch completion {
                        case .finished:
                            break
                        case .failure(let error):
                            continuation.resume(throwing: error)
                        }
                        cancellable?.cancel()
                    },
                    receiveValue: { value in
                        continuation.resume(returning: value)
                    }
                )
        }
    }
}

// MARK: - View Extensions
extension View {
    func withAppState() -> some View {
        self
            .environmentObject(AppState.shared)
            .onReceive(ToastManager.shared.$currentToast) { toast in
                // Handle toast display
            }
    }
    
    func loadingOverlay(_ isLoading: Bool, message: String = "Loading...") -> some View {
        self.overlay(
            Group {
                if isLoading {
                    ZStack {
                        Color.black.opacity(0.3)
                            .ignoresSafeArea()
                            .transition(.opacity)
                        
                        LoadingView(message: message)
                            .transition(.scale.combined(with: .opacity))
                    }
                }
            }
        )
    }
}