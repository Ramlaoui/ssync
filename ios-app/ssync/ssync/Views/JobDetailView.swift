import SwiftUI
import Combine
import zlib

struct JobDetailView: View {
    let job: Job
    @StateObject private var viewModel = JobDetailViewModel()
    @State private var selectedTab = 0
    @Environment(\.dismiss) var dismiss
    @EnvironmentObject var jobPreferences: JobPreferencesManager
    @EnvironmentObject var liveActivityManager: LiveActivityManager
    
    var body: some View {
        ScrollView {
            VStack(spacing: 20) {
                // Job Header
                jobHeader

                if viewModel.isLoadingDetails {
                    HStack(spacing: 8) {
                        ProgressView()
                            .scaleEffect(0.9)
                        Text("Loading job details...")
                            .font(.caption)
                            .foregroundColor(.secondary)
                    }
                    .padding(.horizontal)
                }
                
                // Tab Selection
                Picker("", selection: $selectedTab) {
                    Text("Info").tag(0)
                    Text("Script").tag(1)
                    Text("Output").tag(2)
                    Text("Error").tag(3)
                    Text("Watchers").tag(4)
                }
                .pickerStyle(SegmentedPickerStyle())
                .padding(.horizontal)
                
                // Tab Content
                tabContent
            }
            .padding(.vertical)
        }
        .navigationTitle("Job Details")
        .navigationBarTitleDisplayMode(.inline)
        .toolbar {
            ToolbarItem(placement: .navigationBarTrailing) {
                Menu {
                    Button(action: refreshJob) {
                        Label("Refresh", systemImage: "arrow.clockwise")
                    }
                    
                    if job.isRunning {
                        Button(action: cancelJob) {
                            Label("Cancel Job", systemImage: "xmark.circle")
                        }
                        .foregroundColor(.red)
                    }

                    Button(action: toggleFavorite) {
                        Label(
                            isFavorite ? "Unfavorite" : "Favorite",
                            systemImage: isFavorite ? "star.slash" : "star"
                        )
                    }

                    Button(action: toggleJobNotifications) {
                        Label(
                            notificationsEnabled ? "Mute Notifications" : "Enable Notifications",
                            systemImage: notificationsEnabled ? "bell.slash" : "bell"
                        )
                    }

                    if liveActivityManager.isSupported && (job.isRunning || job.isPending || liveActivitiesEnabled) {
                        Button(action: toggleLiveActivity) {
                            Label(
                                liveActivitiesEnabled ? "Stop Live Activity" : "Start Live Activity",
                                systemImage: liveActivitiesEnabled ? "dot.radiowaves.left.and.right.slash" : "dot.radiowaves.left.and.right"
                            )
                        }
                    }
                    
                    ShareLink(item: shareText) {
                        Label("Share", systemImage: "square.and.arrow.up")
                    }
                } label: {
                    Image(systemName: "ellipsis.circle")
                }
            }
        }
        .onAppear {
            viewModel.loadJobDetail(job)
            WebSocketManager.shared.subscribeToJob(job.id)
        }
        .onDisappear {
            WebSocketManager.shared.unsubscribeFromJob(job.id)
            viewModel.stopStreamingOutput(.stdout)
            viewModel.stopStreamingOutput(.stderr)
        }
    }
    
    var jobHeader: some View {
        VStack(spacing: 12) {
            HStack {
                Circle()
                    .fill(statusColor)
                    .frame(width: 12, height: 12)
                
                Text(job.state.displayName)
                    .font(.headline)
                    .foregroundColor(statusColor)
                
                Spacer()
                
                Text(job.id)
                    .font(.caption)
                    .foregroundColor(.secondary)
            }
            .padding(.horizontal)
            
            Text(job.name)
                .font(.title2)
                .fontWeight(.semibold)
                .multilineTextAlignment(.center)
                .padding(.horizontal)
            
            HStack(spacing: 20) {
                if let duration = job.formattedDuration {
                    Label(duration, systemImage: "timer")
                        .font(.caption)
                }
                
                Label(job.user ?? "Unknown", systemImage: "person")
                    .font(.caption)
                
                Label(job.host.split(separator: ".").first.map(String.init) ?? job.host, 
                      systemImage: "server.rack")
                    .font(.caption)
            }
            .foregroundColor(.secondary)

            HStack(spacing: 10) {
                if isFavorite {
                    Label("Favorite", systemImage: "star.fill")
                        .font(.caption2)
                        .foregroundColor(.yellow)
                }
                if !notificationsEnabled {
                    Label("Muted", systemImage: "bell.slash.fill")
                        .font(.caption2)
                        .foregroundColor(.secondary)
                }
                if liveActivitiesEnabled {
                    Label("Live Activity", systemImage: "dot.radiowaves.left.and.right")
                        .font(.caption2)
                        .foregroundColor(.blue)
                }
            }
        }
        .padding()
        .background(Color(.systemGray6))
        .cornerRadius(12)
        .padding(.horizontal)
    }
    
