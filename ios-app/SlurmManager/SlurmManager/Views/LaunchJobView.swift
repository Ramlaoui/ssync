import SwiftUI
import Combine

// MARK: - Launch Job View
struct LaunchJobView: View {
    @StateObject private var viewModel = LaunchJobViewModel()
    @Environment(\.dismiss) var dismiss

    @State private var showingScriptEditor = false
    @State private var showingRecentScripts = false
    @State private var showingValidationError = false

    var body: some View {
        NavigationView {
            ScrollView {
                VStack(spacing: 24) {
                    // Header card
                    headerCard

                    // Host selection
                    hostSelectionSection

                    // Script configuration
                    scriptSection

                    // Resource configuration
                    resourceSection

                    // Advanced options (collapsible)
                    advancedSection

                    // Launch button
                    launchButton

                    Spacer(minLength: 32)
                }
                .padding()
            }
            .background(Color(.systemGroupedBackground))
            .navigationTitle("Launch Job")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .navigationBarLeading) {
                    Button("Cancel") {
                        dismiss()
                    }
                }

                ToolbarItem(placement: .navigationBarTrailing) {
                    Menu {
                        Button(action: { showingRecentScripts = true }) {
                            Label("Recent Scripts", systemImage: "clock.arrow.circlepath")
                        }

                        Button(action: viewModel.resetToDefaults) {
                            Label("Reset to Defaults", systemImage: "arrow.counterclockwise")
                        }
                    } label: {
                        Image(systemName: "ellipsis.circle")
                    }
                }
            }
            .onAppear {
                viewModel.loadHosts()
            }
            .alert("Validation Error", isPresented: $showingValidationError) {
                Button("OK", role: .cancel) {}
            } message: {
                Text(viewModel.validationError ?? "Please check your input")
            }
            .sheet(isPresented: $showingScriptEditor) {
                ScriptEditorView(script: $viewModel.scriptContent)
            }
            .sheet(isPresented: $showingRecentScripts) {
                RecentScriptsView(onSelect: { script in
                    viewModel.scriptContent = script.content
                    viewModel.jobName = script.name
                    showingRecentScripts = false
                })
            }
        }
    }

    // MARK: - Header Card
    var headerCard: some View {
        VStack(spacing: 12) {
            Image(systemName: "play.circle.fill")
                .font(.system(size: 48))
                .foregroundColor(.blue)

            Text("Launch New Job")
                .font(.title2)
                .fontWeight(.bold)

            Text("Configure and submit a SLURM job to your cluster")
                .font(.subheadline)
                .foregroundColor(.secondary)
                .multilineTextAlignment(.center)
        }
        .padding(24)
        .frame(maxWidth: .infinity)
        .background(Color(.secondarySystemGroupedBackground))
        .cornerRadius(16)
    }

    // MARK: - Host Selection
    var hostSelectionSection: some View {
        FormSection(title: "Cluster", icon: "server.rack") {
            if viewModel.isLoadingHosts {
                HStack {
                    ProgressView()
                    Text("Loading hosts...")
                        .foregroundColor(.secondary)
                }
                .frame(maxWidth: .infinity)
                .padding()
            } else if viewModel.hosts.isEmpty {
                VStack(spacing: 8) {
                    Image(systemName: "exclamationmark.triangle")
                        .font(.title2)
                        .foregroundColor(.orange)
                    Text("No hosts available")
                        .font(.subheadline)
                        .foregroundColor(.secondary)
                }
                .frame(maxWidth: .infinity)
                .padding()
            } else {
                ScrollView(.horizontal, showsIndicators: false) {
                    HStack(spacing: 12) {
                        ForEach(viewModel.hosts) { host in
                            HostSelectionCard(
                                host: host,
                                isSelected: viewModel.selectedHost?.id == host.id
                            ) {
                                withAnimation(.spring()) {
                                    viewModel.selectedHost = host
                                }
                                HapticManager.selection()
                            }
                        }
                    }
                    .padding(.horizontal, 4)
                    .padding(.vertical, 8)
                }
            }
        }
    }

    // MARK: - Script Section
    var scriptSection: some View {
        FormSection(title: "Script", icon: "doc.text") {
            VStack(spacing: 16) {
                // Job name
                FormTextField(
                    label: "Job Name",
                    placeholder: "my_job",
                    text: $viewModel.jobName,
                    icon: "tag"
                )

                // Script content or path
                VStack(alignment: .leading, spacing: 8) {
                    Text("Script Content")
                        .font(.subheadline)
                        .foregroundColor(.secondary)

                    Button(action: { showingScriptEditor = true }) {
                        HStack {
                            Image(systemName: viewModel.scriptContent.isEmpty ? "plus.circle" : "pencil.circle")
                                .font(.title3)

                            VStack(alignment: .leading, spacing: 2) {
                                Text(viewModel.scriptContent.isEmpty ? "Add Script" : "Edit Script")
                                    .font(.subheadline)
                                    .fontWeight(.medium)

                                if !viewModel.scriptContent.isEmpty {
                                    Text("\(viewModel.scriptContent.components(separatedBy: "\n").count) lines")
                                        .font(.caption)
                                        .foregroundColor(.secondary)
                                }
                            }

                            Spacer()

                            Image(systemName: "chevron.right")
                                .font(.caption)
                                .foregroundColor(.secondary)
                        }
                        .padding()
                        .background(Color(.systemGray6))
                        .cornerRadius(10)
                    }
                    .buttonStyle(.plain)
                }

                // Source directory (optional)
                FormTextField(
                    label: "Source Directory (Optional)",
                    placeholder: "/path/to/source",
                    text: $viewModel.sourceDir,
                    icon: "folder"
                )
            }
        }
    }

    // MARK: - Resource Section
    var resourceSection: some View {
        FormSection(title: "Resources", icon: "cpu") {
            VStack(spacing: 16) {
                // CPUs
                FormStepper(
                    label: "CPUs",
                    value: $viewModel.cpus,
                    range: 1...128,
                    icon: "bolt.fill"
                )

                // Memory
                FormTextField(
                    label: "Memory",
                    placeholder: "8G",
                    text: $viewModel.memory,
                    icon: "memorychip"
                )

                // Time limit
                FormTextField(
                    label: "Time Limit",
                    placeholder: "1:00:00",
                    text: $viewModel.timeLimit,
                    icon: "clock"
                )

                // Nodes
                FormStepper(
                    label: "Nodes",
                    value: $viewModel.nodes,
                    range: 1...64,
                    icon: "rectangle.stack"
                )

                // GPUs (if available)
                if viewModel.selectedHost?.workDir.contains("gpu") == true {
                    FormStepper(
                        label: "GPUs per Node",
                        value: $viewModel.gpusPerNode,
                        range: 0...8,
                        icon: "cpu"
                    )
                }
            }
        }
    }

    // MARK: - Advanced Section
    var advancedSection: some View {
        ExpandableSection(title: "Advanced Options", icon: "slider.horizontal.3") {
            VStack(spacing: 16) {
                // Partition
                FormTextField(
                    label: "Partition",
                    placeholder: "batch",
                    text: $viewModel.partition,
                    icon: "square.stack.3d.up"
                )

                // Account
                FormTextField(
                    label: "Account",
                    placeholder: "default",
                    text: $viewModel.account,
                    icon: "person.2"
                )

                // QoS
                FormTextField(
                    label: "QoS",
                    placeholder: "normal",
                    text: $viewModel.qos,
                    icon: "gauge.medium"
                )

                // Sync options
                Toggle(isOn: $viewModel.syncBeforeLaunch) {
                    Label("Sync source directory", systemImage: "arrow.triangle.2.circlepath")
                }

                if viewModel.syncBeforeLaunch {
                    Toggle(isOn: $viewModel.respectGitignore) {
                        Label("Respect .gitignore", systemImage: "doc.badge.gearshape")
                    }
                }
            }
        }
    }

    // MARK: - Launch Button
    var launchButton: some View {
        Button(action: {
            if viewModel.validate() {
                viewModel.launchJob()
            } else {
                showingValidationError = true
            }
        }) {
            HStack {
                if viewModel.isLaunching {
                    ProgressView()
                        .progressViewStyle(CircularProgressViewStyle(tint: .white))
                } else {
                    Image(systemName: "play.fill")
                }

                Text(viewModel.isLaunching ? "Launching..." : "Launch Job")
                    .fontWeight(.semibold)
            }
            .frame(maxWidth: .infinity)
            .padding()
            .background(viewModel.canLaunch ? Color.blue : Color.gray)
            .foregroundColor(.white)
            .cornerRadius(12)
        }
        .disabled(!viewModel.canLaunch || viewModel.isLaunching)
    }
}

