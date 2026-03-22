import SwiftUI

@main
struct ssyncApp: App {
    @StateObject private var authManager = AuthenticationManager.shared
    @StateObject private var apiClient = APIClient.shared
    @StateObject private var jobManager = JobManager.shared
    @StateObject private var watcherManager = WatcherManager.shared
    @StateObject private var appState = AppState.shared
    @StateObject private var jobPreferences = JobPreferencesManager.shared
    @StateObject private var liveActivityManager = LiveActivityManager.shared
    
    var body: some Scene {
        WindowGroup {
            ContentView()
                .environmentObject(authManager)
                .environmentObject(apiClient)
                .environmentObject(jobManager)
                .environmentObject(watcherManager)
                .environmentObject(appState)
                .environmentObject(jobPreferences)
                .environmentObject(liveActivityManager)
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
        NotificationManager.shared.setupNotificationCategories()

        // Start WebSocket connection if authenticated
        if authManager.isAuthenticated {
            authManager.validateStoredSession()
        }
    }
}