    @ViewBuilder
    var tabContent: some View {
        switch selectedTab {
        case 0:
            jobInfoView
        case 1:
            scriptView
        case 2:
            outputView(type: .stdout)
        case 3:
            outputView(type: .stderr)
        case 4:
            watchersView
        default:
            EmptyView()
        }
    }

    var watchersView: some View {
        JobWatchersView(job: job)
            .padding(.vertical)
    }
    
    var jobInfoView: some View {
        VStack(spacing: 16) {
            InfoRow(label: "Job ID", value: job.id)
            InfoRow(label: "Name", value: job.name)
            InfoRow(label: "User", value: job.user ?? "Unknown")
            InfoRow(label: "State", value: job.state.displayName)
            
            if let partition = job.partition {
                InfoRow(label: "Partition", value: partition)
            }
            
            if let nodes = job.nodes {
                InfoRow(label: "Nodes", value: nodes)
            }
            
            if let cpus = job.cpus {
                InfoRow(label: "CPUs", value: "\(cpus)")
            }
            
            if let memory = job.memory {
                InfoRow(label: "Memory", value: memory)
            }
            
            if let submitTime = job.submitTime {
                InfoRow(label: "Submitted", value: formatDate(submitTime))
            }
            
            if let startTime = job.startTime {
                InfoRow(label: "Started", value: formatDate(startTime))
            }
            
            if let endTime = job.endTime {
                InfoRow(label: "Ended", value: formatDate(endTime))
            }
            
            if let workDir = sanitized(job.workDir) {
                InfoRow(label: "Work Directory", value: workDir)
            }

            if let stdoutFile = sanitized(job.stdoutFile) {
                InfoRow(label: "Stdout File", value: stdoutFile)
            }

            if let stderrFile = sanitized(job.stderrFile) {
                InfoRow(label: "Stderr File", value: stderrFile)
            }

            if let submitLine = sanitized(job.submitLine) {
                InfoRow(label: "Submit Line", value: submitLine)
            }
        }
        .padding(.horizontal)
    }
    
    var scriptView: some View {
        Group {
            if viewModel.isLoadingScript {
                ProgressView("Loading script...")
                    .frame(maxWidth: .infinity, minHeight: 200)
            } else if let script = viewModel.script {
                ScrollView(.horizontal) {
                    Text(script)
                        .font(.system(.caption, design: .monospaced))
                        .padding()
                        .frame(maxWidth: .infinity, alignment: .leading)
                }
                .background(Color(.systemGray6))
                .cornerRadius(8)
                .padding(.horizontal)
            } else {
                Text("Script not available")
                    .foregroundColor(.secondary)
                    .frame(maxWidth: .infinity, minHeight: 200)
            }
        }
    }
    
