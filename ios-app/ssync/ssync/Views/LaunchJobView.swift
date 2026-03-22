import SwiftUI

struct LaunchJobView: View {
    @Environment(\.dismiss) private var dismiss

    @State private var scriptContent = """
#!/bin/bash
#SBATCH --job-name=ssync-job

echo "Starting job..."
"""
    @State private var sourceDir = ""
    @State private var selectedHost = ""
    @State private var jobName = ""

    @State private var partition = ""
    @State private var nodes = ""
    @State private var cpus = ""
    @State private var memory = ""
    @State private var timeLimit = ""
    @State private var gpus = ""
    @State private var account = ""

    @State private var hosts: [Host] = []
    @State private var isLoadingHosts = false
    @State private var isLaunching = false
    @State private var showAdvancedOptions = false
    @State private var showingDirectoryPicker = false
    @State private var launchResult: LaunchJobResponse?
    @State private var errorMessage: String?

    var body: some View {
        Form {
            if let launchResult {
                Section("Last Submission") {
                    LabeledContent("Status", value: launchResult.success ? "Submitted" : "Failed")
                    if let jobId = launchResult.jobId {
                        LabeledContent("Job ID", value: jobId)
                    }
                    LabeledContent("Host", value: launchResult.host)
                    LabeledContent("Server Message", value: launchResult.message)

                    if let warning = launchResult.directoryWarning,
                       !warning.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
                        Text(warning)
                            .font(.caption)
                            .foregroundColor(.orange)
                    }
                }
            }

            Section("Host") {
                if isLoadingHosts && hosts.isEmpty {
                    HStack(spacing: 12) {
                        ProgressView()
                        Text("Loading hosts...")
                            .foregroundColor(.secondary)
                    }
                } else if hosts.isEmpty {
                    VStack(alignment: .leading, spacing: 8) {
                        Text("No hosts available")
                            .foregroundColor(.secondary)
                        Button("Retry") {
                            Task { await loadHosts(forceRefresh: true) }
                        }
                    }
                } else {
                    Picker("Target Host", selection: $selectedHost) {
                        Text("Select Host").tag("")
                        ForEach(hosts, id: \.id) { host in
                            Text(host.displayName).tag(host.hostname)
                        }
                    }

                    if let host = selectedHostInfo,
                       let defaults = host.slurmDefaults {
                        VStack(alignment: .leading, spacing: 6) {
                            Text("Host defaults")
                                .font(.caption)
                                .foregroundColor(.secondary)

                            HostDefaultsSummary(defaults: defaults)
                        }
                        .padding(.top, 4)
                    }
                }
            }

            Section("Job Configuration") {
                TextField("Job Name (optional)", text: $jobName)

                HStack(spacing: 8) {
                    TextField("Source Directory (optional)", text: $sourceDir)
                        .textInputAutocapitalization(.never)
                        .autocorrectionDisabled()

                    Button {
                        showingDirectoryPicker = true
                    } label: {
                        Image(systemName: "folder")
                    }
                    .disabled(selectedHost.isEmpty)
                }

                Text("Leave the source directory empty to submit a script without syncing local files.")
                    .font(.caption2)
                    .foregroundColor(.secondary)
            }

            Section("Script") {
                TextEditor(text: $scriptContent)
                    .font(.system(.caption, design: .monospaced))
                    .frame(minHeight: 220)
            }

            Section {
                DisclosureGroup("SLURM Overrides", isExpanded: $showAdvancedOptions) {
                    TextField("Partition", text: $partition)
                    TextField("Nodes", text: $nodes)
                        .keyboardType(.numberPad)
                    TextField("CPUs", text: $cpus)
                        .keyboardType(.numberPad)
                    TextField("Memory in GB (e.g. 32)", text: $memory)
                        .keyboardType(.numberPad)
                    TextField("Time in minutes or HH:MM:SS", text: $timeLimit)
                        .textInputAutocapitalization(.never)
                        .autocorrectionDisabled()
                    TextField("GPUs per node", text: $gpus)
                        .keyboardType(.numberPad)
                    TextField("Account", text: $account)
                        .textInputAutocapitalization(.never)
                        .autocorrectionDisabled()
                }
            }

            Section {
                Text("For advanced directives such as QoS, arrays, constraints, or exclusive scheduling, add `#SBATCH` lines directly in the script.")
                    .font(.caption2)
                    .foregroundColor(.secondary)
            }

            if let errorMessage {
                Section {
                    Label(errorMessage, systemImage: "exclamationmark.triangle.fill")
                        .foregroundColor(.red)
                        .font(.caption)
                }
            }

            Section {
                Button(action: {
                    Task { await launchJob() }
                }) {
                    HStack {
                        if isLaunching {
                            ProgressView()
                                .scaleEffect(0.9)
                        } else {
                            Image(systemName: "play.circle.fill")
                        }
                        Text(isLaunching ? "Submitting..." : "Launch Job")
                            .fontWeight(.semibold)
                    }
                    .frame(maxWidth: .infinity)
                }
                .disabled(!canSubmit)
            }
        }
        .navigationTitle("Launch")
        .refreshable {
            await loadHosts(forceRefresh: true)
        }
        .task {
            await loadHosts(forceRefresh: false)
        }
        .onChange(of: selectedHost) { _ in
            applyHostDefaultsIfNeeded()
        }
        .sheet(isPresented: $showingDirectoryPicker) {
            NavigationView {
                DirectoryPickerView(
                    initialPath: sourceDir.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty ? "/Users" : sourceDir,
                    selectedPath: $sourceDir
                )
            }
        }
    }

    private var canSubmit: Bool {
        !scriptContent.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty &&
        !selectedHost.isEmpty &&
        !isLaunching
    }

    private var selectedHostInfo: Host? {
        hosts.first { $0.hostname == selectedHost }
    }

    private func loadHosts(forceRefresh: Bool) async {
        if isLoadingHosts { return }
        if !forceRefresh && !hosts.isEmpty { return }

        isLoadingHosts = true
        errorMessage = nil
        defer { isLoadingHosts = false }

        do {
            let fetchedHosts = try await APIClient.shared.getHosts().async()
            hosts = fetchedHosts.sorted {
                $0.displayName.localizedCaseInsensitiveCompare($1.displayName) == .orderedAscending
            }

            if selectedHost.isEmpty {
                selectedHost = hosts.first(where: { $0.isDefault })?.hostname ?? hosts.first?.hostname ?? ""
            } else if !hosts.contains(where: { $0.hostname == selectedHost }) {
                selectedHost = hosts.first?.hostname ?? ""
            }

            applyHostDefaultsIfNeeded()
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    @MainActor
    private func launchJob() async {
        guard canSubmit else { return }

        isLaunching = true
        errorMessage = nil
        defer { isLaunching = false }

        let request = LaunchJobRequest(
            scriptContent: scriptContent.trimmingCharacters(in: .whitespacesAndNewlines),
            sourceDir: sourceDir,
            host: selectedHost,
            jobName: normalized(jobName),
            slurmParams: makeSlurmParameters(),
            syncSettings: nil
        )

        do {
            let response = try await APIClient.shared.launchJob(request).async()
            launchResult = response

            if response.success {
                let successLabel = response.jobId.map { "Submitted job \($0)" } ?? response.message
                ToastManager.shared.show(successLabel, type: .success)
                resetFormAfterLaunch()
                dismiss()
            } else {
                errorMessage = response.message
            }
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    private func makeSlurmParameters() -> SlurmParameters? {
        let params = SlurmParameters(
            partition: normalized(partition),
            nodes: normalizedInt(nodes),
            cpus: normalizedInt(cpus),
            memory: normalized(memory),
            time: normalized(timeLimit),
            gpus: normalizedInt(gpus),
            account: normalized(account),
            qos: nil,
            array: nil,
            exclusive: nil
        )

        let hasOverrides = params.partition != nil ||
            params.nodes != nil ||
            params.cpus != nil ||
            params.memory != nil ||
            params.time != nil ||
            params.gpus != nil ||
            params.account != nil

        return hasOverrides ? params : nil
    }

    private func applyHostDefaultsIfNeeded() {
        guard let defaults = selectedHostInfo?.slurmDefaults else { return }

        if partition.isEmpty, let defaultPartition = defaults.partition {
            partition = defaultPartition
        }
        if cpus.isEmpty, let defaultCPUs = defaults.cpus {
            cpus = String(defaultCPUs)
        }
        if memory.isEmpty, let defaultMem = defaults.mem {
            memory = String(defaultMem)
        }
        if timeLimit.isEmpty, let defaultTime = defaults.time {
            timeLimit = defaultTime
        }
        if nodes.isEmpty, let defaultNodes = defaults.nodes {
            nodes = String(defaultNodes)
        }
        if gpus.isEmpty, let defaultGPUs = defaults.gpusPerNode {
            gpus = String(defaultGPUs)
        }
        if account.isEmpty, let defaultAccount = defaults.account {
            account = defaultAccount
        }
    }

    private func resetFormAfterLaunch() {
        jobName = ""
        partition = ""
        nodes = ""
        cpus = ""
        memory = ""
        timeLimit = ""
        gpus = ""
        account = ""
    }

    private func normalized(_ value: String) -> String? {
        let trimmed = value.trimmingCharacters(in: .whitespacesAndNewlines)
        return trimmed.isEmpty ? nil : trimmed
    }

    private func normalizedInt(_ value: String) -> Int? {
        Int(value.trimmingCharacters(in: .whitespacesAndNewlines))
    }
}

private struct HostDefaultsSummary: View {
    let defaults: HostSlurmDefaults

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            if let partition = defaults.partition {
                Text("Partition: \(partition)")
            }
            if let cpus = defaults.cpus {
                Text("CPUs: \(cpus)")
            }
            if let mem = defaults.mem {
                Text("Memory: \(mem) GB")
            }
            if let time = defaults.time {
                Text("Time: \(time)")
            }
            if let gpus = defaults.gpusPerNode {
                Text("GPUs: \(gpus)")
            }
        }
        .font(.caption2)
        .foregroundColor(.secondary)
    }
}

private struct DirectoryPickerView: View {
    @Environment(\.dismiss) private var dismiss

    let initialPath: String
    @Binding var selectedPath: String

    @State private var currentPath: String
    @State private var entries: [FileEntry] = []
    @State private var isLoading = false
    @State private var errorMessage: String?

    init(initialPath: String, selectedPath: Binding<String>) {
        self.initialPath = initialPath
        _selectedPath = selectedPath
        _currentPath = State(initialValue: initialPath)
    }

    var body: some View {
        List {
            Section("Current Folder") {
                Text(currentPath)
                    .font(.caption)
                    .foregroundColor(.secondary)

                Button("Use This Folder") {
                    selectedPath = currentPath
                    dismiss()
                }
            }

            if let parentPath = parentPath, parentPath != currentPath {
                Section {
                    Button {
                        currentPath = parentPath
                        Task { await loadEntries() }
                    } label: {
                        Label("..", systemImage: "arrow.up.left")
                    }
                }
            }

            if isLoading {
                Section {
                    HStack {
                        ProgressView()
                        Text("Loading directories...")
                    }
                }
            }

            if let errorMessage {
                Section {
                    Text(errorMessage)
                        .font(.caption)
                        .foregroundColor(.red)
                }
            }

            Section("Directories") {
                ForEach(entries.filter(\.isDir)) { entry in
                    Button {
                        currentPath = entry.path
                        Task { await loadEntries() }
                    } label: {
                        Label(entry.name, systemImage: "folder")
                    }
                }
            }
        }
        .navigationTitle("Source Directory")
        .toolbar {
            ToolbarItem(placement: .navigationBarLeading) {
                Button("Cancel") {
                    dismiss()
                }
            }

            ToolbarItem(placement: .navigationBarTrailing) {
                Button {
                    Task { await loadEntries(force: true) }
                } label: {
                    Image(systemName: "arrow.clockwise")
                }
            }
        }
        .task {
            await loadEntries()
        }
    }

    private var parentPath: String? {
        let normalized = NSString(string: currentPath).standardizingPath
        let parent = NSString(string: normalized).deletingLastPathComponent
        guard !parent.isEmpty else { return nil }
        return parent
    }

    private func loadEntries(force: Bool = false) async {
        if isLoading && !force { return }
        isLoading = true
        errorMessage = nil
        defer { isLoading = false }

        do {
            let response = try await APIClient.shared.browseFiles(path: currentPath, showHidden: false, dirsOnly: true).async()
            entries = response.entries.sorted {
                $0.name.localizedCaseInsensitiveCompare($1.name) == .orderedAscending
            }
        } catch {
            errorMessage = error.localizedDescription
        }
    }
}
