import SwiftUI
import Combine

struct JobDetailView: View {
    let job: Job
    @StateObject private var viewModel = JobDetailViewModel()
    @State private var selectedTab = 0
    @Environment(\.dismiss) var dismiss
    
    var body: some View {
        ScrollView {
            VStack(spacing: 20) {
                // Job Header
                jobHeader
                
                // Tab Selection
                Picker("", selection: $selectedTab) {
                    Text("Info").tag(0)
                    Text("Script").tag(1)
                    Text("Output").tag(2)
                    Text("Error").tag(3)
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
                    
                    Button(action: shareJob) {
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
                
                Label(job.user, systemImage: "person")
                    .font(.caption)
                
                Label(job.host.split(separator: ".").first.map(String.init) ?? job.host, 
                      systemImage: "server.rack")
                    .font(.caption)
            }
            .foregroundColor(.secondary)
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
        default:
            EmptyView()
        }
    }
    
    var jobInfoView: some View {
        VStack(spacing: 16) {
            InfoRow(label: "Job ID", value: job.id)
            InfoRow(label: "Name", value: job.name)
            InfoRow(label: "User", value: job.user)
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
            
            if let workDir = job.workDir {
                InfoRow(label: "Work Directory", value: workDir)
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
            if viewModel.isLoadingOutput {
                ProgressView("Loading output...")
                    .frame(maxWidth: .infinity, minHeight: 200)
            } else {
                let content = type == .stdout ? viewModel.output : viewModel.error
                if let content = content, !content.isEmpty {
                    ScrollView {
                        Text(content)
                            .font(.system(.caption, design: .monospaced))
                            .padding()
                            .frame(maxWidth: .infinity, alignment: .leading)
                    }
                    .background(Color(.systemGray6))
                    .cornerRadius(8)
                    .padding(.horizontal)
                } else {
                    Text("No \(type == .stdout ? "output" : "error") available")
                        .foregroundColor(.secondary)
                        .frame(maxWidth: .infinity, minHeight: 200)
                }
            }
        }
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
    
    private func formatDate(_ date: Date) -> String {
        let formatter = DateFormatter()
        formatter.dateStyle = .medium
        formatter.timeStyle = .medium
        return formatter.string(from: date)
    }
    
    private func refreshJob() {
        viewModel.loadJobDetail(job)
    }
    
    private func cancelJob() {
        viewModel.cancelJob(job)
    }
    
    private func shareJob() {
        let text = """
        Job: \(job.name)
        ID: \(job.id)
        State: \(job.state.displayName)
        Host: \(job.host)
        """
        
        let av = UIActivityViewController(activityItems: [text], applicationActivities: nil)
        
        if let windowScene = UIApplication.shared.connectedScenes.first as? UIWindowScene,
           let window = windowScene.windows.first {
            window.rootViewController?.present(av, animated: true)
        }
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
    @Published var output: String?
    @Published var error: String?
    @Published var isLoadingScript = false
    @Published var isLoadingOutput = false
    
    private var cancellables = Set<AnyCancellable>()
    
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
    }
    
    func loadScript(_ job: Job) {
        isLoadingScript = true
        
        // In a real app, this would call an API endpoint for the script
        // For now, we'll use the detail endpoint
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.5) {
            self.isLoadingScript = false
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
                        // Job cancelled successfully
                    }
                }
            )
            .store(in: &cancellables)
    }
}