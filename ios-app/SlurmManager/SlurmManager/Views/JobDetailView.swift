import SwiftUI
import Combine

// MARK: - Enhanced Job Detail View
struct JobDetailView: View {
    let job: Job
    @StateObject private var viewModel = JobDetailViewModel()
    @State private var selectedTab = 0
    @State private var showCancelConfirmation = false
    @State private var showShareSheet = false
    @Environment(\.dismiss) var dismiss

    var body: some View {
        ScrollView {
            VStack(spacing: 0) {
                // Sticky Header
                jobHeader
                    .padding(.horizontal)
                    .padding(.top)

                // Quick Stats
                quickStatsBar
                    .padding(.vertical, 12)

                // Tab Selection with smooth animation
                tabSelector
                    .padding(.horizontal)

                // Tab Content
                tabContent
                    .padding(.top, 16)
            }
        }
        .background(Color(.systemGroupedBackground))
        .navigationTitle("Job Details")
        .navigationBarTitleDisplayMode(.inline)
        .toolbar {
            ToolbarItem(placement: .navigationBarTrailing) {
                Menu {
                    Button(action: { viewModel.loadJobDetail(job) }) {
                        Label("Refresh", systemImage: "arrow.clockwise")
                    }

                    if job.isRunning {
                        Button(role: .destructive, action: { showCancelConfirmation = true }) {
                            Label("Cancel Job", systemImage: "xmark.circle")
                        }
                    }

                    Divider()

                    Button(action: { showShareSheet = true }) {
                        Label("Share", systemImage: "square.and.arrow.up")
                    }

                    Button(action: copyJobId) {
                        Label("Copy Job ID", systemImage: "doc.on.doc")
                    }
                } label: {
                    Image(systemName: "ellipsis.circle")
                        .font(.title3)
                }
            }
        }
        .confirmationDialog(
            "Cancel Job",
            isPresented: $showCancelConfirmation,
            titleVisibility: .visible
        ) {
            Button("Cancel Job", role: .destructive) {
                viewModel.cancelJob(job)
            }
            Button("Keep Running", role: .cancel) {}
        } message: {
            Text("Are you sure you want to cancel job \(job.name)?")
        }
        .sheet(isPresented: $showShareSheet) {
            ShareSheet(items: [createShareText()])
        }
        .onAppear {
            viewModel.loadJobDetail(job)
            if job.isRunning || job.state == .pending {
                WebSocketManager.shared.subscribeToJob(job.id)
            }
        }
        .onDisappear {
            WebSocketManager.shared.unsubscribeFromJob(job.id)
        }
    }

    // MARK: - Job Header
    var jobHeader: some View {
        VStack(spacing: 16) {
            // Status and ID row
            HStack {
                AnimatedStatusBadge(state: job.state)

                Spacer()

                HStack(spacing: 4) {
                    Text("ID:")
                        .foregroundColor(.secondary)
                    Text(job.id)
                        .fontWeight(.medium)
                }
                .font(.caption)
            }

            // Job Name
            Text(job.name)
                .font(.title2)
                .fontWeight(.bold)
                .multilineTextAlignment(.center)
                .frame(maxWidth: .infinity)

            // Live duration for running jobs
            if job.isRunning {
                LiveDurationDisplay(startTime: job.startTime)
            }

            // Meta info
            HStack(spacing: 20) {
                MetaItem(icon: "person.fill", text: job.user)

                if let host = job.host.split(separator: ".").first {
                    MetaItem(icon: "server.rack", text: String(host))
                }

                if let partition = job.partition {
                    MetaItem(icon: "square.stack.3d.up", text: partition)
                }
            }
        }
        .padding(20)
        .background(
            RoundedRectangle(cornerRadius: 16)
                .fill(Color(.secondarySystemGroupedBackground))
                .shadow(color: .black.opacity(0.05), radius: 10, y: 5)
        )
    }

    // MARK: - Quick Stats
    var quickStatsBar: some View {
        ScrollView(.horizontal, showsIndicators: false) {
            HStack(spacing: 12) {
                if let cpus = job.cpus {
                    QuickStatCard(icon: "cpu", title: "CPUs", value: "\(cpus)")
                }

                if let nodes = job.nodes {
                    QuickStatCard(icon: "rectangle.stack", title: "Nodes", value: nodes)
                }

                if let memory = job.memory {
                    QuickStatCard(icon: "memorychip", title: "Memory", value: memory)
                }

                if let timeLimit = job.timeLimit {
                    QuickStatCard(icon: "clock", title: "Time Limit", value: timeLimit)
                }

                if let qos = job.qos {
                    QuickStatCard(icon: "gauge.medium", title: "QoS", value: qos)
                }
            }
            .padding(.horizontal)
        }
    }