    func outputView(type: OutputType) -> some View {
        Group {
            let state = type == .stdout ? viewModel.stdoutViewState : viewModel.stderrViewState

            VStack(spacing: 12) {
                HStack {
                    if let lastUpdated = state.lastUpdated {
                        Text("Last updated \(formatDate(lastUpdated))")
                            .font(.caption)
                            .foregroundColor(.secondary)
                    } else if job.isRunning {
                        Text("Live streaming")
                            .font(.caption)
                            .foregroundColor(.secondary)
                    } else if state.isLoading {
                        Text("Loading...")
                            .font(.caption)
                            .foregroundColor(.secondary)
                    } else {
                        Text("Not loaded")
                            .font(.caption)
                            .foregroundColor(.secondary)
                    }
                    Spacer()
                    if state.receivedKB > 0 {
                        Text("\(state.receivedKB) KB")
                            .font(.caption2)
                            .foregroundColor(.secondary)
                    }
                    Button(action: {
                        if job.isRunning {
                            viewModel.startStreamingOutput(job, outputType: type)
                        } else {
                            viewModel.loadOutputSnapshot(job, outputType: type, forceRefresh: true)
                        }
                    }) {
                        Label("Refresh", systemImage: "arrow.clockwise")
                            .labelStyle(.iconOnly)
                    }
                    .disabled(state.isLoading)
                }
                .padding(.horizontal)

                if let error = state.error {
                    Text(error)
                        .font(.caption)
                        .foregroundColor(.red)
                        .padding(.horizontal)
                }

                if let content = state.content, !content.isEmpty {
                    ScrollView {
                        Text(content)
                            .font(.system(.caption, design: .monospaced))
                            .padding()
                            .frame(maxWidth: .infinity, alignment: .leading)
                    }
                    .background(Color(.systemGray6))
                    .cornerRadius(8)
                    .padding(.horizontal)
                } else if state.isLoading {
                    ProgressView(job.isRunning ? "Streaming output..." : "Loading output...")
                        .frame(maxWidth: .infinity, minHeight: 200)
                } else {
                    Text("No \(type == .stdout ? "output" : "error") available")
                        .foregroundColor(.secondary)
                        .frame(maxWidth: .infinity, minHeight: 200)
                }

                if state.isLoading {
                    ProgressView()
                        .scaleEffect(0.8)
                }

                if let notice = state.notice {
                    Text(notice)
                        .font(.caption)
                        .foregroundColor(.secondary)
                        .padding(.horizontal)
                }
            }
        }
        .onAppear {
            let currentState = type == .stdout ? viewModel.stdoutViewState : viewModel.stderrViewState
            if job.isRunning {
                viewModel.startStreamingOutput(job, outputType: type)
            } else if currentState.lastUpdated == nil && !currentState.isLoading && (currentState.content == nil || currentState.content?.isEmpty == true) {
                viewModel.loadOutputSnapshot(job, outputType: type)
            }
        }
        .onDisappear {
            viewModel.stopStreamingOutput(type)
            viewModel.cancelOutputLoad(type)
        }
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
    
    private func formatDate(_ date: Date) -> String {
        let formatter = DateFormatter()
        formatter.dateStyle = .medium
        formatter.timeStyle = .medium
        return formatter.string(from: date)
    }

    private func sanitized(_ value: String?) -> String? {
        guard let value else { return nil }
        let trimmed = value.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else { return nil }
        if trimmed == "N/A" || trimmed == "None" || trimmed == "UNKNOWN" {
            return nil
        }
        return trimmed
    }
    
    private func refreshJob() {
        viewModel.loadJobDetail(job)
    }
    
    private func cancelJob() {
        viewModel.cancelJob(job)
    }

    private var isFavorite: Bool {
        jobPreferences.isFavorite(job)
    }

    private var notificationsEnabled: Bool {
        jobPreferences.notificationsEnabled(for: job)
    }

    private var liveActivitiesEnabled: Bool {
        jobPreferences.liveActivitiesEnabled(for: job)
    }

    private func toggleFavorite() {
        jobPreferences.toggleFavorite(job)
        LiveActivityManager.shared.handleJobUpdate(job)
    }

    private func toggleJobNotifications() {
        jobPreferences.toggleNotifications(for: job)
    }

    private func toggleLiveActivity() {
        jobPreferences.toggleLiveActivities(for: job)
        liveActivityManager.handleJobUpdate(job)
    }

    private var shareText: String {
        """
        Job: \(job.name)
        ID: \(job.id)
        State: \(job.state.displayName)
        Host: \(job.host)
        """
    }
}

struct InfoRow: View {
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
        .padding(.vertical, 4)
    }
}

@MainActor
class JobDetailViewModel: ObservableObject {
    @Published var jobDetail: JobDetail?
    @Published var script: String?
    @Published var isLoadingDetails = false
    @Published var isLoadingScript = false
    @Published var stdoutViewState = OutputViewState()
    @Published var stderrViewState = OutputViewState()
    
    private var cancellables = Set<AnyCancellable>()
    private var outputCancellables: [OutputType: AnyCancellable] = [:]
    private var stdoutStreamer: OutputStreamClient?
    private var stderrStreamer: OutputStreamClient?
    private var streamStates: [OutputType: StreamState] = [:]
    private var streamTimers: [OutputType: DispatchSourceTimer] = [:]
    private let maxOutputChars = 1_000_000

    struct OutputViewState {
        var content: String? = nil
        var notice: String? = nil
        var error: String? = nil
        var isLoading: Bool = false
        var lastUpdated: Date? = nil
        var receivedKB: Int = 0
    }

    private struct StreamState {
        var compression: String? = nil
        var source: String? = nil
        var originalSize: Int? = nil
        var truncated: Bool = false
        var isBase64: Bool = true
        var gzipDecoder: GzipStreamDecoder? = nil
        var pendingText: String = ""
        var hasDeliveredText: Bool = false
        var lastFlush: Date = .distantPast
        var receivedBytes: Int = 0
        var lastNotice: Date = .distantPast
        var lastChunkAt: Date = .distantPast
    }
    
