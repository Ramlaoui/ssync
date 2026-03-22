import SwiftUI
import Combine

struct WatchersView: View {
    @EnvironmentObject var watcherManager: WatcherManager
    @State private var selectedSegment: WatcherSegment = .watchers
    @State private var selectedFilter: WatcherStateFilter = .all
    @State private var searchText = ""
    @State private var showingCreate = false
    @State private var pendingDelete: Watcher?

    var body: some View {
        NavigationView {
            VStack(spacing: 0) {
                Picker("", selection: $selectedSegment) {
                    ForEach(WatcherSegment.allCases) { segment in
                        Text(segment.title).tag(segment)
                    }
                }
                .pickerStyle(SegmentedPickerStyle())
                .padding(.horizontal)
                .padding(.top, 8)

                Divider()

                content
            }
            .navigationTitle("Watchers")
            .toolbar {
                ToolbarItem(placement: .navigationBarLeading) {
                    HStack(spacing: 6) {
                        Circle()
                            .fill(watcherManager.isWebSocketConnected ? Color.green : Color.orange)
                            .frame(width: 8, height: 8)
                        Text(watcherManager.isWebSocketConnected ? "Live" : "Polling")
                            .font(.caption2)
                            .foregroundColor(.secondary)
                    }
                }
                ToolbarItem(placement: .navigationBarTrailing) {
                    HStack(spacing: 16) {
                        Button(action: { Task { await refreshCurrentSegment() } }) {
                            Image(systemName: "arrow.clockwise")
                        }

                        Button(action: { showingCreate = true }) {
                            Image(systemName: "plus")
                        }
                    }
                }
            }
            .searchable(text: $searchText, prompt: "Search watchers...")
            .sheet(isPresented: $showingCreate) {
                NavigationView {
                    WatcherFormView(job: nil)
                }
            }
            .sheet(item: $pendingDelete) { watcher in
                WatcherDeleteConfirmView(watcher: watcher) { confirmed in
                    if confirmed {
                        Task { await deleteWatcher(watcher) }
                    }
                    pendingDelete = nil
                }
            }
            .onAppear {
                watcherManager.connectWebSocket()
                Task { await refreshCurrentSegment() }
            }
            .onDisappear {
                watcherManager.disconnectWebSocket()
            }
            .onChange(of: selectedSegment) { _ in
                Task { await refreshCurrentSegment() }
            }
        }
    }

    @ViewBuilder
    private var content: some View {
        switch selectedSegment {
        case .watchers:
            watchersList
        case .events:
            watcherEventsList
        case .stats:
            watcherStatsView
        }
    }

    private var watchersList: some View {
        Group {
            if watcherManager.isLoading && watcherManager.watchers.isEmpty {
                LoadingView(message: "Loading watchers...")
            } else if filteredWatchers.isEmpty {
                EmptyStateView(
                    icon: "eye.slash",
                    title: "No Watchers",
                    message: selectedFilter == .all ? "No watchers found yet" : "No watchers match the selected filter",
                    action: { showingCreate = true },
                    actionLabel: "Create Watcher"
                )
            } else {
                List {
                    Section {
                        Picker("State", selection: $selectedFilter) {
                            ForEach(WatcherStateFilter.allCases) { filter in
                                Text(filter.title).tag(filter)
                            }
                        }
                        .pickerStyle(.segmented)
                        .padding(.vertical, 4)
                    }

                    ForEach(filteredWatchers) { watcher in
                        NavigationLink(destination: WatcherDetailView(watcher: watcher)) {
                            WatcherRowView(watcher: watcher)
                        }
                        .swipeActions(edge: .leading, allowsFullSwipe: false) {
                            Button {
                                Task { await triggerWatcher(watcher) }
                            } label: {
                                Label("Trigger", systemImage: "bolt.fill")
                            }
                            .tint(.blue)
                        }
                        .swipeActions(edge: .trailing, allowsFullSwipe: false) {
                            if watcher.stateEnum == .active {
                                Button {
                                    Task { await pauseWatcher(watcher) }
                                } label: {
                                    Label("Pause", systemImage: "pause.fill")
                                }
                                .tint(.orange)
                            } else if watcher.stateEnum == .paused {
                                Button {
                                    Task { await resumeWatcher(watcher) }
                                } label: {
                                    Label("Resume", systemImage: "play.fill")
                                }
                                .tint(.green)
                            }

                            Button(role: .destructive) {
                                pendingDelete = watcher
                            } label: {
                                Label("Delete", systemImage: "trash")
                            }
                        }
                    }
                }
                .listStyle(.insetGrouped)
                .refreshable {
                    await refreshCurrentSegment()
                }
            }
        }
    }