// MARK: - Form Components

struct FormSection<Content: View>: View {
    let title: String
    let icon: String
    @ViewBuilder let content: Content

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            Label(title, systemImage: icon)
                .font(.headline)

            VStack(spacing: 0) {
                content
            }
            .padding(16)
            .background(Color(.secondarySystemGroupedBackground))
            .cornerRadius(12)
        }
    }
}

struct ExpandableSection<Content: View>: View {
    let title: String
    let icon: String
    @ViewBuilder let content: Content
    @State private var isExpanded = false

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            Button(action: {
                withAnimation(.spring()) {
                    isExpanded.toggle()
                }
                HapticManager.selection()
            }) {
                HStack {
                    Label(title, systemImage: icon)
                        .font(.headline)
                        .foregroundColor(.primary)

                    Spacer()

                    Image(systemName: "chevron.right")
                        .font(.caption)
                        .foregroundColor(.secondary)
                        .rotationEffect(.degrees(isExpanded ? 90 : 0))
                }
            }

            if isExpanded {
                VStack(spacing: 0) {
                    content
                }
                .padding(16)
                .background(Color(.secondarySystemGroupedBackground))
                .cornerRadius(12)
                .transition(.asymmetric(
                    insertion: .scale(scale: 0.95).combined(with: .opacity),
                    removal: .opacity
                ))
            }
        }
    }
}