    func loadJobDetail(_ job: Job) {
        // Load full job details
        isLoadingDetails = true
        JobManager.shared.fetchJobDetail(jobId: job.id, host: job.host)
            .sink(
                receiveCompletion: { [weak self] _ in
                    self?.isLoadingDetails = false
                },
                receiveValue: { [weak self] detail in
                    self?.jobDetail = detail
                    self?.script = detail.script
                }
            )
            .store(in: &cancellables)
        
        // Load script if not included
        loadScript(job)
    }
    
    func loadScript(_ job: Job) {
        isLoadingScript = true
        APIClient.shared.getJobScript(jobId: job.id, host: job.host)
            .sink(
                receiveCompletion: { [weak self] _ in
                    self?.isLoadingScript = false
                },
                receiveValue: { [weak self] response in
                    self?.script = response.scriptContent
                }
            )
            .store(in: &cancellables)
    }
    
    func startStreamingOutput(_ job: Job, outputType: OutputType) {
        guard job.isRunning || job.isCompleted else { return }

        stopStreamingOutput(outputType)
        updateViewState(outputType) { state in
            state.isLoading = true
            state.notice = nil
            state.error = nil
        }
        var state = StreamState()
        state.lastChunkAt = Date()
        streamStates[outputType] = state

        let baseURL = UserDefaults.standard.string(forKey: "api_base_url") ?? "https://localhost:8042"
        var components = URLComponents(string: baseURL)
        components?.path = "/api/jobs/\(job.id)/output/stream"
        components?.queryItems = [
            URLQueryItem(name: "host", value: job.host),
            URLQueryItem(name: "output_type", value: outputType == .stdout ? "stdout" : "stderr")
        ]

        guard let url = components?.url else {
            updateViewState(outputType) { state in
                state.isLoading = false
                state.error = "Invalid output URL"
            }
            return
        }

        let headers: [String: String] = {
            if let apiKey = KeychainManager.shared.getAPIKey() {
                return ["X-API-Key": apiKey]
            }
            return [:]
        }()

        let streamer = OutputStreamClient(url: url, headers: headers) { [weak self] event in
            Task { @MainActor [weak self] in
                self?.handleStreamEvent(event, outputType: outputType)
            }
        }

        if outputType == .stdout {
            stdoutStreamer = streamer
        } else {
            stderrStreamer = streamer
        }

        startStreamTimeoutTimer(outputType)
        streamer.start()
    }

    func stopStreamingOutput(_ outputType: OutputType) {
        if outputType == .stdout {
            stdoutStreamer?.stop()
            stdoutStreamer = nil
        } else {
            stderrStreamer?.stop()
            stderrStreamer = nil
        }
        stopStreamTimeoutTimer(outputType)
        updateViewState(outputType) { state in
            state.isLoading = false
        }
        streamStates.removeValue(forKey: outputType)
    }