    private var watcherEventsList: some View {
        Group {
            if watcherManager.isEventsLoading && watcherManager.events.isEmpty {
                LoadingView(message: "Loading events...")
            } else if watcherManager.events.isEmpty {
                EmptyStateView(
                    icon: "waveform.path.ecg",
                    title: "No Events",
                    message: "Watcher events will appear here as they trigger.",
                    action: nil,
                    actionLabel: nil
                )
            } else {
                List {
                    ForEach(watcherManager.events) { event in
                        WatcherEventRowView(event: event)
                    }
                }
                .listStyle(.insetGrouped)
                .refreshable {
                    await refreshCurrentSegment()
                }
            }
        }
    }

    private var watcherStatsView: some View {
        ScrollView {
            if watcherManager.isStatsLoading && watcherManager.stats == nil {
                LoadingView(message: "Loading stats...")
                    .frame(maxWidth: .infinity, minHeight: 200)
            } else if let stats = watcherManager.stats {
                VStack(spacing: 16) {
                    CardView {
                        VStack(alignment: .leading, spacing: 8) {
                            Text("Overview")
                                .font(.headline)
                            InfoLine(label: "Total Watchers", value: "\(stats.totalWatchers)")
                            InfoLine(label: "Total Events", value: "\(stats.totalEvents)")
                            InfoLine(label: "Events (last hour)", value: "\(stats.eventsLastHour)")
                        }
                    }

                    CardView {
                        VStack(alignment: .leading, spacing: 8) {
                            Text("Watchers By State")
                                .font(.headline)
                            ForEach(stats.watchersByState.sorted(by: { $0.key < $1.key }), id: \.key) { state, count in
                                InfoLine(label: state.capitalized, value: "\(count)")
                            }
                        }
                    }

                    CardView {
                        VStack(alignment: .leading, spacing: 8) {
                            Text("Events By Action")
                                .font(.headline)
                            ForEach(stats.eventsByAction.sorted(by: { $0.key < $1.key }), id: \.key) { action, detail in
                                InfoLine(label: action, value: "\(detail.total) total • \(detail.success) ok • \(detail.failed) failed")
                            }
                        }
                    }

                    if !stats.topWatchers.isEmpty {
                        CardView {
                            VStack(alignment: .leading, spacing: 8) {
                                Text("Top Watchers")
                                    .font(.headline)
                                ForEach(stats.topWatchers) { watcher in
                                    InfoLine(label: watcher.name, value: "\(watcher.eventCount) events")
                                }
                            }
                        }
                    }
                }
                .padding()
            } else {
                EmptyStateView(
                    icon: "chart.bar",
                    title: "No Stats",
                    message: "Stats will appear once watchers are active.",
                    action: nil,
                    actionLabel: nil
                )
                .padding(.top, 40)
            }
        }
        .refreshable {
            await refreshCurrentSegment()
        }
    }

    private var filteredWatchers: [Watcher] {
        watcherManager.watchers.filter { watcher in
            let matchesState = selectedFilter == .all || watcher.stateEnum == selectedFilter.state
            let matchesSearch = searchText.isEmpty || watcher.name.localizedCaseInsensitiveContains(searchText)
                || watcher.jobId.localizedCaseInsensitiveContains(searchText)
                || watcher.hostname.localizedCaseInsensitiveContains(searchText)
                || watcher.pattern.localizedCaseInsensitiveContains(searchText)
            return matchesState && matchesSearch
        }
        .sorted { lhs, rhs in
            (lhs.createdAt ?? .distantPast) > (rhs.createdAt ?? .distantPast)
        }
    }

