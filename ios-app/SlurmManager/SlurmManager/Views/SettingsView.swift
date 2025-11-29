import SwiftUI
import Combine

// MARK: - Enhanced Settings View
struct SettingsView: View {
    @StateObject private var authManager = AuthenticationManager.shared
    @StateObject private var appState = AppState.shared
    @State private var showingLogoutAlert = false
    @State private var showingClearCacheAlert = false
    @State private var showingServerConfig = false
    @State private var showingDiagnostics = false
    @State private var cacheStats: CacheStats?

    var body: some View {
        NavigationView {
            List {
                // Server Connection
                serverSection

                // Security
                securitySection

                // Real-time Updates
                realtimeSection

                // Cache & Storage
                cacheSection

                // Notifications
                notificationSection

                // Appearance
                appearanceSection

                // About
                aboutSection

                // Sign Out
                signOutSection
            }
            .listStyle(.insetGrouped)
            .navigationTitle("Settings")
            .refreshable {
                await loadCacheStats()
            }
            .task {
                await loadCacheStats()
            }
            .alert("Sign Out", isPresented: $showingLogoutAlert) {
                Button("Cancel", role: .cancel) {}
                Button("Sign Out", role: .destructive) {
                    authManager.logout()
                }
            } message: {
                Text("Are you sure you want to sign out? You'll need to enter your credentials again.")
            }
            .alert("Clear Cache", isPresented: $showingClearCacheAlert) {
                Button("Cancel", role: .cancel) {}
                Button("Clear", role: .destructive) {
                    Task {
                        await CacheManager.shared.clearAll()
                        await loadCacheStats()
                        HapticManager.notification(.success)
                        ToastManager.shared.show("Cache cleared", type: .success)
                    }
                }
            } message: {
                Text("This will clear all cached job data. Fresh data will be loaded from the server.")
            }
            .sheet(isPresented: $showingServerConfig) {
                ServerConfigSheet()
            }
            .sheet(isPresented: $showingDiagnostics) {
                DiagnosticsView()
            }
        }
    }

    // MARK: - Server Section
    var serverSection: some View {
        Section {
            // Server URL
            HStack {
                Label("Server", systemImage: "globe")
                Spacer()
                Text(truncatedURL)
                    .foregroundColor(.secondary)
                    .font(.caption)
                    .lineLimit(1)
            }

            // Connection status
            HStack {
                Label("Status", systemImage: connectionIcon)
                Spacer()
                HStack(spacing: 6) {
                    Circle()
                        .fill(connectionColor)
                        .frame(width: 8, height: 8)
                    Text(connectionStatus)
                        .foregroundColor(.secondary)
                        .font(.caption)
                }
            }

            // Configure button
            Button(action: { showingServerConfig = true }) {
                Label("Configure Server", systemImage: "gearshape")
            }

            // Test connection
            Button(action: testConnection) {
                Label("Test Connection", systemImage: "arrow.triangle.2.circlepath")
            }
        } header: {
            Text("Connection")
        }
    }

    // MARK: - Security Section
    var securitySection: some View {
        Section {
            Toggle(isOn: Binding(
                get: { authManager.requiresBiometric },
                set: { authManager.toggleBiometric($0) }
            )) {
                Label("Require Face ID", systemImage: "faceid")
            }

            HStack {
                Label("API Key", systemImage: "key.fill")
                Spacer()
                Text(maskedApiKey)
                    .foregroundColor(.secondary)
                    .font(.caption)
            }
        } header: {
            Text("Security")
        } footer: {
            Text("When enabled, Face ID or Touch ID is required to access the app.")
        }
    }

    // MARK: - Realtime Section
    var realtimeSection: some View {
        Section {
            HStack {
                Label("WebSocket", systemImage: "antenna.radiowaves.left.and.right")
                Spacer()
                HStack(spacing: 6) {
                    if case .connecting = appState.connectionStatus {
                        ProgressView()
                            .scaleEffect(0.7)
                    }
                    Text(appState.connectionStatus.displayText)
                        .foregroundColor(.secondary)
                        .font(.caption)
                }
            }

            Button(action: reconnectWebSocket) {
                Label("Reconnect", systemImage: "arrow.clockwise")
            }
        } header: {
            Text("Real-time Updates")
        } footer: {
            Text("WebSocket provides instant job status updates without polling.")
        }
    }