    private func handleStreamEvent(_ event: OutputStreamClient.Event, outputType: OutputType) {
        func flushIfNeeded(_ outputType: OutputType, state: inout StreamState, force: Bool = false) {
            let now = Date()
            if force || state.pendingText.count > 8192 || now.timeIntervalSince(state.lastFlush) > 0.25 {
                let text = state.pendingText
                state.pendingText = ""
                state.lastFlush = now
                if !text.isEmpty {
                    if state.hasDeliveredText {
                        appendOutput(text, outputType: outputType)
                    } else {
                        setOutput(text, outputType: outputType)
                        state.hasDeliveredText = true
                    }
                }
            }
        }

        func updateNoticeIfNeeded(_ outputType: OutputType, state: inout StreamState) {
            let now = Date()
            if now.timeIntervalSince(state.lastNotice) > 1.0 {
                state.lastNotice = now
                let kb = state.receivedBytes / 1024
                updateViewState(outputType) { viewState in
                    viewState.receivedKB = kb
                    viewState.notice = "Receiving output... \(kb) KB"
                }
            }
        }

        switch event {
        case .metadata(let metadata):
            var state = streamStates[outputType] ?? StreamState()
            state.compression = metadata.compression
            state.source = metadata.source
            state.originalSize = metadata.originalSize
            state.truncated = metadata.truncated ?? false
            state.isBase64 = !(metadata.source == "cache" && metadata.compression == "none")
            state.gzipDecoder = (metadata.compression == "gzip") ? GzipStreamDecoder() : nil
            state.pendingText = ""
            state.receivedBytes = 0
            state.lastFlush = .distantPast
            state.lastNotice = .distantPast
            state.lastChunkAt = Date()
            streamStates[outputType] = state

            if metadata.truncated == true {
                setNotice("Output was truncated on the server.", outputType: outputType)
            }
        case .chunk(let chunk):
            guard var state = streamStates[outputType] else { return }

            let chunkData: Data?
            if state.isBase64 {
                chunkData = Data(base64Encoded: chunk.data)
            } else {
                chunkData = chunk.data.data(using: .utf8)
            }

            guard let data = chunkData else {
                setNotice("Failed to decode output chunk.", outputType: outputType)
                return
            }

            state.receivedBytes += data.count
            state.lastChunkAt = Date()
            updateNoticeIfNeeded(outputType, state: &state)

            if state.compression == "gzip" || chunk.compressed == true {
                if state.gzipDecoder == nil {
                    state.gzipDecoder = GzipStreamDecoder()
                }
                if let decoded = state.gzipDecoder?.append(data), !decoded.isEmpty {
                    let text = String(data: decoded, encoding: .utf8) ?? ""
                    state.pendingText.append(text)
                }
            } else {
                let text = String(data: data, encoding: .utf8) ?? ""
                state.pendingText.append(text)
            }

            flushIfNeeded(outputType, state: &state)
            streamStates[outputType] = state
        case .truncationNotice(let originalSize):
            setNotice("Output truncated. Original size: \(originalSize) bytes.", outputType: outputType)
        case .complete:
            guard var state = streamStates[outputType] else { return }
            flushIfNeeded(outputType, state: &state, force: true)
            streamStates[outputType] = state

            updateViewState(outputType) { viewState in
                viewState.isLoading = false
                viewState.lastUpdated = Date()
                if let notice = viewState.notice, notice.hasPrefix("Receiving output") {
                    viewState.notice = nil
                }
            }

            streamStates.removeValue(forKey: outputType)
            stopStreamTimeoutTimer(outputType)
            if outputType == .stdout {
                stdoutStreamer?.stop()
                stdoutStreamer = nil
            } else {
                stderrStreamer?.stop()
                stderrStreamer = nil
            }
        case .error(let message):
            updateViewState(outputType) { viewState in
                viewState.error = message
                viewState.isLoading = false
            }
            streamStates.removeValue(forKey: outputType)
            stopStreamTimeoutTimer(outputType)
            if outputType == .stdout {
                stdoutStreamer?.stop()
                stdoutStreamer = nil
            } else {
                stderrStreamer?.stop()
                stderrStreamer = nil
            }
        }
    }

    private func setOutput(_ text: String, outputType: OutputType) {
        let trimmed = trimOutputIfNeeded(text)
        updateViewState(outputType) { state in
            state.content = trimmed
            state.lastUpdated = Date()
        }
    }

    private func appendOutput(_ text: String, outputType: OutputType) {
        updateViewState(outputType) { state in
            var current = state.content ?? ""
            current.append(text)
            state.content = self.trimOutputIfNeeded(current)
        }
    }

    private func setNotice(_ message: String, outputType: OutputType) {
        updateViewState(outputType) { state in
            state.notice = message
        }
    }

    private func trimOutputIfNeeded(_ text: String) -> String {
        guard text.count > maxOutputChars else { return text }
        let startIndex = text.index(text.endIndex, offsetBy: -maxOutputChars)
        return String(text[startIndex...])
    }

    private func updateViewState(_ outputType: OutputType, _ update: @escaping (inout OutputViewState) -> Void) {
        if outputType == .stdout {
            var state = stdoutViewState
            update(&state)
            stdoutViewState = state
        } else {
            var state = stderrViewState
            update(&state)
            stderrViewState = state
        }
    }

    func loadOutputSnapshot(_ job: Job, outputType: OutputType, forceRefresh: Bool = false) {
        outputCancellables[outputType]?.cancel()

        updateViewState(outputType) { state in
            state.isLoading = true
            state.error = nil
            state.notice = nil
        }

        outputCancellables[outputType] = APIClient.shared.getJobOutput(
            jobId: job.id,
            host: job.host,
            outputType: outputType,
            lines: 400,
            metadataOnly: false,
            forceRefresh: forceRefresh
        )
        .sink(
            receiveCompletion: { [weak self] completion in
                guard let self else { return }
                self.outputCancellables[outputType] = nil
                if case let .failure(error) = completion {
                    self.updateViewState(outputType) { state in
                        state.error = self.errorMessage(error)
                        state.isLoading = false
                    }
                }
            },
            receiveValue: { [weak self] output in
                guard let self else { return }
                let text = (outputType == .stdout ? output.stdout : output.stderr) ?? ""
                let trimmed = self.trimOutputIfNeeded(text)
                let metadata = outputType == .stdout ? output.stdoutMetadata : output.stderrMetadata
                let notice = self.noticeForEmptyOutput(job: job, content: trimmed, metadata: metadata, outputType: outputType)

                self.updateViewState(outputType) { state in
                    state.isLoading = false
                    state.content = trimmed.isEmpty ? nil : trimmed
                    state.lastUpdated = Date()
                    state.notice = notice
                    state.receivedKB = trimmed.utf8.count / 1024
                }
            }
        )
    }

