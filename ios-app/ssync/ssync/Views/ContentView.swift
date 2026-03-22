import SwiftUI

struct ContentView: View {
    @EnvironmentObject var authManager: AuthenticationManager
    @State private var showingSettings = false
    @State private var isUnlocked = false
    
    var body: some View {
        Group {
            if !authManager.isAuthenticated {
                AuthenticationView()
            } else if authManager.requiresBiometric && !isUnlocked {
                BiometricLockView(isUnlocked: $isUnlocked)
            } else {
                MainTabView()
            }
        }
        .onAppear {
            if authManager.requiresBiometric && authManager.isAuthenticated {
                unlockWithBiometrics()
            }
        }
    }
    
    private func unlockWithBiometrics() {
        authManager.authenticateWithBiometrics { success in
            if success {
                isUnlocked = true
            }
        }
    }
}

struct MainTabView: View {
    @State private var selectedTab = 0
    
    var body: some View {
        TabView(selection: $selectedTab) {
            HomeDashboardView(selectedTab: $selectedTab)
                .tabItem {
                    Label("Home", systemImage: "house.fill")
                }
                .tag(0)

            JobListView()
                .tabItem {
                    Label("Jobs", systemImage: "server.rack")
                }
                .tag(1)

            WatchersView()
                .tabItem {
                    Label("Watchers", systemImage: "eye")
                }
                .tag(2)
            
            HostsView()
                .tabItem {
                    Label("Hosts", systemImage: "network")
                }
                .tag(3)
            
            NavigationView {
                LaunchJobView()
            }
                .tabItem {
                    Label("Launch", systemImage: "play.circle.fill")
                }
                .tag(4)
            
            SettingsView()
                .tabItem {
                    Label("Settings", systemImage: "gear")
                }
                .tag(5)
        }
        .onReceive(NotificationCenter.default.publisher(for: .jobNotificationOpenJob)) { _ in
            selectedTab = 1
        }
    }
}

struct HomeDashboardView: View {
    @Binding var selectedTab: Int

    @EnvironmentObject private var appState: AppState
    @EnvironmentObject private var jobManager: JobManager
    @EnvironmentObject private var watcherManager: WatcherManager

    @State private var hosts: [Host] = []
    @State private var isRefreshing = false
    @State private var homeError: String?

    private var jobs: [Job] {
        jobManager.jobs
    }

    private var runningJobs: [Job] {
        jobs.filter { $0.state == .running }
    }

    private var pendingJobs: [Job] {
        jobs.filter { $0.state == .pending }
    }

    private var completedJobs: [Job] {
        jobs.filter { $0.state.isCompleted }
    }

    var body: some View {
        NavigationView {
            ScrollView {
                VStack(spacing: 16) {
                    CardView {
                        VStack(alignment: .leading, spacing: 12) {
                            HStack {
                                VStack(alignment: .leading, spacing: 4) {
                                    Text("Server")
                                        .font(.caption)
                                        .foregroundColor(.secondary)
                                    Text(AuthenticationManager.shared.serverURL)
                                        .font(.headline)
                                        .lineLimit(1)
                                }
                                Spacer()
                                ConnectionStatusBadge()
                            }

                            Text(summaryLine)
                                .font(.subheadline)
                                .foregroundColor(.secondary)
                        }
                    }

                    HStack(spacing: 12) {
                        SummaryMetricCard(title: "Running", value: "\(runningJobs.count)", tint: .green)
                        SummaryMetricCard(title: "Pending", value: "\(pendingJobs.count)", tint: .orange)
                    }

                    HStack(spacing: 12) {
                        SummaryMetricCard(title: "Hosts", value: "\(hosts.count)", tint: .blue)
                        SummaryMetricCard(
                            title: "Watcher Events",
                            value: watcherManager.stats.map { "\($0.eventsLastHour)" } ?? "—",
                            tint: .purple
                        )
                    }

                    CardView {
                        VStack(alignment: .leading, spacing: 12) {
                            Text("Quick Actions")
                                .font(.headline)

                            Button {
                                selectedTab = 4
                            } label: {
                                DashboardActionLabel(title: "Launch Job", subtitle: "Open the new inline launch flow", icon: "play.circle.fill")
                            }

                            Button {
                                selectedTab = 1
                            } label: {
                                DashboardActionLabel(title: "Review Jobs", subtitle: "Inspect live jobs and outputs", icon: "server.rack")
                            }

                            Button {
                                selectedTab = 2
                            } label: {
                                DashboardActionLabel(title: "Manage Watchers", subtitle: "Review triggers, stats, and actions", icon: "eye")
                            }
                        }
                    }

                    if let latestJob = jobs.sorted(by: { ($0.submitTime ?? .distantPast) > ($1.submitTime ?? .distantPast) }).first {
                        CardView {
                            VStack(alignment: .leading, spacing: 8) {
                                Text("Latest Job")
                                    .font(.headline)
                                Text(latestJob.name)
                                    .font(.subheadline)
                                Text("\(latestJob.state.displayName) on \(latestJob.host)")
                                    .font(.caption)
                                    .foregroundColor(.secondary)
                            }
                        }
                    }

                    if let homeError {
                        CardView {
                            Text(homeError)
                                .font(.caption)
                                .foregroundColor(.red)
                        }
                    }
                }
                .padding()
            }
            .navigationTitle("Home")
            .refreshable {
                await refreshDashboard()
            }
            .task {
                await refreshDashboard()
            }
        }
    }

