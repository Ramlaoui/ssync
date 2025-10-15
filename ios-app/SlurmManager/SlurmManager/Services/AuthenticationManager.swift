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
            isAuthenticated = true
        }
        
        // Load biometric preference
        requiresBiometric = UserDefaults.standard.bool(forKey: "requires_biometric")
    }
    
    func saveCredentials() -> Bool {
        // Validate inputs
        guard !serverURL.isEmpty, !apiKey.isEmpty else {
            return false
        }
        
        // Save server URL
        UserDefaults.standard.set(serverURL, forKey: "api_base_url")
        
        // Save API key to keychain
        if KeychainManager.shared.saveAPIKey(apiKey) {
            isAuthenticated = true
            
            // Connect WebSocket after authentication
            WebSocketManager.shared.connect()
            
            return true
        }
        
        return false
    }
    
    func logout() {
        // Clear API key
        KeychainManager.shared.deleteAPIKey()
        apiKey = ""
        isAuthenticated = false
        
        // Disconnect WebSocket
        WebSocketManager.shared.disconnect()
        
        // Clear cached data
        JobManager.shared.clearCache()
    }
    
    func authenticateWithBiometrics(completion: @escaping (Bool) -> Void) {
        guard requiresBiometric else {
            completion(true)
            return
        }
        
        let context = LAContext()
        var error: NSError?
        
        if context.canEvaluatePolicy(.deviceOwnerAuthenticationWithBiometrics, error: &error) {
            let reason = "Authenticate to access SLURM Manager"
            
            context.evaluatePolicy(.deviceOwnerAuthenticationWithBiometrics, localizedReason: reason) { success, error in
                DispatchQueue.main.async {
                    completion(success)
                }
            }
        } else {
            // Biometrics not available, fall back to passcode
            if context.canEvaluatePolicy(.deviceOwnerAuthentication, error: &error) {
                let reason = "Authenticate to access SLURM Manager"
                
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
        APIClient.shared.testConnection()
            .sink { result in
                completion(result, result ? nil : "Failed to connect to server")
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