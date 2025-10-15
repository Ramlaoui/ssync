import SwiftUI

@main
struct SlurmManagerApp: App {
    @StateObject private var authManager = AuthenticationManager.shared
    @StateObject private var apiClient = APIClient.shared
    @StateObject private var jobManager = JobManager.shared
    
    var body: some Scene {
        WindowGroup {
            ContentView()
                .environmentObject(authManager)
                .environmentObject(apiClient)
                .environmentObject(jobManager)
                .onAppear {
                    setupApp()
                }
        }
    }
    
    private func setupApp() {
        // Configure app on launch
        authManager.loadStoredCredentials()
        
        // Setup notification handlers
        NotificationManager.shared.requestAuthorization()
        
        // Start WebSocket connection if authenticated
        if authManager.isAuthenticated {
            WebSocketManager.shared.connect()
        }
    }
}