    @MainActor
    private func refreshCurrentSegment() async {
        switch selectedSegment {
        case .watchers:
            _ = try? await watcherManager.fetchAllWatchers().async()
        case .events:
            _ = try? await watcherManager.fetchWatcherEvents(limit: 50).async()
        case .stats:
            _ = try? await watcherManager.fetchWatcherStats().async()
        }
    }

    @MainActor
    private func pauseWatcher(_ watcher: Watcher) async {
        do {
            _ = try await watcherManager.pauseWatcher(watcher.id).async()
            ToastManager.shared.show("Watcher paused", type: .success)
        } catch {
            ToastManager.shared.show("Failed to pause watcher", type: .error)
        }
    }

    @MainActor
    private func resumeWatcher(_ watcher: Watcher) async {
        do {
            _ = try await watcherManager.resumeWatcher(watcher.id).async()
            ToastManager.shared.show("Watcher resumed", type: .success)
        } catch {
            ToastManager.shared.show("Failed to resume watcher", type: .error)
        }
    }

    @MainActor
    private func triggerWatcher(_ watcher: Watcher) async {
        do {
            let response = try await watcherManager.triggerWatcher(watcher.id).async()
            let message = response.message ?? "Watcher triggered"
            ToastManager.shared.show(message, type: response.success == true ? .success : .warning)
        } catch {
            ToastManager.shared.show("Failed to trigger watcher", type: .error)
        }
    }

    @MainActor
    private func deleteWatcher(_ watcher: Watcher) async {
        do {
            _ = try await watcherManager.deleteWatcher(watcher.id).async()
            ToastManager.shared.show("Watcher deleted", type: .success)
        } catch {
            ToastManager.shared.show("Failed to delete watcher", type: .error)
        }
    }
}

// MARK: - Job Watchers Section

struct JobWatchersView: View {
    let job: Job
    @EnvironmentObject var watcherManager: WatcherManager
    @State private var showingCreate = false
    @State private var pendingDelete: Watcher?

    var body: some View {
        VStack(spacing: 12) {
            HStack {
                Text("Watchers")
                    .font(.headline)
                Spacer()
                Button(action: { showingCreate = true }) {
                    Label("Attach", systemImage: "plus.circle")
                }
            }
            .padding(.horizontal)

            if watcherManager.isLoading && jobWatchers.isEmpty {
                LoadingView(message: "Loading watchers...")
                    .padding()
            } else if jobWatchers.isEmpty {
                EmptyStateView(
                    icon: "eye.slash",
                    title: "No Watchers",
                    message: "Attach a watcher to monitor this job output.",
                    action: { showingCreate = true },
                    actionLabel: "Attach Watcher"
                )
                .padding(.horizontal)
            } else {
                LazyVStack(spacing: 12) {
                    ForEach(jobWatchers) { watcher in
                        WatcherCardView(watcher: watcher, jobId: job.id) { action in
                            handleAction(action, for: watcher)
                        }
                        .contextMenu {
                            Button("Trigger") { Task { await triggerWatcher(watcher) } }
                            if watcher.stateEnum == .active {
                                Button("Pause") { Task { await pauseWatcher(watcher) } }
                            } else if watcher.stateEnum == .paused {
                                Button("Resume") { Task { await resumeWatcher(watcher) } }
                            }
                            Button("Delete", role: .destructive) { pendingDelete = watcher }
                        }
                    }
                }
                .padding(.horizontal)
            }
        }
        .sheet(isPresented: $showingCreate) {
            NavigationView {
                WatcherFormView(job: job)
            }
        }
        .sheet(item: $pendingDelete) { watcher in
            WatcherDeleteConfirmView(watcher: watcher) { confirmed in
                if confirmed {
                    Task { await deleteWatcher(watcher) }
                }
                pendingDelete = nil
            }
        }
        .onAppear {
            Task {
                _ = try? await watcherManager.fetchJobWatchers(jobId: job.id, host: job.host).async()
            }
        }
    }

    private var jobWatchers: [Watcher] {
        watcherManager.watchers.filter { $0.jobId == job.id }
    }

