import SwiftUI
import Combine

struct JobListView: View {
    @StateObject private var viewModel = JobListViewModel()
    @EnvironmentObject var appState: AppState
    @EnvironmentObject var jobPreferences: JobPreferencesManager
    @State private var searchText = ""
    @State private var selectedJob: Job?
    @State private var loadingJobId: String?
    @State private var showingFilters = false
    @State private var showingNewJob = false
    @Namespace private var animationNamespace
    
    var body: some View {
        NavigationView {
            ZStack {
                // Background gradient
                LinearGradient(
                    colors: [Color(.systemBackground), Color(.secondarySystemBackground)],
                    startPoint: .top,
                    endPoint: .bottom
                )
                .ignoresSafeArea()
                
                // Content
                if viewModel.isLoading && viewModel.jobs.isEmpty {
                    LoadingView(message: "Loading jobs...")
                        .transition(.scale.combined(with: .opacity))
                } else if let error = viewModel.errorMessage {
                    ErrorView(
                        error: error,
                        retry: {
                            Task { await viewModel.refreshJobs() }
                        }
                    )
                    .transition(.asymmetric(
                        insertion: .scale.combined(with: .opacity),
                        removal: .opacity
                    ))
                } else if viewModel.jobs.isEmpty && !searchText.isEmpty {
                    EmptyStateView(
                        icon: "magnifyingglass",
                        title: "No Results",
                        message: "No jobs match '\(searchText)'",
                        action: { searchText = "" },
                        actionLabel: "Clear Search"
                    )
                    .transition(.opacity)
                } else if viewModel.jobs.isEmpty {
                    EmptyStateView(
                        icon: "tray",
                        title: "No Jobs",
                        message: "No jobs running on selected hosts",
                        action: { showingNewJob = true },
                        actionLabel: "Launch New Job"
                    )
                    .transition(.opacity)
                } else {
                    jobList
                }
                
                // Floating Action Button
                VStack {
                    Spacer()
                    HStack {
                        Spacer()
                        FloatingActionButton(icon: "plus") {
                            showingNewJob = true
                        }
                        .padding()
                    }
                }
            }
            .navigationTitle("Jobs")
            .searchable(text: $searchText, prompt: "Search jobs...")
            .refreshable {
                await viewModel.refreshJobs()
            }
            .toolbar {
                ToolbarItem(placement: .navigationBarLeading) {
                    Menu {
                        // Filter options
                        Section("Quick Filters") {
                            Button(action: { viewModel.applyQuickFilter(.running) }) {
                                Label("Running Jobs", systemImage: "play.circle")
                            }
                            Button(action: { viewModel.applyQuickFilter(.pending) }) {
                                Label("Pending Jobs", systemImage: "clock")
                            }
                            Button(action: { viewModel.applyQuickFilter(.myJobs) }) {
                                Label("My Jobs", systemImage: "person.circle")
                            }
                        }
                        
                        Button(action: { showingFilters = true }) {
                            Label("Advanced Filters", systemImage: "slider.horizontal.3")
                        }
                        
                        if viewModel.hasActiveFilters {
                            Divider()
                            Button(action: { viewModel.resetFilters() }) {
                                Label("Clear Filters", systemImage: "xmark.circle")
                            }
                        }
                    } label: {
                        ZStack {
                            Image(systemName: "line.3.horizontal.decrease.circle")
                            if viewModel.hasActiveFilters {
                                Circle()
                                    .fill(Color.red)
                                    .frame(width: 8, height: 8)
                                    .offset(x: 8, y: -8)
                            }
                        }
                    }
                }
                
                ToolbarItem(placement: .navigationBarTrailing) {
                    HStack(spacing: 16) {
                        // Connection status indicator
                        ConnectionStatusBadge()

                        if !jobPreferences.notificationsEnabledGlobally {
                            Image(systemName: "bell.slash.fill")
                                .foregroundColor(.secondary)
                                .accessibilityLabel("Notifications disabled")
                        }
                        
                        // Refresh button
                        Button(action: {
                            Task {
                                HapticManager.impact(.light)
                                await viewModel.refreshJobs()
                            }
                        }) {
                            Image(systemName: viewModel.isLoading ? "arrow.clockwise.circle.fill" : "arrow.clockwise")
                                .rotationEffect(.degrees(viewModel.isLoading ? 360 : 0))
                                .animation(
                                    viewModel.isLoading ?
                                    Animation.linear(duration: 1).repeatForever(autoreverses: false) :
                                    .default,
                                    value: viewModel.isLoading
                                )
                        }
                        .disabled(viewModel.isLoading)
                    }
                }
            }
            .sheet(isPresented: $showingFilters) {
                JobFilterView(viewModel: viewModel)
            }
            .sheet(item: $selectedJob, onDismiss: {
                loadingJobId = nil
            }) { job in
                NavigationView {
                    JobDetailView(job: job)
                        .onAppear {
                            loadingJobId = nil
                        }
                }
                .presentationDetents([.large])
                .presentationDragIndicator(.visible)
            }
            .sheet(isPresented: $showingNewJob) {
                NavigationView {
                    LaunchJobView()
                }
            }
        }
        .onAppear {
            viewModel.startPolling()
            if let pendingTarget = NotificationManager.shared.consumePendingOpenJob() {
                Task {
                    await openJob(jobId: pendingTarget.jobId, host: pendingTarget.host)
                }
            }
        }
        .onDisappear {
            viewModel.stopPolling()
        }
        .onReceive(NotificationCenter.default.publisher(for: .jobNotificationOpenJob)) { notification in
            Task {
                await handleOpenJobNotification(notification)
            }
        }
    }
    