    func cancelOutputLoad(_ outputType: OutputType) {
        outputCancellables[outputType]?.cancel()
        outputCancellables[outputType] = nil
        updateViewState(outputType) { state in
            state.isLoading = false
        }
    }

    private func noticeForEmptyOutput(
        job: Job,
        content: String,
        metadata: FileMetadata?,
        outputType: OutputType
    ) -> String? {
        guard content.isEmpty else { return nil }

        if job.isPending {
            return "Job is pending. Output isn't available yet."
        }

        if let metadata, metadata.exists == false {
            if let path = metadata.path, !path.isEmpty {
                return "No \(outputType.rawValue) output found at \(path)."
            }
            return "No \(outputType.rawValue) output file found."
        }

        return nil
    }

    private func errorMessage(_ error: Error) -> String {
        if let decodingError = error as? DecodingError {
            return "Decode error: \(decodingErrorDetails(decodingError))"
        }
        let nsError = error as NSError
        if nsError.domain == NSURLErrorDomain {
            return nsError.localizedDescription
        }
        return error.localizedDescription
    }

    private func decodingErrorDetails(_ error: DecodingError) -> String {
        switch error {
        case .typeMismatch(let type, let context):
            return "Type mismatch (\(type)) at \(codingPath(context.codingPath)): \(context.debugDescription)"
        case .valueNotFound(let type, let context):
            return "Value not found (\(type)) at \(codingPath(context.codingPath)): \(context.debugDescription)"
        case .keyNotFound(let key, let context):
            return "Key '\(key.stringValue)' not found at \(codingPath(context.codingPath)): \(context.debugDescription)"
        case .dataCorrupted(let context):
            return "Data corrupted at \(codingPath(context.codingPath)): \(context.debugDescription)"
        @unknown default:
            return "Unknown decoding error"
        }
    }

    private func codingPath(_ path: [CodingKey]) -> String {
        guard !path.isEmpty else { return "<root>" }
        return path.map { $0.stringValue }.joined(separator: ".")
    }

    private func startStreamTimeoutTimer(_ outputType: OutputType) {
        stopStreamTimeoutTimer(outputType)
        let timer = DispatchSource.makeTimerSource(queue: DispatchQueue.main)
        timer.schedule(deadline: .now() + 5, repeating: 5)
        timer.setEventHandler { [weak self] in
            Task { @MainActor [weak self] in
                self?.checkStreamTimeout(outputType)
            }
        }
        streamTimers[outputType] = timer
        timer.resume()
    }

    private func stopStreamTimeoutTimer(_ outputType: OutputType) {
        if let timer = streamTimers[outputType] {
            timer.cancel()
            streamTimers.removeValue(forKey: outputType)
        }
    }

    private func checkStreamTimeout(_ outputType: OutputType) {
        guard let state = streamStates[outputType] else { return }

        let now = Date()
        let lastActivity = state.lastChunkAt
        if lastActivity == .distantPast {
            return
        }
        if now.timeIntervalSince(lastActivity) > 30 {
            handleStreamTimeout(outputType)
        }
    }

    private func handleStreamTimeout(_ outputType: OutputType) {
        updateViewState(outputType) { state in
            state.error = "Output request timed out."
            state.isLoading = false
        }

        if outputType == .stdout {
            stdoutStreamer?.stop()
            stdoutStreamer = nil
        } else {
            stderrStreamer?.stop()
            stderrStreamer = nil
        }

        streamStates.removeValue(forKey: outputType)
        stopStreamTimeoutTimer(outputType)
    }
    
    func cancelJob(_ job: Job) {
        JobManager.shared.cancelJob(jobId: job.id, host: job.host)
            .sink(
                receiveCompletion: { _ in },
                receiveValue: { success in
                    if success {
                        // Job cancelled successfully
                    }
                }
            )
            .store(in: &cancellables)
    }
}

// MARK: - Output Streaming

final class OutputStreamClient: NSObject, URLSessionDataDelegate {
    enum Event {
        case metadata(Metadata)
        case chunk(Chunk)
        case complete
        case error(String)
        case truncationNotice(Int)
    }

    struct Metadata: Decodable {
        let type: String
        let outputType: String?
        let jobId: String?
        let host: String?
        let originalSize: Int?
        let compression: String?
        let source: String?
        let truncated: Bool?