    // MARK: - Tab Selector
    var tabSelector: some View {
        HStack(spacing: 0) {
            ForEach(Tab.allCases, id: \.self) { tab in
                TabButton(
                    title: tab.title,
                    icon: tab.icon,
                    isSelected: selectedTab == tab.rawValue,
                    hasContent: tabHasContent(tab)
                ) {
                    withAnimation(.spring(response: 0.3, dampingFraction: 0.7)) {
                        selectedTab = tab.rawValue
                    }
                    HapticManager.selection()
                }
            }
        }
        .padding(4)
        .background(Color(.systemGray6))
        .cornerRadius(12)
    }

    enum Tab: Int, CaseIterable {
        case info = 0
        case script = 1
        case output = 2
        case error = 3

        var title: String {
            switch self {
            case .info: return "Info"
            case .script: return "Script"
            case .output: return "Output"
            case .error: return "Errors"
            }
        }

        var icon: String {
            switch self {
            case .info: return "info.circle"
            case .script: return "doc.text"
            case .output: return "terminal"
            case .error: return "exclamationmark.triangle"
            }
        }
    }

    func tabHasContent(_ tab: Tab) -> Bool {
        switch tab {
        case .info: return true
        case .script: return viewModel.script != nil
        case .output: return viewModel.output != nil && !viewModel.output!.isEmpty
        case .error: return viewModel.error != nil && !viewModel.error!.isEmpty
        }
    }

    // MARK: - Tab Content
    @ViewBuilder
    var tabContent: some View {
        switch selectedTab {
        case 0:
            jobInfoView
        case 1:
            scriptView
        case 2:
            outputView(content: viewModel.output, type: "stdout")
        case 3:
            outputView(content: viewModel.error, type: "stderr")
        default:
            EmptyView()
        }
    }

    // MARK: - Job Info View
    var jobInfoView: some View {
        VStack(spacing: 16) {
            // Timeline section
            InfoSection(title: "Timeline") {
                VStack(spacing: 12) {
                    if let submitTime = job.submitTime {
                        TimelineRow(
                            icon: "paperplane.fill",
                            title: "Submitted",
                            date: submitTime,
                            color: .blue
                        )
                    }

                    if let startTime = job.startTime {
                        TimelineRow(
                            icon: "play.fill",
                            title: "Started",
                            date: startTime,
                            color: .green
                        )
                    }

                    if let endTime = job.endTime {
                        TimelineRow(
                            icon: "stop.fill",
                            title: "Ended",
                            date: endTime,
                            color: job.state == .completed ? .green : .red
                        )
                    }

                    if let duration = job.formattedDuration {
                        JobInfoRow(label: "Duration", value: duration, icon: "timer")
                    }
                }
            }

            // Resources section
            InfoSection(title: "Resources") {
                VStack(spacing: 12) {
                    if let cpus = job.cpus {
                        JobInfoRow(label: "CPUs", value: "\(cpus)", icon: "cpu")
                    }

                    if let nodes = job.nodes {
                        JobInfoRow(label: "Nodes", value: nodes, icon: "rectangle.stack")
                    }

                    if let memory = job.memory {
                        JobInfoRow(label: "Memory", value: memory, icon: "memorychip")
                    }

                    if let timeLimit = job.timeLimit {
                        JobInfoRow(label: "Time Limit", value: timeLimit, icon: "clock")
                    }
                }
            }

            // Details section
            InfoSection(title: "Details") {
                VStack(spacing: 12) {
                    if let partition = job.partition {
                        JobInfoRow(label: "Partition", value: partition, icon: "square.stack.3d.up")
                    }

                    if let qos = job.qos {
                        JobInfoRow(label: "QoS", value: qos, icon: "gauge.medium")
                    }

                    if let account = job.account {
                        JobInfoRow(label: "Account", value: account, icon: "person.2")
                    }

                    if let workDir = job.workDir {
                        JobInfoRow(label: "Work Directory", value: workDir, icon: "folder")
                    }

                    JobInfoRow(label: "Host", value: job.host, icon: "server.rack")
                }
            }
        }
        .padding(.horizontal)
    }