    var jobList: some View {
                List {
                    if !activeFilterChips.isEmpty {
                        ScrollView(.horizontal, showsIndicators: false) {
                            HStack(spacing: 8) {
                                ForEach(activeFilterChips, id: \.self) { chip in
                                    Text(chip)
                                        .font(.caption)
                                        .padding(.horizontal, 10)
                                        .padding(.vertical, 6)
                                        .background(Color.accentColor.opacity(0.15))
                                        .foregroundColor(.accentColor)
                                        .clipShape(Capsule())
                                }
                            }
                        }
                        .listRowSeparator(.hidden)
                        .listRowBackground(Color.clear)
                    }

                    ForEach(filteredJobs) { job in
                        JobRowView(
                            job: job,
                            isLoading: loadingJobId == job.id,
                            isFavorite: jobPreferences.isFavorite(job),
                            notificationsEnabled: jobPreferences.notificationsEnabled(for: job),
                            liveActivitiesEnabled: jobPreferences.liveActivitiesEnabled(for: job)
                        )
                        .contentShape(Rectangle())
                        .onTapGesture {
                            loadingJobId = job.id
                            HapticManager.impact(.light)
                            selectedJob = job
                        }
                        .swipeActions(edge: .trailing, allowsFullSwipe: false) {
                            Button {
                                jobPreferences.toggleFavorite(job)
                                LiveActivityManager.shared.handleJobUpdate(job)
                            } label: {
                                Label(
                                    jobPreferences.isFavorite(job) ? "Unfavorite" : "Favorite",
                                    systemImage: jobPreferences.isFavorite(job) ? "star.slash.fill" : "star.fill"
                                )
                            }
                            .tint(.yellow)

                            Button {
                                jobPreferences.toggleNotifications(for: job)
                            } label: {
                                Label(
                                    jobPreferences.notificationsEnabled(for: job) ? "Mute" : "Unmute",
                                    systemImage: jobPreferences.notificationsEnabled(for: job) ? "bell.slash.fill" : "bell.fill"
                                )
                            }
                            .tint(jobPreferences.notificationsEnabled(for: job) ? .gray : .green)
                        }
                    }
            
            if viewModel.hasMorePages {
                ProgressView()
                    .frame(maxWidth: .infinity)
                    .onAppear {
                        Task {
                            await viewModel.loadMoreJobs()
                        }
                    }
            }
        }
        .listStyle(PlainListStyle())
    }
    