    private func handleAction(_ action: WatcherQuickAction, for watcher: Watcher) {
        switch action {
        case .trigger:
            Task { await triggerWatcher(watcher) }
        case .pause:
            Task { await pauseWatcher(watcher) }
        case .resume:
            Task { await resumeWatcher(watcher) }
        case .delete:
            pendingDelete = watcher
        }
    }

    @MainActor
    private func pauseWatcher(_ watcher: Watcher) async {
        do {
            _ = try await watcherManager.pauseWatcher(watcher.id).async()
            ToastManager.shared.show("Watcher paused", type: .success)
        } catch {
            ToastManager.shared.show("Failed to pause watcher", type: .error)
        }
    }

    @MainActor
    private func resumeWatcher(_ watcher: Watcher) async {
        do {
            _ = try await watcherManager.resumeWatcher(watcher.id).async()
            ToastManager.shared.show("Watcher resumed", type: .success)
        } catch {
            ToastManager.shared.show("Failed to resume watcher", type: .error)
        }
    }

    @MainActor
    private func triggerWatcher(_ watcher: Watcher) async {
        do {
            let response = try await watcherManager.triggerWatcher(watcher.id).async()
            let message = response.message ?? "Watcher triggered"
            ToastManager.shared.show(message, type: response.success == true ? .success : .warning)
        } catch {
            ToastManager.shared.show("Failed to trigger watcher", type: .error)
        }
    }

    @MainActor
    private func deleteWatcher(_ watcher: Watcher) async {
        do {
            _ = try await watcherManager.deleteWatcher(watcher.id).async()
            ToastManager.shared.show("Watcher deleted", type: .success)
        } catch {
            ToastManager.shared.show("Failed to delete watcher", type: .error)
        }
    }
}

// MARK: - Watcher Row

struct WatcherRowView: View {
    let watcher: Watcher

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack {
                Text(watcher.name)
                    .font(.headline)
                    .lineLimit(1)
                Spacer()
                WatcherStateBadge(state: watcher.stateEnum)
            }

            Text(watcher.pattern)
                .font(.caption)
                .foregroundColor(.secondary)
                .lineLimit(2)

            HStack(spacing: 12) {
                Label(watcher.jobId, systemImage: "number")
                    .font(.caption)
                    .foregroundColor(.secondary)
                Label(watcher.hostname, systemImage: "server.rack")
                    .font(.caption)
                    .foregroundColor(.secondary)
                if let count = watcher.triggerCount {
                    Label("\(count)", systemImage: "bolt.fill")
                        .font(.caption)
                        .foregroundColor(.secondary)
                }
            }
        }
        .padding(.vertical, 6)
    }
}

struct WatcherCardView: View {
    let watcher: Watcher
    let jobId: String
    let onAction: (WatcherQuickAction) -> Void

    var body: some View {
        CardView {
            VStack(alignment: .leading, spacing: 12) {
                HStack {
                    Text(watcher.name)
                        .font(.headline)
                    Spacer()
                    WatcherStateBadge(state: watcher.stateEnum)
                }

                Text(watcher.pattern)
                    .font(.caption)
                    .foregroundColor(.secondary)

                HStack(spacing: 16) {
                    if let count = watcher.triggerCount {
                        Label("\(count) triggers", systemImage: "bolt.fill")
                            .font(.caption)
                            .foregroundColor(.secondary)
                    }
                    if let lastCheck = watcher.lastCheckDisplay {
                        Label(lastCheck, systemImage: "clock")
                            .font(.caption)
                            .foregroundColor(.secondary)
                    }
                }

                HStack {
                    Spacer()
                    Button(action: { onAction(.trigger) }) {
                        Label("Trigger", systemImage: "bolt.fill")
                    }
                    .buttonStyle(.bordered)

                    if watcher.stateEnum == .active {
                        Button(action: { onAction(.pause) }) {
                            Label("Pause", systemImage: "pause.fill")
                        }
                        .buttonStyle(.bordered)
                    } else if watcher.stateEnum == .paused {
                        Button(action: { onAction(.resume) }) {
                            Label("Resume", systemImage: "play.fill")
                        }
                        .buttonStyle(.bordered)
                    }
                }
            }
        }
    }
}