struct FormTextField: View {
    let label: String
    let placeholder: String
    @Binding var text: String
    var icon: String? = nil

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            Text(label)
                .font(.subheadline)
                .foregroundColor(.secondary)

            HStack(spacing: 10) {
                if let icon = icon {
                    Image(systemName: icon)
                        .font(.subheadline)
                        .foregroundColor(.secondary)
                        .frame(width: 20)
                }

                TextField(placeholder, text: $text)
                    .textFieldStyle(.plain)
            }
            .padding(12)
            .background(Color(.systemGray6))
            .cornerRadius(8)
        }
    }
}

struct FormStepper: View {
    let label: String
    @Binding var value: Int
    let range: ClosedRange<Int>
    var icon: String? = nil

    var body: some View {
        HStack {
            if let icon = icon {
                Image(systemName: icon)
                    .font(.subheadline)
                    .foregroundColor(.secondary)
                    .frame(width: 20)
            }

            Text(label)
                .font(.subheadline)

            Spacer()

            HStack(spacing: 12) {
                Button(action: {
                    if value > range.lowerBound {
                        value -= 1
                        HapticManager.selection()
                    }
                }) {
                    Image(systemName: "minus.circle.fill")
                        .font(.title2)
                        .foregroundColor(value > range.lowerBound ? .blue : .gray)
                }
                .disabled(value <= range.lowerBound)

                Text("\(value)")
                    .font(.headline)
                    .frame(width: 40)

                Button(action: {
                    if value < range.upperBound {
                        value += 1
                        HapticManager.selection()
                    }
                }) {
                    Image(systemName: "plus.circle.fill")
                        .font(.title2)
                        .foregroundColor(value < range.upperBound ? .blue : .gray)
                }
                .disabled(value >= range.upperBound)
            }
        }
    }
}

