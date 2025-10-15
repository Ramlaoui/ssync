import SwiftUI
import Combine

struct JobListView: View {
    @StateObject private var viewModel = JobListViewModel()
    @EnvironmentObject var appState: AppState
    @State private var searchText = ""
    @State private var selectedJob: Job?
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
            .sheet(item: $selectedJob) { job in
                NavigationView {
                    JobDetailView(job: job)
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
        }
        .onDisappear {
            viewModel.stopPolling()
        }
    }
    
    var jobList: some View {
        List {
            ForEach(filteredJobs) { job in
                JobRowView(job: job)
                    .onTapGesture {
                        selectedJob = job
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
        if searchText.isEmpty {
            return viewModel.jobs
        }
        return viewModel.jobs.filter { job in
            job.name.localizedCaseInsensitiveContains(searchText) ||
            job.id.localizedCaseInsensitiveContains(searchText) ||
            job.user.localizedCaseInsensitiveContains(searchText)
        }
    }
}

struct JobRowView: View {
    let job: Job
    
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
                    if job.isRunning, let duration = job.formattedDuration {
                        Label(duration, systemImage: "timer")
                            .font(.caption)
                            .foregroundColor(.blue)
                    }
                    
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
            
            // State badge
            Text(job.state.displayName)
                .font(.caption)
                .fontWeight(.medium)
                .padding(.horizontal, 8)
                .padding(.vertical, 4)
                .background(statusColor.opacity(0.2))
                .foregroundColor(statusColor)
                .cornerRadius(4)
        }
        .padding(.vertical, 4)
    }
    
    var statusColor: Color {
        switch job.state {
        case .running: return .blue
        case .pending: return .orange
        case .completed: return .green
        case .failed, .timeout, .nodeFailure, .outOfMemory: return .red
        case .cancelled: return .gray
        default: return .gray
        }
    }
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
                        ForEach(viewModel.availableHosts, id: \.self) { host in
                            Text(host).tag(host as String?)
                        }
                    }
                }
                
                Section("State") {
                    Picker("State", selection: $viewModel.selectedState) {
                        Text("All States").tag(nil as JobState?)
                        ForEach(JobState.allCases, id: \.self) { state in
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