enum WatcherQuickAction {
    case trigger
    case pause
    case resume
    case delete
}

struct WatcherStateBadge: View {
    let state: WatcherState

    var body: some View {
        Text(state.displayName)
            .font(.caption2)
            .padding(.horizontal, 8)
            .padding(.vertical, 4)
            .background(stateColor.opacity(0.2))
            .foregroundColor(stateColor)
            .clipShape(Capsule())
    }

    private var stateColor: Color {
        switch state {
        case .active: return .green
        case .paused: return .orange
        case .static: return .gray
        case .completed: return .blue
        case .failed: return .red
        case .disabled: return .gray
        case .triggered: return .purple
        case .pending: return .yellow
        case .unknown: return .secondary
        }
    }
}

// MARK: - Watcher Events

struct WatcherEventRowView: View {
    let event: WatcherEvent

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack {
                Text(event.watcherName)
                    .font(.headline)
                Spacer()
                Image(systemName: event.success ? "checkmark.circle.fill" : "xmark.circle.fill")
                    .foregroundColor(event.success ? .green : .red)
            }

            Text(event.actionType)
                .font(.caption)
                .foregroundColor(.secondary)

            if let matched = event.matchedText, !matched.isEmpty {
                Text(matched)
                    .font(.caption2)
                    .foregroundColor(.secondary)
                    .lineLimit(2)
            }

            HStack(spacing: 12) {
                Label(event.jobId, systemImage: "number")
                    .font(.caption2)
                    .foregroundColor(.secondary)
                if let timestamp = event.timestampDisplay {
                    Label(timestamp, systemImage: "clock")
                        .font(.caption2)
                        .foregroundColor(.secondary)
                }
            }
        }
        .padding(.vertical, 4)
    }
}

// MARK: - Watcher Detail

struct WatcherDetailView: View {
    let watcher: Watcher
    @EnvironmentObject var watcherManager: WatcherManager
    @State private var testText = ""
    @State private var isTriggering = false
    @State private var showingDelete = false

    var body: some View {
        Form {
            Section("Summary") {
                InfoLine(label: "Name", value: watcher.name)
                InfoLine(label: "Job ID", value: watcher.jobId)
                InfoLine(label: "Host", value: watcher.hostname)
                InfoLine(label: "State", value: watcher.stateEnum.displayName)
                if let count = watcher.triggerCount {
                    InfoLine(label: "Triggers", value: "\(count)")
                }
            }

            Section("Pattern") {
                Text(watcher.pattern)
                    .font(.caption)
                if let condition = watcher.condition, !condition.isEmpty {
                    InfoLine(label: "Condition", value: condition)
                }
                if !watcher.captures.isEmpty {
                    InfoLine(label: "Captures", value: watcher.captures.joined(separator: ", "))
                }
            }

            if !watcher.actions.isEmpty {
                Section("Actions") {
                    ForEach(Array(watcher.actions.enumerated()), id: \.offset) { _, action in
                        VStack(alignment: .leading, spacing: 4) {
                            Text(action.type)
                                .font(.subheadline)
                            if let params = action.effectiveParams, !params.isEmpty {
                                Text(params.map { "\($0.key): \($0.value.displayValue)" }.sorted().joined(separator: ", "))
                                    .font(.caption2)
                                    .foregroundColor(.secondary)
                            }
                            if let condition = action.condition, !condition.isEmpty {
                                Text("Condition: \(condition)")
                                    .font(.caption2)
                                    .foregroundColor(.secondary)
                            }
                        }
                    }
                }
            }

            if watcher.hasVariables {
                Section("Variables") {
                    ForEach(watcher.variables?.sorted(by: { $0.key < $1.key }) ?? [], id: \.key) { key, value in
                        InfoLine(label: key, value: value)
                    }
                }
            }

            Section("Manual Trigger") {
                TextField("Optional test text", text: $testText)
                Button {
                    Task { await triggerWatcher() }
                } label: {
                    Label(isTriggering ? "Triggering..." : "Trigger Watcher", systemImage: "bolt.fill")
                }
                .disabled(isTriggering)
            }

            Section("Controls") {
                if watcher.stateEnum == .active {
                    Button("Pause Watcher") {
                        Task { await pauseWatcher() }
                    }
                } else if watcher.stateEnum == .paused {
                    Button("Resume Watcher") {
                        Task { await resumeWatcher() }
                    }
                }

                Button("Delete Watcher", role: .destructive) {
                    showingDelete = true
                }
            }
        }
        .navigationTitle("Watcher")
        .navigationBarTitleDisplayMode(.inline)
        .alert("Delete watcher?", isPresented: $showingDelete) {
            Button("Cancel", role: .cancel) { }
            Button("Delete", role: .destructive) {
                Task { await deleteWatcher() }
            }
        } message: {
            Text("This will delete the watcher and its events.")
        }
    }