    // MARK: - Cache Section
    var cacheSection: some View {
        Section {
            if let stats = cacheStats {
                HStack {
                    Label("Cached Jobs", systemImage: "doc.on.doc")
                    Spacer()
                    Text("\(stats.jobCount)")
                        .foregroundColor(.secondary)
                }

                HStack {
                    Label("Cache Size", systemImage: "externaldrive")
                    Spacer()
                    Text(stats.formattedSize)
                        .foregroundColor(.secondary)
                }

                if let lastSync = stats.lastSync {
                    HStack {
                        Label("Last Sync", systemImage: "clock")
                        Spacer()
                        Text(formattedTime(lastSync))
                            .foregroundColor(.secondary)
                    }
                }
            }

            Button(action: { showingClearCacheAlert = true }) {
                Label("Clear Cache", systemImage: "trash")
                    .foregroundColor(.red)
            }
        } header: {
            Text("Cache & Storage")
        }
    }

    // MARK: - Notification Section
    var notificationSection: some View {
        Section {
            NavigationLink {
                NotificationSettingsView()
            } label: {
                Label("Notification Settings", systemImage: "bell.badge")
            }
        } header: {
            Text("Notifications")
        }
    }

    // MARK: - Appearance Section
    var appearanceSection: some View {
        Section {
            NavigationLink {
                AppearanceSettingsView()
            } label: {
                Label("Appearance", systemImage: "paintbrush")
            }
        } header: {
            Text("Display")
        }
    }

    // MARK: - About Section
    var aboutSection: some View {
        Section {
            HStack {
                Label("Version", systemImage: "info.circle")
                Spacer()
                Text(appVersion)
                    .foregroundColor(.secondary)
            }

            HStack {
                Label("Build", systemImage: "hammer")
                Spacer()
                Text(buildNumber)
                    .foregroundColor(.secondary)
            }

            Link(destination: URL(string: "https://github.com/ssync/ssync")!) {
                Label("Documentation", systemImage: "book")
            }

            Link(destination: URL(string: "https://github.com/ssync/ssync/issues")!) {
                Label("Report Issue", systemImage: "exclamationmark.bubble")
            }

            Button(action: { showingDiagnostics = true }) {
                Label("Diagnostics", systemImage: "wrench.and.screwdriver")
            }
        } header: {
            Text("About")
        }
    }

    // MARK: - Sign Out Section
    var signOutSection: some View {
        Section {
            Button(action: { showingLogoutAlert = true }) {
                HStack {
                    Spacer()
                    Label("Sign Out", systemImage: "rectangle.portrait.and.arrow.right")
                        .foregroundColor(.red)
                    Spacer()
                }
            }
        }
    }

    // MARK: - Helper Properties
    var truncatedURL: String {
        let url = authManager.serverURL
        if url.count > 30 {
            return String(url.prefix(27)) + "..."
        }
        return url
    }

    var connectionIcon: String {
        authManager.isAuthenticated ? "checkmark.shield.fill" : "xmark.shield.fill"
    }

    var connectionColor: Color {
        authManager.isAuthenticated ? .green : .red
    }

    var connectionStatus: String {
        authManager.isAuthenticated ? "Authenticated" : "Not Connected"
    }

    var maskedApiKey: String {
        let key = authManager.apiKey
        if key.count > 8 {
            return String(key.prefix(4)) + "••••" + String(key.suffix(4))
        }
        return "••••••••"
    }

    var appVersion: String {
        Bundle.main.infoDictionary?["CFBundleShortVersionString"] as? String ?? "1.0.0"
    }

    var buildNumber: String {
        Bundle.main.infoDictionary?["CFBundleVersion"] as? String ?? "1"
    }