    var filteredJobs: [Job] {
        let searchedJobs: [Job]
        if searchText.isEmpty {
            searchedJobs = viewModel.jobs
        } else {
            searchedJobs = viewModel.jobs.filter { job in
                job.name.localizedCaseInsensitiveContains(searchText) ||
                job.id.localizedCaseInsensitiveContains(searchText) ||
                (job.user ?? "").localizedCaseInsensitiveContains(searchText)
            }
        }

        return searchedJobs.sorted(by: Job.listSortComparator)
    }

    private var activeFilterChips: [String] {
        var chips: [String] = []

        if let selectedHost = viewModel.selectedHost {
            let hostLabel = viewModel.hostOptions.first(where: { $0.hostname == selectedHost })?.displayName ?? selectedHost
            chips.append("Host: \(hostLabel)")
        }
        if let selectedState = viewModel.selectedState {
            chips.append("State: \(selectedState.displayName)")
        }
        let user = viewModel.userFilter.trimmingCharacters(in: .whitespacesAndNewlines)
        if !user.isEmpty {
            chips.append("User: \(user)")
        }
        if viewModel.showOnlyMyJobs {
            chips.append("My Jobs")
        }

        return chips
    }

    private func hostMatches(_ jobHost: String, targetHost: String) -> Bool {
        let normalizedJob = jobHost.lowercased()
        let normalizedTarget = targetHost.lowercased()
        return normalizedJob == normalizedTarget || normalizedJob.hasPrefix("\(normalizedTarget).")
    }

    @MainActor
    private func handleOpenJobNotification(_ notification: Notification) async {
        guard let userInfo = notification.userInfo else { return }
        guard let jobId = userInfo["jobId"] as? String else { return }
        let host = userInfo["host"] as? String
        await openJob(jobId: jobId, host: host)
    }

    @MainActor
    private func openJob(jobId: String, host: String?) async {
        if let existing = viewModel.jobs.first(where: { job in
            guard job.id == jobId else { return false }
            guard let host else { return true }
            return hostMatches(job.host, targetHost: host)
        }) {
            selectedJob = existing
            return
        }

        do {
            let detail = try await JobManager.shared.fetchJobDetail(jobId: jobId, host: host).async()
            selectedJob = detail.job
        } catch {
            // Ignore; user can refresh manually if the job no longer exists.
        }
    }
}

struct JobRowView: View {
    let job: Job
    let isLoading: Bool
    let isFavorite: Bool
    let notificationsEnabled: Bool
    let liveActivitiesEnabled: Bool
    