        enum CodingKeys: String, CodingKey {
            case type
            case outputType = "output_type"
            case jobId = "job_id"
            case host
            case originalSize = "original_size"
            case compression
            case source
            case truncated
        }
    }

    struct Chunk: Decodable {
        let type: String
        let index: Int?
        let data: String
        let compressed: Bool?
    }

    private struct StreamEvent: Decodable {
        let type: String
        let index: Int?
        let data: String?
        let compressed: Bool?
        let message: String?
        let outputType: String?
        let compression: String?
        let source: String?
        let originalSize: Int?
        let truncated: Bool?
        let truncatedSize: Int?
        let host: String?
        let jobId: String?

        enum CodingKeys: String, CodingKey {
            case type
            case index
            case data
            case compressed
            case message
            case outputType = "output_type"
            case compression
            case source
            case originalSize = "original_size"
            case truncated
            case truncatedSize = "truncated_size"
            case host
            case jobId = "job_id"
        }
    }

    private let url: URL
    private let headers: [String: String]
    private let onEvent: (Event) -> Void

    private var buffer = ""
    private var session: URLSession?
    private var task: URLSessionDataTask?

    init(url: URL, headers: [String: String], onEvent: @escaping (Event) -> Void) {
        self.url = url
        self.headers = headers
        self.onEvent = onEvent
        super.init()
    }

    func start() {
        let configuration = URLSessionConfiguration.default
        configuration.timeoutIntervalForRequest = 30
        configuration.timeoutIntervalForResource = 0
        session = URLSession(configuration: configuration, delegate: self, delegateQueue: nil)

        var request = URLRequest(url: url)
        request.setValue("text/event-stream", forHTTPHeaderField: "Accept")
        for (key, value) in headers {
            request.setValue(value, forHTTPHeaderField: key)
        }

        task = session?.dataTask(with: request)
        task?.resume()
    }

    func stop() {
        task?.cancel()
        session?.invalidateAndCancel()
        task = nil
        session = nil
        buffer = ""
    }

    func urlSession(_ session: URLSession, dataTask: URLSessionDataTask, didReceive data: Data) {
        let chunk = String(decoding: data, as: UTF8.self)
        buffer.append(chunk)
        parseBuffer()
    }

    func urlSession(_ session: URLSession, dataTask: URLSessionDataTask, didReceive response: URLResponse,
                    completionHandler: @escaping (URLSession.ResponseDisposition) -> Void) {
        if let http = response as? HTTPURLResponse, http.statusCode >= 300 {
            onEvent(.error("HTTP \(http.statusCode)"))
            completionHandler(.cancel)
            return
        }
        completionHandler(.allow)
    }

    func urlSession(_ session: URLSession, task: URLSessionTask, didCompleteWithError error: Error?) {
        if let error = error as NSError? {
            if error.domain == NSURLErrorDomain && error.code == NSURLErrorCancelled {
                return
            }
            onEvent(.error(error.localizedDescription))
        }
    }

    private func parseBuffer() {
        while let range = buffer.range(of: "\n\n") {
            let eventString = String(buffer[..<range.lowerBound])
            buffer = String(buffer[range.upperBound...])
            handleEvent(eventString)
        }
    }

    func urlSession(_ session: URLSession, didReceive challenge: URLAuthenticationChallenge,
                    completionHandler: @escaping (URLSession.AuthChallengeDisposition, URLCredential?) -> Void) {
        guard challenge.protectionSpace.authenticationMethod == NSURLAuthenticationMethodServerTrust,
              let trust = challenge.protectionSpace.serverTrust,
              let host = challenge.protectionSpace.host.lowercased() as String? else {
            completionHandler(.performDefaultHandling, nil)
            return
        }

        if isLocalHost(host) {
            completionHandler(.useCredential, URLCredential(trust: trust))
        } else {
            completionHandler(.performDefaultHandling, nil)
        }
    }