    private var summaryLine: String {
        "\(runningJobs.count) running, \(pendingJobs.count) pending, \(completedJobs.count) completed jobs in cache"
    }

    @MainActor
    private func refreshDashboard() async {
        if isRefreshing { return }
        isRefreshing = true
        homeError = nil
        defer { isRefreshing = false }

        do {
            async let fetchedHosts = APIClient.shared.getHosts().async()
            async let fetchedJobs = JobManager.shared.fetchJobs(page: 1, pageSize: 50).async()
            async let watcherStats = watcherManager.fetchWatcherStats().async()

            hosts = try await fetchedHosts
            _ = try await fetchedJobs
            _ = try await watcherStats
        } catch {
            homeError = error.localizedDescription
        }
    }
}

private struct SummaryMetricCard: View {
    let title: String
    let value: String
    let tint: Color

    var body: some View {
        CardView {
            VStack(alignment: .leading, spacing: 6) {
                Text(title)
                    .font(.caption)
                    .foregroundColor(.secondary)
                Text(value)
                    .font(.title2)
                    .fontWeight(.semibold)
                    .foregroundColor(tint)
            }
            .frame(maxWidth: .infinity, alignment: .leading)
        }
    }
}

private struct DashboardActionLabel: View {
    let title: String
    let subtitle: String
    let icon: String

    var body: some View {
        HStack(spacing: 12) {
            Image(systemName: icon)
                .foregroundColor(.accentColor)
            VStack(alignment: .leading, spacing: 2) {
                Text(title)
                    .foregroundColor(.primary)
                Text(subtitle)
                    .font(.caption)
                    .foregroundColor(.secondary)
            }
            Spacer()
            Image(systemName: "chevron.right")
                .font(.caption)
                .foregroundColor(.secondary)
        }
    }
}

struct BiometricLockView: View {
    @Binding var isUnlocked: Bool
    @EnvironmentObject var authManager: AuthenticationManager
    
    var body: some View {
        VStack(spacing: 30) {
            Image(systemName: "lock.shield.fill")
                .font(.system(size: 80))
                .foregroundColor(.blue)
            
            Text("ssync")
                .font(.largeTitle)
                .fontWeight(.bold)
            
            Text("Authentication required")
                .font(.subheadline)
                .foregroundColor(.secondary)
            
            Button(action: unlock) {
                Label("Unlock", systemImage: "faceid")
                    .frame(maxWidth: 200)
                    .padding()
                    .background(Color.blue)
                    .foregroundColor(.white)
                    .cornerRadius(10)
            }
        }
        .padding()
        .onAppear {
            unlock()
        }
    }
    
    private func unlock() {
        authManager.authenticateWithBiometrics { success in
            if success {
                isUnlocked = true
            }
        }
    }
}

#Preview {
    ContentView()
        .environmentObject(AuthenticationManager.shared)
        .environmentObject(APIClient.shared)
        .environmentObject(JobManager.shared)
        .environmentObject(WatcherManager.shared)
        .environmentObject(AppState.shared)
        .environmentObject(JobPreferencesManager.shared)
        .environmentObject(LiveActivityManager.shared)
}