    // MARK: - Script View
    var scriptView: some View {
        Group {
            if viewModel.isLoadingScript {
                VStack(spacing: 16) {
                    ProgressView()
                    Text("Loading script...")
                        .foregroundColor(.secondary)
                }
                .frame(maxWidth: .infinity, minHeight: 200)
            } else if let script = viewModel.script {
                CodeViewer(
                    content: script,
                    language: "bash",
                    showLineNumbers: true
                )
                .padding(.horizontal)
            } else {
                EmptyContentView(
                    icon: "doc.text.magnifyingglass",
                    title: "No Script Available",
                    message: "Script content is not available for this job"
                )
            }
        }
    }

    // MARK: - Output View
    func outputView(content: String?, type: String) -> some View {
        Group {
            if viewModel.isLoadingOutput {
                VStack(spacing: 16) {
                    ProgressView()
                    Text("Loading \(type)...")
                        .foregroundColor(.secondary)
                }
                .frame(maxWidth: .infinity, minHeight: 200)
            } else if let content = content, !content.isEmpty {
                VStack(alignment: .leading, spacing: 8) {
                    // Header with actions
                    HStack {
                        if job.isRunning {
                            LiveIndicator()
                        }

                        Spacer()

                        Button(action: { copyToClipboard(content) }) {
                            Label("Copy", systemImage: "doc.on.doc")
                                .font(.caption)
                        }
                        .buttonStyle(.bordered)
                        .controlSize(.small)
                    }
                    .padding(.horizontal)

                    // Output content
                    CodeViewer(
                        content: content,
                        language: "log",
                        showLineNumbers: true,
                        autoScroll: job.isRunning
                    )
                    .padding(.horizontal)
                }
            } else {
                EmptyContentView(
                    icon: type == "stdout" ? "terminal" : "exclamationmark.triangle",
                    title: "No \(type == "stdout" ? "Output" : "Errors")",
                    message: job.isRunning
                        ? "Output will appear here as the job runs"
                        : "No \(type) was generated by this job"
                )
            }
        }
    }

    // MARK: - Helper Methods
    private func copyJobId() {
        UIPasteboard.general.string = job.id
        HapticManager.notification(.success)
        ToastManager.shared.show("Job ID copied", type: .success)
    }

    private func copyToClipboard(_ text: String) {
        UIPasteboard.general.string = text
        HapticManager.notification(.success)
        ToastManager.shared.show("Copied to clipboard", type: .success)
    }

    private func createShareText() -> String {
        """
        SLURM Job: \(job.name)
        Job ID: \(job.id)
        Status: \(job.state.displayName)
        Host: \(job.host)
        User: \(job.user)
        \(job.partition.map { "Partition: \($0)" } ?? "")
        \(job.formattedDuration.map { "Duration: \($0)" } ?? "")
        """
    }
}

// MARK: - Supporting Views

struct MetaItem: View {
    let icon: String
    let text: String

    var body: some View {
        HStack(spacing: 4) {
            Image(systemName: icon)
                .font(.caption)
            Text(text)
                .font(.caption)
        }
        .foregroundColor(.secondary)
    }
}

struct QuickStatCard: View {
    let icon: String
    let title: String
    let value: String

    var body: some View {
        VStack(spacing: 4) {
            Image(systemName: icon)
                .font(.title3)
                .foregroundColor(.blue)

            Text(value)
                .font(.subheadline)
                .fontWeight(.semibold)

            Text(title)
                .font(.caption2)
                .foregroundColor(.secondary)
        }
        .frame(width: 70)
        .padding(.vertical, 12)
        .background(Color(.secondarySystemGroupedBackground))
        .cornerRadius(12)
    }
}

struct TabButton: View {
    let title: String
    let icon: String
    let isSelected: Bool
    let hasContent: Bool
    let action: () -> Void

    var body: some View {
        Button(action: action) {
            HStack(spacing: 4) {
                Image(systemName: icon)
                    .font(.caption)
                Text(title)
                    .font(.subheadline)
                    .fontWeight(isSelected ? .semibold : .regular)
            }
            .foregroundColor(isSelected ? .white : (hasContent ? .primary : .secondary))
            .frame(maxWidth: .infinity)
            .padding(.vertical, 10)
            .background(isSelected ? Color.blue : Color.clear)
            .cornerRadius(8)
        }
    }
}

struct InfoSection<Content: View>: View {
    let title: String
    @ViewBuilder let content: Content

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text(title)
                .font(.headline)
                .padding(.horizontal, 4)

