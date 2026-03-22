import Foundation
import Combine
import LocalAuthentication

class AuthenticationManager: ObservableObject {
    static let shared = AuthenticationManager()
    
    @Published var isAuthenticated = false
    @Published var requiresBiometric = false
    @Published var serverURL: String = "https://localhost:8042"
    @Published var apiKey: String = ""
    
    private var cancellables = Set<AnyCancellable>()
    
    private init() {
        loadStoredCredentials()
        setupBiometricPreference()
    }
    
    func loadStoredCredentials() {
        // Load server URL
        if let url = UserDefaults.standard.string(forKey: "api_base_url") {
            serverURL = url
        }
        
        // Load API key from keychain
        if let key = KeychainManager.shared.getAPIKey() {
            apiKey = key
            isAuthenticated = !key.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
        }
        
        // Load biometric preference
        requiresBiometric = UserDefaults.standard.bool(forKey: "requires_biometric")
    }
    
    func saveCredentials() -> Bool {
        let normalizedURL = serverURL.trimmingCharacters(in: .whitespacesAndNewlines)
        let normalizedAPIKey = apiKey.trimmingCharacters(in: .whitespacesAndNewlines)

        // Validate inputs
        guard !normalizedURL.isEmpty, !normalizedAPIKey.isEmpty else {
            return false
        }

        serverURL = normalizedURL
        apiKey = normalizedAPIKey
        
        // Save server URL
        UserDefaults.standard.set(normalizedURL, forKey: "api_base_url")
        
        // Save API key to keychain
        if KeychainManager.shared.saveAPIKey(normalizedAPIKey) {
            isAuthenticated = true
            
            // Connect WebSocket after authentication
            WebSocketManager.shared.connect()
            Task { @MainActor in
                NotificationManager.shared.syncRemoteRegistrationIfPossible()
                NotificationManager.shared.syncNotificationPreferences()
            }
            
            return true
        }
        
        return false
    }
    
    func logout() {
        let currentAPIKey = apiKey.trimmingCharacters(in: .whitespacesAndNewlines)
        if !currentAPIKey.isEmpty {
            Task { @MainActor in
                NotificationManager.shared.unregisterCurrentDevice(apiKeyOverride: currentAPIKey)
            }
        }

        // Clear API key
        KeychainManager.shared.deleteAPIKey()
        apiKey = ""
        isAuthenticated = false
        
        // Disconnect WebSocket
        WebSocketManager.shared.disconnect()
        
        // Clear cached data
        JobManager.shared.clearCache()
        NotificationManager.shared.clearAllNotifications()
        Task { @MainActor in
            LiveActivityManager.shared.endAllActivities()
        }
    }
    
    func authenticateWithBiometrics(completion: @escaping (Bool) -> Void) {
        guard requiresBiometric else {
            completion(true)
            return
        }
        
        let context = LAContext()
        var error: NSError?
        
        if context.canEvaluatePolicy(.deviceOwnerAuthenticationWithBiometrics, error: &error) {
            let reason = "Authenticate to access ssync"
            
            context.evaluatePolicy(.deviceOwnerAuthenticationWithBiometrics, localizedReason: reason) { success, error in
                DispatchQueue.main.async {
                    completion(success)
                }
            }
        } else {
            // Biometrics not available, fall back to passcode
            if context.canEvaluatePolicy(.deviceOwnerAuthentication, error: &error) {
                let reason = "Authenticate to access ssync"
                
                context.evaluatePolicy(.deviceOwnerAuthentication, localizedReason: reason) { success, error in
                    DispatchQueue.main.async {
                        completion(success)
                    }
                }
            } else {
                completion(true) // No authentication available
            }
        }
    }
    
    func testConnection(completion: @escaping (Bool, String?) -> Void) {
        let normalizedURL = serverURL.trimmingCharacters(in: .whitespacesAndNewlines)
        let normalizedAPIKey = apiKey.trimmingCharacters(in: .whitespacesAndNewlines)

        APIClient.shared.testConnection(serverURL: normalizedURL, apiKey: normalizedAPIKey)
            .sink { [weak self] result in
                if result {
                    completion(true, nil)
                } else {
                    let message = APIClient.shared.lastError ?? "Failed to connect to server"
                    self?.isAuthenticated = false
                    completion(false, message)
                }
            }
            .store(in: &cancellables)
    }

    func validateStoredSession() {
        guard !serverURL.isEmpty, !apiKey.isEmpty else {
            isAuthenticated = false
            return
        }

        APIClient.shared.testConnection()
            .sink { [weak self] result in
                self?.isAuthenticated = result
                if result {
                    WebSocketManager.shared.connect()
                    Task { @MainActor in
                        NotificationManager.shared.syncRemoteRegistrationIfPossible()
                        NotificationManager.shared.syncNotificationPreferences()
                    }
                } else {
                    WebSocketManager.shared.disconnect()
                }
            }
            .store(in: &cancellables)
    }
    
    private func setupBiometricPreference() {
        let context = LAContext()
        var error: NSError?
        
        // Check if biometrics are available
        if context.canEvaluatePolicy(.deviceOwnerAuthenticationWithBiometrics, error: &error) {
            // Biometrics available, use stored preference
            requiresBiometric = UserDefaults.standard.bool(forKey: "requires_biometric")
        } else {
            // Biometrics not available
            requiresBiometric = false
            UserDefaults.standard.set(false, forKey: "requires_biometric")
        }
    }
    
    func toggleBiometric(_ enabled: Bool) {
        requiresBiometric = enabled
        UserDefaults.standard.set(enabled, forKey: "requires_biometric")
    }
}
