import SwiftUI

struct SettingsView: View {
    @EnvironmentObject var authManager: AuthenticationManager
    @EnvironmentObject var jobPreferences: JobPreferencesManager
    @EnvironmentObject var liveActivityManager: LiveActivityManager
    @EnvironmentObject var notificationManager: NotificationManager
    @State private var showingLogoutAlert = false
    
    var body: some View {
        NavigationView {
            Form {
                Section("Connection") {
                    HStack {
                        Text("Server")
                        Spacer()
                        Text(authManager.serverURL)
                            .foregroundColor(.secondary)
                            .font(.caption)
                    }
                    
                    HStack {
                        Text("Status")
                        Spacer()
                        if authManager.isAuthenticated {
                            Label("Connected", systemImage: "checkmark.circle.fill")
                                .foregroundColor(.green)
                                .font(.caption)
                        } else {
                            Label("Disconnected", systemImage: "xmark.circle.fill")
                                .foregroundColor(.red)
                                .font(.caption)
                        }
                    }
                }
                
                Section("Security") {
                    Toggle("Require Face ID/Touch ID", isOn: $authManager.requiresBiometric)
                        .onChange(of: authManager.requiresBiometric) { newValue in
                            authManager.toggleBiometric(newValue)
                        }
                }
                
                Section("WebSocket") {
                    HStack {
                        Text("Real-time Updates")
                        Spacer()
                        Text(WebSocketManager.shared.connectionStatus)
                            .foregroundColor(.secondary)
                            .font(.caption)
                    }
                }

                Section("Notifications") {
                    Toggle(
                        "Job Completion Alerts",
                        isOn: Binding(
                            get: { jobPreferences.notificationsEnabledGlobally },
                            set: { jobPreferences.setNotificationsEnabledGlobally($0) }
                        )
                    )

                    Toggle(
                        "Live Activities",
                        isOn: Binding(
                            get: { jobPreferences.liveActivitiesEnabledGlobally },
                            set: { value in
                                jobPreferences.setLiveActivitiesEnabledGlobally(value)
                                if !value {
                                    liveActivityManager.endAllActivities()
                                }
                            }
                        )
                    )
                    .disabled(!liveActivityManager.isSupported)

                    if !liveActivityManager.isSupported {
                        Text("Live Activities are unavailable on this device or currently disabled in system settings.")
                            .font(.caption2)
                            .foregroundColor(.secondary)
                    }

                    HStack {
                        Text("Favorited Jobs")
                        Spacer()
                        Text("\(jobPreferences.favoriteJobKeys.count)")
                            .foregroundColor(.secondary)
                    }

                    HStack {
                        Text("Muted Jobs")
                        Spacer()
                        Text("\(jobPreferences.mutedJobKeys.count)")
                            .foregroundColor(.secondary)
                    }

                    HStack {
                        Text("Permission")
                        Spacer()
                        Text(notificationAuthorizationLabel)
                            .foregroundColor(.secondary)
                            .font(.caption)
                    }

                    HStack {
                        Text("Push Delivery")
                        Spacer()
                        Text(notificationManager.registrationStatusMessage)
                            .foregroundColor(.secondary)
                            .font(.caption)
                            .multilineTextAlignment(.trailing)
                    }

                    Button("Refresh Push Registration") {
                        notificationManager.requestAuthorization()
                        notificationManager.syncRemoteRegistrationIfPossible()
                    }

                    Button("Send Test Push") {
                        notificationManager.sendRemoteTestNotification()
                    }
                    .disabled(!authManager.isAuthenticated || !notificationManager.isRemoteRegistrationSynced)
                }
                
                Section("About") {
                    HStack {
                        Text("Version")
                        Spacer()
                        Text("1.0.0")
                            .foregroundColor(.secondary)
                    }
                    
                    Link("Documentation", destination: URL(string: "https://github.com/yourusername/slurm-manager")!)
                    Link("Report Issue", destination: URL(string: "https://github.com/yourusername/slurm-manager/issues")!)
                }
                
                Section {
                    Button(action: { showingLogoutAlert = true }) {
                        Text("Sign Out")
                            .foregroundColor(.red)
                            .frame(maxWidth: .infinity)
                    }
                }
            }
            .navigationTitle("Settings")
            .alert("Sign Out", isPresented: $showingLogoutAlert) {
                Button("Cancel", role: .cancel) { }
                Button("Sign Out", role: .destructive) {
                    authManager.logout()
                }
            } message: {
                Text("Are you sure you want to sign out?")
            }
        }
    }

    private var notificationAuthorizationLabel: String {
        switch notificationManager.authorizationStatus {
        case .authorized:
            return "Allowed"
        case .provisional:
            return "Provisional"
        case .ephemeral:
            return "Ephemeral"
        case .denied:
            return "Denied"
        case .notDetermined:
            return "Not Requested"
        @unknown default:
            return "Unknown"
        }
    }
}