struct HostSelectionCard: View {
    let host: Host
    let isSelected: Bool
    let action: () -> Void

    var body: some View {
        Button(action: action) {
            VStack(spacing: 8) {
                ZStack {
                    Circle()
                        .fill(host.isAvailable ? (isSelected ? Color.blue : Color.gray.opacity(0.2)) : Color.red.opacity(0.2))
                        .frame(width: 50, height: 50)

                    Image(systemName: "server.rack")
                        .font(.title3)
                        .foregroundColor(host.isAvailable ? (isSelected ? .white : .primary) : .red)
                }

                Text(host.displayName)
                    .font(.caption)
                    .fontWeight(isSelected ? .semibold : .regular)
                    .foregroundColor(.primary)
                    .lineLimit(1)

                Circle()
                    .fill(host.isAvailable ? Color.green : Color.red)
                    .frame(width: 8, height: 8)
            }
            .frame(width: 80)
            .padding(.vertical, 12)
            .background(
                RoundedRectangle(cornerRadius: 12)
                    .fill(isSelected ? Color.blue.opacity(0.1) : Color.clear)
                    .overlay(
                        RoundedRectangle(cornerRadius: 12)
                            .strokeBorder(isSelected ? Color.blue : Color.clear, lineWidth: 2)
                    )
            )
        }
        .buttonStyle(.plain)
        .disabled(!host.isAvailable)
    }
}

// MARK: - Script Editor View
struct ScriptEditorView: View {
    @Binding var script: String
    @Environment(\.dismiss) var dismiss
    @State private var tempScript: String = ""

    var body: some View {
        NavigationView {
            VStack(spacing: 0) {
                // Toolbar
                HStack {
                    Button("Template") {
                        tempScript = defaultTemplate
                    }
                    .buttonStyle(.bordered)

                    Spacer()

                    Text("\(tempScript.components(separatedBy: "\n").count) lines")
                        .font(.caption)
                        .foregroundColor(.secondary)
                }
                .padding()

                // Editor
                TextEditor(text: $tempScript)
                    .font(.system(.body, design: .monospaced))
                    .autocapitalization(.none)
                    .disableAutocorrection(true)
            }
            .navigationTitle("Script Editor")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .navigationBarLeading) {
                    Button("Cancel") {
                        dismiss()
                    }
                }

                ToolbarItem(placement: .navigationBarTrailing) {
                    Button("Save") {
                        script = tempScript
                        dismiss()
                    }
                    .fontWeight(.semibold)
                }
            }
            .onAppear {
                tempScript = script
            }
        }
    }

    var defaultTemplate: String {
        """
        #!/bin/bash
        #SBATCH --job-name=my_job
        #SBATCH --output=%j.out
        #SBATCH --error=%j.err
        #SBATCH --time=1:00:00
        #SBATCH --ntasks=1
        #SBATCH --cpus-per-task=4
        #SBATCH --mem=8G

        # Load modules
        # module load python/3.9

        # Run your code
        echo "Starting job"

        # Your commands here

        echo "Job completed"
        """
    }
}

// MARK: - Recent Scripts View
struct RecentScriptsView: View {
    let onSelect: (RecentScript) -> Void
    @Environment(\.dismiss) var dismiss

    var body: some View {
        NavigationView {
            List {
                Text("No recent scripts")
                    .foregroundColor(.secondary)
                    .frame(maxWidth: .infinity, alignment: .center)
            }
            .navigationTitle("Recent Scripts")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .navigationBarTrailing) {
                    Button("Done") {
                        dismiss()
                    }
                }
            }
        }
    }
}

struct RecentScript: Identifiable {
    let id = UUID()
    let name: String
    let content: String
    let date: Date
}