    @MainActor
    private func pauseWatcher() async {
        do {
            _ = try await watcherManager.pauseWatcher(watcher.id).async()
            ToastManager.shared.show("Watcher paused", type: .success)
        } catch {
            ToastManager.shared.show("Failed to pause watcher", type: .error)
        }
    }

    @MainActor
    private func resumeWatcher() async {
        do {
            _ = try await watcherManager.resumeWatcher(watcher.id).async()
            ToastManager.shared.show("Watcher resumed", type: .success)
        } catch {
            ToastManager.shared.show("Failed to resume watcher", type: .error)
        }
    }

    @MainActor
    private func triggerWatcher() async {
        isTriggering = true
        defer { isTriggering = false }
        do {
            let response = try await watcherManager.triggerWatcher(watcher.id, testText: testText.isEmpty ? nil : testText).async()
            ToastManager.shared.show(response.message ?? "Watcher triggered", type: response.success == true ? .success : .warning)
        } catch {
            ToastManager.shared.show("Failed to trigger watcher", type: .error)
        }
    }

    @MainActor
    private func deleteWatcher() async {
        do {
            _ = try await watcherManager.deleteWatcher(watcher.id).async()
            ToastManager.shared.show("Watcher deleted", type: .success)
        } catch {
            ToastManager.shared.show("Failed to delete watcher", type: .error)
        }
    }
}

// MARK: - Watcher Form

struct WatcherFormView: View {
    let job: Job?
    @EnvironmentObject var watcherManager: WatcherManager
    @Environment(\.dismiss) private var dismiss

    @State private var mode: WatcherFormMode = .attach
    @State private var jobId: String = ""
    @State private var host: String = ""
    @State private var name: String = ""
    @State private var pattern: String = ""
    @State private var intervalSeconds = "60"
    @State private var capturesText = ""
    @State private var condition = ""
    @State private var outputType: OutputType = .stdout
    @State private var maxTriggers = ""
    @State private var timerModeEnabled = false
    @State private var timerIntervalSeconds = "60"
    @State private var actions: [WatcherActionDraft] = [WatcherActionDraft()]
    @State private var isSaving = false
    @State private var errorMessage: String?

    private var showError: Binding<Bool> {
        Binding(
            get: { errorMessage != nil },
            set: { if !$0 { errorMessage = nil } }
        )
    }

    private var navigationTitle: String {
        job == nil ? "Create Watcher" : "Attach Watcher"
    }

    var body: some View {
        Form {
            targetSection
            basicsSection
            actionsSection
            advancedSection
        }
        .navigationTitle(navigationTitle)
        .navigationBarTitleDisplayMode(.inline)
        .toolbar { formToolbar }
        .onAppear(perform: populateFromJob)
        .alert("Unable to save watcher", isPresented: showError) {
            Button("OK", role: .cancel) { errorMessage = nil }
        } message: {
            Text(errorMessage ?? "")
        }
    }

    @ViewBuilder
    private var targetSection: some View {
        Section("Target") {
            if job == nil {
                Picker("Mode", selection: $mode) {
                    ForEach(WatcherFormMode.allCases) { mode in
                        Text(mode.title).tag(mode)
                    }
                }
                .pickerStyle(.segmented)
            }

            TextField("Job ID", text: $jobId)
                .disabled(job != nil)
            TextField("Host", text: $host)
                .disabled(job != nil)
        }
    }