    var body: some View {
        HStack {
            // Status indicator
            Circle()
                .fill(statusColor)
                .frame(width: 10, height: 10)
            
            VStack(alignment: .leading, spacing: 4) {
                HStack {
                    Text(job.name)
                        .font(.headline)
                        .lineLimit(1)
                    
                    if isFavorite {
                        Image(systemName: "star.fill")
                            .font(.caption)
                            .foregroundColor(.yellow)
                    }

                    if !notificationsEnabled {
                        Image(systemName: "bell.slash.fill")
                            .font(.caption)
                            .foregroundColor(.secondary)
                    }

                    if liveActivitiesEnabled {
                        Image(systemName: "dot.radiowaves.left.and.right")
                            .font(.caption2)
                            .foregroundColor(.blue)
                    }

                    if job.cached {
                        Image(systemName: "clock.arrow.circlepath")
                            .font(.caption)
                            .foregroundColor(.secondary)
                    }
                }
                
                HStack {
                    Label(job.id, systemImage: "number")
                        .font(.caption)
                        .foregroundColor(.secondary)
                    
                    if let host = job.host.split(separator: ".").first {
                        Label(String(host), systemImage: "server.rack")
                            .font(.caption)
                            .foregroundColor(.secondary)
                    }
                }
                
                HStack {
                    if let partition = job.partition {
                        Label(partition, systemImage: "square.stack.3d.up")
                            .font(.caption)
                            .foregroundColor(.secondary)
                    }
                    
                    if let nodes = job.nodes {
                        Label(nodes, systemImage: "cpu")
                            .font(.caption)
                            .foregroundColor(.secondary)
                    }
                }
            }
            
            Spacer()
            
            VStack(alignment: .trailing, spacing: 6) {
                if isLoading {
                    ProgressView()
                        .scaleEffect(0.7)
                }

                if let duration = job.formattedDuration {
                    Label(duration, systemImage: "timer")
                        .font(.caption.weight(.semibold))
                        .foregroundColor(.blue)
                }

                if let timelineText {
                    Text(timelineText)
                        .font(.caption2)
                        .foregroundColor(.secondary)
                        .multilineTextAlignment(.trailing)
                }
            }
        }
        .padding(.vertical, 4)
    }

    private var timelineText: String? {
        if let startTime = job.startTime {
            return "Started \(Self.timelineFormatter.string(from: startTime))"
        }

        if let submitTime = job.submitTime {
            return "Submitted \(Self.timelineFormatter.string(from: submitTime))"
        }

        return nil
    }
    
    var statusColor: Color {
        switch job.state {
        case .running: return .green
        case .pending: return .orange
        case .completed: return .blue
        case .failed, .timeout: return .red
        case .cancelled: return .gray
        default: return .gray
        }
    }

    private static let timelineFormatter: DateFormatter = {
        let formatter = DateFormatter()
        formatter.doesRelativeDateFormatting = true
        formatter.dateStyle = .medium
        formatter.timeStyle = .short
        return formatter
    }()
}

struct EmptyJobsView: View {
    var body: some View {
        VStack(spacing: 20) {
            Image(systemName: "tray")
                .font(.system(size: 60))
                .foregroundColor(.secondary)
            
            Text("No Jobs")
                .font(.title2)
                .fontWeight(.semibold)
            
            Text("No jobs found on the selected hosts")
                .font(.subheadline)
                .foregroundColor(.secondary)
                .multilineTextAlignment(.center)
        }
        .padding()
    }
}

struct JobFilterView: View {
    @ObservedObject var viewModel: JobListViewModel
    @Environment(\.dismiss) var dismiss
    
    var body: some View {
        NavigationView {
            Form {
                Section("Host") {
                    Picker("Host", selection: $viewModel.selectedHost) {
                        Text("All Hosts").tag(nil as String?)
                        ForEach(viewModel.hostOptions, id: \.id) { host in
                            Text(host.displayName).tag(host.hostname as String?)
                        }
                    }
                }
                
                Section("State") {
                    Picker("State", selection: $viewModel.selectedState) {
                        Text("All States").tag(nil as JobState?)
                        ForEach(JobState.filterOptions, id: \.self) { state in
                            Text(state.displayName).tag(state as JobState?)
                        }
                    }
                }
                
                Section("User") {
                    TextField("Filter by user", text: $viewModel.userFilter)
                        .textInputAutocapitalization(.never)
                        .autocorrectionDisabled()
                }
                
                Section {
                    Toggle("Show only my jobs", isOn: $viewModel.showOnlyMyJobs)
                }
            }
            .navigationTitle("Filters")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .navigationBarLeading) {
                    Button("Reset") {
                        viewModel.resetFilters()
                    }
                }
                
                ToolbarItem(placement: .navigationBarTrailing) {
                    Button("Done") {
                        dismiss()
                        Task {
                            await viewModel.refreshJobs()
                        }
                    }
                }
            }
        }
    }
}