// MARK: - View Model
@MainActor
class LaunchJobViewModel: ObservableObject {
    // Host selection
    @Published var hosts: [Host] = []
    @Published var selectedHost: Host?
    @Published var isLoadingHosts = false

    // Job configuration
    @Published var jobName = ""
    @Published var scriptContent = ""
    @Published var sourceDir = ""

    // Resources
    @Published var cpus = 4
    @Published var memory = "8G"
    @Published var timeLimit = "1:00:00"
    @Published var nodes = 1
    @Published var gpusPerNode = 0

    // Advanced
    @Published var partition = ""
    @Published var account = ""
    @Published var qos = ""
    @Published var syncBeforeLaunch = false
    @Published var respectGitignore = true

    // State
    @Published var isLaunching = false
    @Published var validationError: String?

    private var cancellables = Set<AnyCancellable>()

    var canLaunch: Bool {
        selectedHost != nil &&
        !jobName.isEmpty &&
        !scriptContent.isEmpty
    }

    func loadHosts() {
        isLoadingHosts = true

        APIClient.shared.getHosts()
            .sink(
                receiveCompletion: { [weak self] completion in
                    self?.isLoadingHosts = false
                    if case .failure(let error) = completion {
                        print("Failed to load hosts: \(error)")
                    }
                },
                receiveValue: { [weak self] hosts in
                    self?.hosts = hosts
                    // Auto-select default host
                    if let defaultHost = hosts.first(where: { $0.isDefault && $0.isAvailable }) {
                        self?.selectedHost = defaultHost
                    } else if let firstAvailable = hosts.first(where: { $0.isAvailable }) {
                        self?.selectedHost = firstAvailable
                    }
                }
            )
            .store(in: &cancellables)
    }

    func validate() -> Bool {
        if selectedHost == nil {
            validationError = "Please select a host"
            return false
        }

        if jobName.isEmpty {
            validationError = "Please enter a job name"
            return false
        }

        if scriptContent.isEmpty {
            validationError = "Please add script content"
            return false
        }

        validationError = nil
        return true
    }

    func resetToDefaults() {
        jobName = ""
        scriptContent = ""
        sourceDir = ""
        cpus = 4
        memory = "8G"
        timeLimit = "1:00:00"
        nodes = 1
        gpusPerNode = 0
        partition = ""
        account = ""
        qos = ""
        syncBeforeLaunch = false
        respectGitignore = true
    }

    func launchJob() {
        guard let host = selectedHost else { return }

        isLaunching = true

        // Build launch request
        let request = LaunchJobRequest(
            scriptPath: "",
            sourceDir: sourceDir.isEmpty ? nil : sourceDir,
            host: host.hostname,
            jobName: jobName,
            slurmParams: SlurmParameters(
                partition: partition.isEmpty ? nil : partition,
                nodes: nodes,
                cpus: cpus,
                memory: memory,
                time: timeLimit,
                gpus: gpusPerNode > 0 ? gpusPerNode : nil,
                account: account.isEmpty ? nil : account,
                qos: qos.isEmpty ? nil : qos,
                array: nil,
                exclusive: nil
            ),
            syncSettings: syncBeforeLaunch ? SyncSettings(
                excludePatterns: nil,
                includePatterns: nil,
                dryRun: false
            ) : nil
        )

        APIClient.shared.launchJob(request)
            .sink(
                receiveCompletion: { [weak self] completion in
                    self?.isLaunching = false
                    if case .failure(let error) = completion {
                        HapticManager.notification(.error)
                        ToastManager.shared.show("Failed to launch job: \(error.localizedDescription)", type: .error)
                    }
                },
                receiveValue: { [weak self] response in
                    HapticManager.notification(.success)
                    ToastManager.shared.show("Job \(response.jobId) submitted successfully", type: .success)
                    self?.resetToDefaults()
                }
            )
            .store(in: &cancellables)
    }
}

// MARK: - Preview
#Preview {
    LaunchJobView()
}