            VStack(spacing: 0) {
                content
            }
            .padding(16)
            .background(Color(.secondarySystemGroupedBackground))
            .cornerRadius(12)
        }
    }
}

struct JobInfoRow: View {
    let label: String
    let value: String
    var icon: String? = nil

    var body: some View {
        HStack {
            if let icon = icon {
                Image(systemName: icon)
                    .font(.caption)
                    .foregroundColor(.secondary)
                    .frame(width: 20)
            }

            Text(label)
                .font(.subheadline)
                .foregroundColor(.secondary)

            Spacer()

            Text(value)
                .font(.subheadline)
                .fontWeight(.medium)
                .lineLimit(1)
        }
    }
}

struct TimelineRow: View {
    let icon: String
    let title: String
    let date: Date
    let color: Color

    var body: some View {
        HStack(spacing: 12) {
            Circle()
                .fill(color.opacity(0.2))
                .frame(width: 32, height: 32)
                .overlay(
                    Image(systemName: icon)
                        .font(.caption)
                        .foregroundColor(color)
                )

            VStack(alignment: .leading, spacing: 2) {
                Text(title)
                    .font(.caption)
                    .foregroundColor(.secondary)
                Text(formatDate(date))
                    .font(.subheadline)
                    .fontWeight(.medium)
            }

            Spacer()

            Text(relativeTime(date))
                .font(.caption)
                .foregroundColor(.secondary)
        }
    }

    private func formatDate(_ date: Date) -> String {
        let formatter = DateFormatter()
        formatter.dateStyle = .medium
        formatter.timeStyle = .short
        return formatter.string(from: date)
    }

    private func relativeTime(_ date: Date) -> String {
        let formatter = RelativeDateTimeFormatter()
        formatter.unitsStyle = .abbreviated
        return formatter.localizedString(for: date, relativeTo: Date())
    }
}

struct LiveDurationDisplay: View {
    let startTime: Date?
    @State private var currentTime = Date()

    private let timer = Timer.publish(every: 1, on: .main, in: .common).autoconnect()

    var body: some View {
        HStack(spacing: 8) {
            Circle()
                .fill(Color.green)
                .frame(width: 8, height: 8)
                .pulseAnimation()

            Text(formattedDuration)
                .font(.system(.title3, design: .monospaced))
                .fontWeight(.bold)
                .foregroundColor(.blue)
        }
        .onReceive(timer) { time in
            currentTime = time
        }
    }

    var formattedDuration: String {
        guard let start = startTime else { return "--:--:--" }
        let duration = currentTime.timeIntervalSince(start)

        let hours = Int(duration) / 3600
        let minutes = (Int(duration) % 3600) / 60
        let seconds = Int(duration) % 60

        return String(format: "%02d:%02d:%02d", hours, minutes, seconds)
    }
}

struct LiveIndicator: View {
    @State private var isAnimating = false

    var body: some View {
        HStack(spacing: 4) {
            Circle()
                .fill(Color.red)
                .frame(width: 6, height: 6)
                .scaleEffect(isAnimating ? 1.0 : 0.6)
                .animation(
                    .easeInOut(duration: 0.8)
                    .repeatForever(autoreverses: true),
                    value: isAnimating
                )

            Text("LIVE")
                .font(.caption2)
                .fontWeight(.bold)
                .foregroundColor(.red)
        }
        .padding(.horizontal, 8)
        .padding(.vertical, 4)
        .background(Color.red.opacity(0.1))
        .cornerRadius(4)
        .onAppear {
            isAnimating = true
        }
    }
}

struct EmptyContentView: View {
    let icon: String
    let title: String
    let message: String

    var body: some View {
        VStack(spacing: 16) {
            Image(systemName: icon)
                .font(.system(size: 48))
                .foregroundColor(.secondary)

            Text(title)
                .font(.headline)

            Text(message)
                .font(.subheadline)
                .foregroundColor(.secondary)
                .multilineTextAlignment(.center)
        }
        .frame(maxWidth: .infinity, minHeight: 200)
        .padding()
    }
}

struct CodeViewer: View {
    let content: String
    var language: String = "text"
    var showLineNumbers: Bool = true
    var autoScroll: Bool = false

