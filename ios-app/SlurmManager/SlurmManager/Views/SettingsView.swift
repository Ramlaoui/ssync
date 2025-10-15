import SwiftUI

struct SettingsView: View {
    @EnvironmentObject var authManager: AuthenticationManager
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
}