    @ViewBuilder
    private var basicsSection: some View {
        Section("Basics") {
            TextField("Name", text: $name)
            TextField("Pattern", text: $pattern)
            TextField("Interval (seconds)", text: $intervalSeconds)
                .keyboardType(.numberPad)
            TextField("Captures (comma-separated)", text: $capturesText)
            TextField("Condition (optional)", text: $condition)
            Picker("Output", selection: $outputType) {
                Text("stdout").tag(OutputType.stdout)
                Text("stderr").tag(OutputType.stderr)
                Text("both").tag(OutputType.both)
            }
        }
    }

    @ViewBuilder
    private var actionsSection: some View {
        Section("Actions") {
            ForEach(actions.indices, id: \.self) { index in
                WatcherActionEditorRow(action: $actions[index]) {
                    removeAction(actions[index])
                }
                .padding(.vertical, 4)
            }

            Button("Add Action") {
                actions.append(WatcherActionDraft())
            }
        }
    }

    @ViewBuilder
    private var advancedSection: some View {
        Section("Advanced") {
            TextField("Max Triggers (optional)", text: $maxTriggers)
                .keyboardType(.numberPad)
            Toggle("Enable Timer Mode", isOn: $timerModeEnabled)
            if timerModeEnabled {
                TextField("Timer Interval (seconds)", text: $timerIntervalSeconds)
                    .keyboardType(.numberPad)
            }
        }
    }

    @ToolbarContentBuilder
    private var formToolbar: some ToolbarContent {
        ToolbarItem(placement: .cancellationAction) {
            Button("Cancel") { dismiss() }
        }
        ToolbarItem(placement: .confirmationAction) {
            Button(isSaving ? "Saving..." : "Save") {
                Task { await saveWatcher() }
            }
            .disabled(isSaving)
        }
    }

    private func populateFromJob() {
        guard let job else { return }
        jobId = job.id
        host = job.host
        if job.isRunning || job.isPending {
            mode = .attach
        } else {
            mode = .staticWatcher
        }
    }

    private func removeAction(_ action: WatcherActionDraft) {
        if let index = actions.firstIndex(where: { $0.id == action.id }) {
            actions.remove(at: index)
        }
        if actions.isEmpty {
            actions.append(WatcherActionDraft())
        }
    }

    @MainActor
    private func saveWatcher() async {
        guard !isSaving else { return }
        isSaving = true
        defer { isSaving = false }

        guard !jobId.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else {
            errorMessage = "Job ID is required."
            return
        }
        guard !host.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else {
            errorMessage = "Host is required."
            return
        }
        guard !name.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else {
            errorMessage = "Name is required."
            return
        }
        guard !pattern.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else {
            errorMessage = "Pattern is required."
            return
        }

        let interval = Int(intervalSeconds) ?? 60
        let timerInterval = Int(timerIntervalSeconds) ?? interval
        let maxTriggerValue = Int(maxTriggers)

        let captures = capturesText
            .split(separator: ",")
            .map { $0.trimmingCharacters(in: .whitespacesAndNewlines) }
            .filter { !$0.isEmpty }

        var actionRequests: [WatcherActionRequest] = []
        for draft in actions {
            let params: [String: JSONValue]?
            if draft.paramsJSON.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
                params = nil
            } else if let parsed = JSONValue.decodeObject(from: draft.paramsJSON) {
                params = parsed
            } else {
                errorMessage = "Invalid JSON for action params."
                return
            }
            actionRequests.append(
                WatcherActionRequest(
                    type: draft.type.rawValue,
                    params: params,
                    condition: draft.condition.isEmpty ? nil : draft.condition
                )
            )
        }

        let definition = WatcherDefinitionRequest(
            name: name,
            pattern: pattern,
            intervalSeconds: interval,
            captures: captures,
            condition: condition.isEmpty ? nil : condition,
            actions: actionRequests,
            maxTriggers: maxTriggerValue,
            outputType: outputType.rawValue,
            timerModeEnabled: timerModeEnabled,
            timerIntervalSeconds: timerInterval
        )