    var body: some View {
        ScrollView([.horizontal, .vertical]) {
            ScrollViewReader { proxy in
                VStack(alignment: .leading, spacing: 0) {
                    let lines = content.components(separatedBy: "\n")

                    ForEach(Array(lines.enumerated()), id: \.offset) { index, line in
                        HStack(alignment: .top, spacing: 8) {
                            if showLineNumbers {
                                Text("\(index + 1)")
                                    .font(.system(.caption2, design: .monospaced))
                                    .foregroundColor(.secondary)
                                    .frame(width: 30, alignment: .trailing)
                            }

                            Text(line.isEmpty ? " " : line)
                                .font(.system(.caption, design: .monospaced))
                                .foregroundColor(.primary)
                        }
                        .padding(.vertical, 2)
                        .id(index)
                    }
                }
                .padding(12)
                .onAppear {
                    if autoScroll {
                        proxy.scrollTo(content.components(separatedBy: "\n").count - 1)
                    }
                }
                .onChange(of: content) { newContent in
                    if autoScroll {
                        withAnimation {
                            proxy.scrollTo(newContent.components(separatedBy: "\n").count - 1)
                        }
                    }
                }
            }
        }
        .background(Color(.systemGray6))
        .cornerRadius(8)
    }
}

struct ShareSheet: UIViewControllerRepresentable {
    let items: [Any]

    func makeUIViewController(context: Context) -> UIActivityViewController {
        UIActivityViewController(activityItems: items, applicationActivities: nil)
    }

    func updateUIViewController(_ uiViewController: UIActivityViewController, context: Context) {}
}

// MARK: - View Model
@MainActor
class JobDetailViewModel: ObservableObject {
    @Published var jobDetail: JobDetail?
    @Published var script: String?
    @Published var output: String?
    @Published var error: String?
    @Published var isLoadingScript = false
    @Published var isLoadingOutput = false

    private var cancellables = Set<AnyCancellable>()
    private var outputTimer: Timer?

    func loadJobDetail(_ job: Job) {
        // Load full job details
        JobManager.shared.fetchJobDetail(jobId: job.id, host: job.host)
            .sink(
                receiveCompletion: { _ in },
                receiveValue: { [weak self] detail in
                    self?.jobDetail = detail
                    self?.script = detail.script
                    self?.output = detail.output
                    self?.error = detail.error
                }
            )
            .store(in: &cancellables)

        // Load script if not included
        loadScript(job)

        // Load output if job is running or completed
        if job.isRunning || job.isCompleted {
            loadOutput(job)
        }

        // Start polling for running jobs
        if job.isRunning {
            startOutputPolling(job)
        }
    }

    func loadScript(_ job: Job) {
        isLoadingScript = true

        DispatchQueue.main.asyncAfter(deadline: .now() + 0.5) { [weak self] in
            self?.isLoadingScript = false
        }
    }

    func loadOutput(_ job: Job) {
        isLoadingOutput = true

        APIClient.shared.getJobOutput(jobId: job.id, host: job.host, outputType: .both)
            .sink(
                receiveCompletion: { [weak self] _ in
                    self?.isLoadingOutput = false
                },
                receiveValue: { [weak self] output in
                    self?.output = output.output
                    self?.error = output.error
                }
            )
            .store(in: &cancellables)
    }

    func cancelJob(_ job: Job) {
        JobManager.shared.cancelJob(jobId: job.id, host: job.host)
            .sink(
                receiveCompletion: { _ in },
                receiveValue: { success in
                    if success {
                        HapticManager.notification(.success)
                        ToastManager.shared.show("Job cancelled", type: .success)
                    } else {
                        HapticManager.notification(.error)
                        ToastManager.shared.show("Failed to cancel job", type: .error)
                    }
                }
            )
            .store(in: &cancellables)
    }

    private func startOutputPolling(_ job: Job) {
        outputTimer = Timer.scheduledTimer(withTimeInterval: 5, repeats: true) { [weak self] _ in
            self?.loadOutput(job)
        }
    }

    deinit {
        outputTimer?.invalidate()
    }
}

// MARK: - Preview
#Preview {
    NavigationView {
        JobDetailView(
            job: Job(
                id: "12345",
                name: "training_model_v2",
                user: "jsmith",
                state: .running,
                submitTime: Date().addingTimeInterval(-3600),
                startTime: Date().addingTimeInterval(-1800),
                endTime: nil,
                partition: "gpu",
                nodes: "4",
                cpus: 32,
                memory: "128G",
                timeLimit: "24:00:00",
                workDir: "/home/jsmith/projects/ml-training",
                command: nil,
                array: nil,
                qos: "normal",
                account: "research",
                host: "cluster1.example.com",
                cached: false
            )
        )
    }
}