    private func handleEvent(_ eventString: String) {
        let lines = eventString.split(separator: "\n")
        var dataLines: [String] = []

        for line in lines {
            if line.hasPrefix("data:") {
                let value = line.dropFirst(5)
                dataLines.append(value.trimmingCharacters(in: .whitespaces))
            }
        }

        guard !dataLines.isEmpty else { return }
        let payload = dataLines.joined(separator: "\n")
        guard let payloadData = payload.data(using: .utf8) else { return }

        do {
            let event = try JSONDecoder().decode(StreamEvent.self, from: payloadData)
            switch event.type {
            case "metadata":
                let metadata = Metadata(
                    type: event.type,
                    outputType: event.outputType,
                    jobId: event.jobId,
                    host: event.host,
                    originalSize: event.originalSize,
                    compression: event.compression,
                    source: event.source,
                    truncated: event.truncated
                )
                onEvent(.metadata(metadata))
            case "chunk":
                guard let data = event.data else { return }
                let chunk = Chunk(
                    type: event.type,
                    index: event.index,
                    data: data,
                    compressed: event.compressed
                )
                onEvent(.chunk(chunk))
            case "complete":
                onEvent(.complete)
            case "truncation_notice":
                onEvent(.truncationNotice(event.originalSize ?? 0))
            case "error":
                onEvent(.error(event.message ?? "Stream error"))
            default:
                break
            }
        } catch {
            #if DEBUG
            print("[OutputStreamClient] Failed to decode SSE event: \(error)")
            print("[OutputStreamClient] Raw event: \(payload)")
            #endif
        }
    }

    private func isLocalHost(_ host: String) -> Bool {
        if host == "localhost" || host == "127.0.0.1" || host == "::1" {
            return true
        }
        if host.hasSuffix(".local") {
            return true
        }
        if host.hasPrefix("10.") || host.hasPrefix("192.168.") {
            return true
        }
        if host.hasPrefix("172.") {
            let parts = host.split(separator: ".")
            if parts.count > 1, let second = Int(parts[1]) {
                return (16...31).contains(second)
            }
        }
        return false
    }
}

extension Data {
    func gunzipped() -> Data? {
        guard !isEmpty else { return Data() }

        var stream = z_stream()
        var status: Int32

        status = inflateInit2_(&stream, 16 + MAX_WBITS, ZLIB_VERSION, Int32(MemoryLayout<z_stream>.size))
        guard status == Z_OK else { return nil }
        defer { inflateEnd(&stream) }

        return withUnsafeBytes { (sourcePointer: UnsafeRawBufferPointer) -> Data? in
            guard let sourceBase = sourcePointer.baseAddress else { return nil }

            stream.next_in = UnsafeMutablePointer<Bytef>(mutating: sourceBase.assumingMemoryBound(to: Bytef.self))
            stream.avail_in = uInt(count)

            let chunkSize = 16_384
            var output = Data()
            var buffer = [UInt8](repeating: 0, count: chunkSize)

            repeat {
                buffer.withUnsafeMutableBytes { outPtr in
                    stream.next_out = outPtr.bindMemory(to: Bytef.self).baseAddress
                    stream.avail_out = uInt(chunkSize)
                    status = inflate(&stream, Z_NO_FLUSH)
                }
                if status == Z_STREAM_ERROR || status == Z_DATA_ERROR || status == Z_MEM_ERROR {
                    return nil
                }

                let have = chunkSize - Int(stream.avail_out)
                if have > 0 {
                    output.append(buffer, count: have)
                }
            } while status != Z_STREAM_END

            return output
        }
    }
}

final class GzipStreamDecoder {
    private var stream = z_stream()
    private var isInitialized = false
    private var hasError = false

    init?() {
        var localStream = z_stream()
        let status = inflateInit2_(&localStream, 16 + MAX_WBITS, ZLIB_VERSION, Int32(MemoryLayout<z_stream>.size))
        guard status == Z_OK else {
            return nil
        }
        stream = localStream
        isInitialized = true
    }

    deinit {
        if isInitialized {
            inflateEnd(&stream)
        }
    }

    func append(_ data: Data) -> Data? {
        guard isInitialized, !hasError, !data.isEmpty else { return Data() }

        var output = Data()
        var status: Int32 = Z_OK

        data.withUnsafeBytes { inPtr in
            guard let baseAddress = inPtr.bindMemory(to: Bytef.self).baseAddress else { return }
            stream.next_in = UnsafeMutablePointer<Bytef>(mutating: baseAddress)
            stream.avail_in = uInt(inPtr.count)

            let chunkSize = 16_384
            var buffer = [UInt8](repeating: 0, count: chunkSize)

            repeat {
                buffer.withUnsafeMutableBytes { outPtr in
                    stream.next_out = outPtr.bindMemory(to: Bytef.self).baseAddress
                    stream.avail_out = uInt(chunkSize)
                    status = inflate(&stream, Z_SYNC_FLUSH)
                }

                if status == Z_STREAM_ERROR || status == Z_DATA_ERROR || status == Z_MEM_ERROR {
                    hasError = true
                    return
                }

                let have = chunkSize - Int(stream.avail_out)
                if have > 0 {
                    output.append(buffer, count: have)
                }
            } while stream.avail_in > 0 && status != Z_STREAM_END
        }

        return hasError ? nil : output
    }
}