    // MARK: - Actions
    func testConnection() {
        HapticManager.impact(.medium)
        authManager.testConnection { success, error in
            if success {
                HapticManager.notification(.success)
                ToastManager.shared.show("Connection successful", type: .success)
            } else {
                HapticManager.notification(.error)
                ToastManager.shared.show(error ?? "Connection failed", type: .error)
            }
        }
    }

    func reconnectWebSocket() {
        HapticManager.impact(.medium)
        WebSocketManager.shared.reconnect()
    }

    func loadCacheStats() async {
        let stats = await CacheManager.shared.getCacheStats()
        cacheStats = CacheStats(
            jobCount: stats.jobs,
            hostCount: stats.hosts,
            lastSync: stats.lastSync,
            sizeBytes: 0 // Would need to calculate actual size
        )
    }

    func formattedTime(_ date: Date) -> String {
        let formatter = RelativeDateTimeFormatter()
        formatter.unitsStyle = .abbreviated
        return formatter.localizedString(for: date, relativeTo: Date())
    }
}

// MARK: - Cache Stats
struct CacheStats {
    let jobCount: Int
    let hostCount: Int
    let lastSync: Date?
    let sizeBytes: Int64

    var formattedSize: String {
        let formatter = ByteCountFormatter()
        formatter.countStyle = .file
        return formatter.string(fromByteCount: sizeBytes)
    }
}

// MARK: - Server Config Sheet
struct ServerConfigSheet: View {
    @StateObject private var authManager = AuthenticationManager.shared
    @Environment(\.dismiss) var dismiss
    @State private var serverURL: String = ""
    @State private var apiKey: String = ""
    @State private var isTesting = false
    @State private var testResult: String?

    var body: some View {
        NavigationView {
            Form {
                Section {
                    TextField("Server URL", text: $serverURL)
                        .autocapitalization(.none)
                        .keyboardType(.URL)
                        .disableAutocorrection(true)
                } header: {
                    Text("Server")
                } footer: {
                    Text("e.g., https://your-server.com:8042")
                }

                Section {
                    SecureField("API Key", text: $apiKey)
                        .autocapitalization(.none)
                        .disableAutocorrection(true)
                } header: {
                    Text("Authentication")
                }

                if let result = testResult {
                    Section {
                        HStack {
                            Image(systemName: result.contains("success") ? "checkmark.circle.fill" : "xmark.circle.fill")
                                .foregroundColor(result.contains("success") ? .green : .red)
                            Text(result)
                                .font(.caption)
                        }
                    }
                }

                Section {
                    Button(action: testConnection) {
                        HStack {
                            if isTesting {
                                ProgressView()
                                    .scaleEffect(0.8)
                            }
                            Text("Test Connection")
                        }
                    }
                    .disabled(serverURL.isEmpty || apiKey.isEmpty || isTesting)
                }
            }
            .navigationTitle("Server Configuration")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .navigationBarLeading) {
                    Button("Cancel") { dismiss() }
                }

                ToolbarItem(placement: .navigationBarTrailing) {
                    Button("Save") {
                        save()
                    }
                    .fontWeight(.semibold)
                    .disabled(serverURL.isEmpty || apiKey.isEmpty)
                }
            }
            .onAppear {
                serverURL = authManager.serverURL
                apiKey = authManager.apiKey
            }
        }
    }

    func testConnection() {
        isTesting = true
        testResult = nil

        // Temporarily update credentials for testing
        let originalURL = authManager.serverURL
        let originalKey = authManager.apiKey
        authManager.serverURL = serverURL
        authManager.apiKey = apiKey

        authManager.testConnection { success, error in
            isTesting = false
            if success {
                testResult = "Connection successful!"
            } else {
                testResult = error ?? "Connection failed"
            }

            // Restore original if test fails
            if !success {
                authManager.serverURL = originalURL
                authManager.apiKey = originalKey
            }
        }
    }

    func save() {
        authManager.serverURL = serverURL
        authManager.apiKey = apiKey
        _ = authManager.saveCredentials()
        dismiss()
    }
}

