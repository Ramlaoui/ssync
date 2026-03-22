//
//  ssyncAppApp.swift
//  ssyncApp
//
//  Created by Ali RAMLAOUI on 04/02/2026.
//

import SwiftUI

@main
struct ssyncAppApp: App {
    @UIApplicationDelegateAdaptor(ssyncAppDelegate.self) private var appDelegate
    @StateObject private var authManager = AuthenticationManager.shared
    @StateObject private var apiClient = APIClient.shared
    @StateObject private var jobManager = JobManager.shared
    @StateObject private var watcherManager = WatcherManager.shared
    @StateObject private var appState = AppState.shared
    @StateObject private var jobPreferences = JobPreferencesManager.shared
    @StateObject private var liveActivityManager = LiveActivityManager.shared
    @StateObject private var notificationManager = NotificationManager.shared

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
                .environmentObject(notificationManager)
                .onAppear {
                    setupApp()
                }
        }
    }

    private func setupApp() {
        authManager.loadStoredCredentials()
        NotificationManager.shared.configure()
        NotificationManager.shared.requestAuthorization()
        if authManager.isAuthenticated {
            authManager.validateStoredSession()
            NotificationManager.shared.syncRemoteRegistrationIfPossible()
        }
    }
}