        do {
            if mode == .attach {
                _ = try await watcherManager.attachWatchers(jobId: jobId, host: host, definitions: [definition]).async()
                ToastManager.shared.show("Watcher attached", type: .success)
            } else {
                let request = WatcherCreateRequest(
                    jobId: jobId,
                    hostname: host,
                    name: name,
                    pattern: pattern,
                    intervalSeconds: interval,
                    captures: captures,
                    condition: condition.isEmpty ? nil : condition,
                    actions: actionRequests,
                    outputType: outputType.rawValue,
                    timerModeEnabled: timerModeEnabled,
                    timerIntervalSeconds: timerInterval,
                    maxTriggers: maxTriggerValue
                )
                _ = try await watcherManager.createWatcher(request).async()
                ToastManager.shared.show("Watcher created", type: .success)
            }
            dismiss()
        } catch {
            errorMessage = error.localizedDescription
        }
    }
}

struct WatcherActionDraft: Identifiable, Hashable {
    let id = UUID()
    var type: WatcherActionType = .logEvent
    var condition: String = ""
    var paramsJSON: String = "{}"
}

struct WatcherActionEditorRow: View {
    @Binding var action: WatcherActionDraft
    let onRemove: () -> Void

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            Picker("Action", selection: $action.type) {
                ForEach(WatcherActionType.allCases) { type in
                    Text(type.displayName).tag(type)
                }
            }

            TextField("Condition (optional)", text: $action.condition)

            VStack(alignment: .leading, spacing: 6) {
                Text("Params (JSON)")
                    .font(.caption)
                    .foregroundColor(.secondary)
                TextEditor(text: $action.paramsJSON)
                    .frame(minHeight: 80)
                    .font(.system(.caption, design: .monospaced))
                    .overlay(
                        RoundedRectangle(cornerRadius: 6)
                            .stroke(Color(.separator), lineWidth: 1)
                    )
            }

            Button("Remove Action") {
                onRemove()
            }
            .foregroundColor(.red)
        }
    }
}

enum WatcherFormMode: String, CaseIterable, Identifiable {
    case attach
    case staticWatcher

    var id: String { rawValue }

    var title: String {
        switch self {
        case .attach: return "Attach"
        case .staticWatcher: return "Static"
        }
    }
}

// MARK: - Supporting Views

struct WatcherDeleteConfirmView: View {
    let watcher: Watcher
    let onConfirm: (Bool) -> Void

    var body: some View {
        VStack(spacing: 16) {
            Image(systemName: "trash")
                .font(.system(size: 40))
                .foregroundColor(.red)

            Text("Delete Watcher?")
                .font(.headline)

            Text("This will remove \(watcher.name) and its events.")
                .font(.subheadline)
                .foregroundColor(.secondary)
                .multilineTextAlignment(.center)

            HStack(spacing: 12) {
                Button("Cancel") {
                    onConfirm(false)
                }
                .buttonStyle(.bordered)

                Button("Delete") {
                    onConfirm(true)
                }
                .buttonStyle(.borderedProminent)
                .tint(.red)
            }
        }
        .padding()
    }
}

struct InfoLine: View {
    let label: String
    let value: String

    var body: some View {
        HStack {
            Text(label)
                .font(.caption)
                .foregroundColor(.secondary)
            Spacer()
            Text(value)
                .font(.caption)
                .multilineTextAlignment(.trailing)
        }
        .padding(.vertical, 2)
    }
}

enum WatcherSegment: String, CaseIterable, Identifiable {
    case watchers
    case events
    case stats

    var id: String { rawValue }

    var title: String {
        switch self {
        case .watchers: return "Watchers"
        case .events: return "Events"
        case .stats: return "Stats"
        }
    }
}

enum WatcherStateFilter: String, CaseIterable, Identifiable {
    case all
    case active
    case paused
    case `static`
    case completed
    case failed
    case disabled
    case pending
    case triggered

    var id: String { rawValue }

    var title: String {
        rawValue.capitalized
    }

    var state: WatcherState {
        WatcherState.from(rawValue)
    }
}