// MARK: - Notification Settings View
struct NotificationSettingsView: View {
    @AppStorage("notifyJobComplete") private var notifyJobComplete = true
    @AppStorage("notifyJobFailed") private var notifyJobFailed = true
    @AppStorage("notifyJobStarted") private var notifyJobStarted = false

    var body: some View {
        Form {
            Section {
                Toggle("Job Completed", isOn: $notifyJobComplete)
                Toggle("Job Failed", isOn: $notifyJobFailed)
                Toggle("Job Started", isOn: $notifyJobStarted)
            } header: {
                Text("Job Events")
            } footer: {
                Text("Choose which events trigger notifications")
            }

            Section {
                Button("Open System Settings") {
                    if let url = URL(string: UIApplication.openSettingsURLString) {
                        UIApplication.shared.open(url)
                    }
                }
            } footer: {
                Text("To enable or disable notifications entirely, use system settings.")
            }
        }
        .navigationTitle("Notifications")
        .navigationBarTitleDisplayMode(.inline)
    }
}

// MARK: - Appearance Settings View
struct AppearanceSettingsView: View {
    @AppStorage("preferredColorScheme") private var preferredColorScheme = 0
    @AppStorage("compactJobList") private var compactJobList = false

    var body: some View {
        Form {
            Section {
                Picker("Theme", selection: $preferredColorScheme) {
                    Text("System").tag(0)
                    Text("Light").tag(1)
                    Text("Dark").tag(2)
                }
            } header: {
                Text("Theme")
            }

            Section {
                Toggle("Compact Job List", isOn: $compactJobList)
            } header: {
                Text("Layout")
            } footer: {
                Text("Show more jobs per screen with a compact layout")
            }
        }
        .navigationTitle("Appearance")
        .navigationBarTitleDisplayMode(.inline)
    }
}

// MARK: - Diagnostics View
struct DiagnosticsView: View {
    @Environment(\.dismiss) var dismiss
    @StateObject private var appState = AppState.shared
    @State private var diagnosticText = ""

    var body: some View {
        NavigationView {
            ScrollView {
                VStack(alignment: .leading, spacing: 16) {
                    Text(diagnosticText)
                        .font(.system(.caption, design: .monospaced))
                        .padding()
                        .background(Color(.systemGray6))
                        .cornerRadius(8)
                }
                .padding()
            }
            .navigationTitle("Diagnostics")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .navigationBarLeading) {
                    Button("Done") { dismiss() }
                }

                ToolbarItem(placement: .navigationBarTrailing) {
                    Button(action: copyDiagnostics) {
                        Label("Copy", systemImage: "doc.on.doc")
                    }
                }
            }
            .onAppear {
                generateDiagnostics()
            }
        }
    }

    func generateDiagnostics() {
        let device = UIDevice.current
        let bundle = Bundle.main

        diagnosticText = """
        === SLURM Manager Diagnostics ===

        App Version: \(bundle.infoDictionary?["CFBundleShortVersionString"] ?? "Unknown")
        Build: \(bundle.infoDictionary?["CFBundleVersion"] ?? "Unknown")

        Device: \(device.model)
        iOS Version: \(device.systemVersion)

        Connection Status: \(appState.connectionStatus.displayText)
        Server: \(AuthenticationManager.shared.serverURL)
        Authenticated: \(AuthenticationManager.shared.isAuthenticated)

        WebSocket: \(WebSocketManager.shared.isConnected ? "Connected" : "Disconnected")

        Biometrics Enabled: \(AuthenticationManager.shared.requiresBiometric)

        Generated: \(Date())
        """
    }

    func copyDiagnostics() {
        UIPasteboard.general.string = diagnosticText
        HapticManager.notification(.success)
        ToastManager.shared.show("Copied to clipboard", type: .success)
    }
}

// MARK: - Preview
#Preview {
    SettingsView()
}
