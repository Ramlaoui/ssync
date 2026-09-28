import SwiftUI

/// The modal launch task. It opens over any tab and closes back to where the user was.
struct LaunchFlow: View {
  var initial: LaunchDraft?
  let connectionID: UUID
  var body: some View {
    NavigationStack {
      if let initial {
        if initial.launchID != nil || initial.submittedJobID != nil || initial.submissionUnknown {
          LaunchStatusRoot(draft: initial, connectionID: connectionID)
        } else {
          LaunchEditor(initial: initial, connectionID: connectionID)
        }
      } else {
        LaunchStart(connectionID: connectionID)
      }
    }
    .interactiveDismissDisabled()
  }
}

private struct LaunchStatusRoot: View {
  @State var draft: LaunchDraft
  let connectionID: UUID
  var body: some View { LaunchReview(draft: $draft, connectionID: connectionID) }
}

struct LaunchStart: View {
  let connectionID: UUID
  @Environment(AppStore.self) private var store
  @State private var editing: LaunchDraft?
  @State private var loadingJob: JobID?
  @State private var error: String?
  private func decode(_ saved: SavedDraft) -> LaunchDraft? {
    try? JSONDecoder().decode(LaunchDraft.self, from: saved.payload)
  }
  var recipes: [SavedDraft] { store.drafts.filter(\.isTemplate) }
  var drafts: [(SavedDraft, LaunchDraft)] {
    store.drafts.filter { !$0.isTemplate }.compactMap { saved in
      guard let draft = decode(saved), draft.launchID == nil, draft.submittedJobID == nil,
        !draft.submissionUnknown
      else { return nil }
      return (saved, draft)
    }
  }
  var recentJobs: [Job] {
    Array(
      store.listedJobs.sorted {
        $0.number.localizedStandardCompare($1.number) == .orderedDescending
      }.prefix(5))
  }
  var body: some View {
    List {
      Section {
        Button {
          var draft = LaunchDraft()
          draft.host = store.hosts.first?.hostname ?? ""
          editing = draft
        } label: {
          Label("Blank script", systemImage: "doc.badge.plus")
        }.accessibilityIdentifier("blankLaunch")
        if store.demo {
          Button {
            editing = .sample
          } label: {
            Label("protein-fold recipe (sample)", systemImage: "square.stack")
          }
        }
      }
      if let error {
        Label(error, systemImage: "exclamationmark.triangle").foregroundStyle(Theme.amber)
          .font(.subheadline)
      }
      if !recentJobs.isEmpty {
        Section("Relaunch a recent job") {
          ForEach(recentJobs) { job in
            Button {
              relaunch(job)
            } label: {
              HStack {
                JobRow(job: job)
                if loadingJob == job.id { ProgressView() }
              }
            }.tint(.primary).disabled(loadingJob != nil)
          }
        }
      }
      if !recipes.isEmpty {
        Section("Recipes") {
          ForEach(recipes) { saved in
            Button {
              guard var draft = decode(saved) else { return }
              draft.id = UUID()
              draft.launchID = nil
              draft.submittedJobID = nil
              draft.submissionUnknown = false
              editing = draft
            } label: {
              Label(
                saved.name.isEmpty ? "Untitled recipe" : saved.name, systemImage: "square.stack")
            }.tint(.primary)
              .swipeActions { deleteButton(saved) }
          }
        }
      }
      if !drafts.isEmpty {
        Section("Drafts") {
          ForEach(drafts, id: \.0.id) { saved, draft in
            Button {
              editing = draft
            } label: {
              LabeledContent {
                Text(Format.age(saved.updatedAt)).font(.caption)
              } label: {
                Label(draft.name.isEmpty ? "Untitled launch" : draft.name, systemImage: "doc.text")
              }
            }.tint(.primary)
              .swipeActions { deleteButton(saved) }
          }
        }
      }
    }
    .navigationTitle("New launch")
    .navigationBarTitleDisplayMode(.inline)
    .toolbar {
      ToolbarItem(placement: .cancellationAction) { Button("Cancel") { store.launch = nil } }
    }
    .navigationDestination(item: $editing) { draft in
      LaunchEditor(initial: draft, connectionID: connectionID)
    }
    .onAppear { store.reloadDrafts() }
  }
  private func deleteButton(_ saved: SavedDraft) -> some View {
    Button("Delete", systemImage: "trash", role: .destructive) {
      do {
        try store.storage.deleteDraft(saved.id, connectionID: connectionID)
        store.reloadDrafts()
      } catch { self.error = error.localizedDescription }
    }
  }
  private func relaunch(_ job: Job) {
    loadingJob = job.id
    Task {
      defer { loadingJob = nil }
      do {
        editing = try await store.relaunchDraft(for: job)
        error = nil
      } catch { self.error = error.localizedDescription }
    }
  }
}

struct LaunchEditor: View {
  var initial: LaunchDraft
  let connectionID: UUID
  @Environment(AppStore.self) private var store
  @State private var draft: LaunchDraft
  @State private var review = false
  @State private var error: String?
  @State private var confirmClose = false
  @State private var recipeSaved = false
  init(initial: LaunchDraft, connectionID: UUID) {
    self.initial = initial
    self.connectionID = connectionID
    _draft = State(initialValue: initial)
  }
  var partitions: [String] {
    let known =
      store.partitions.first { $0.hostname == draft.host }?.partitions.map {
        $0.partition.trimmingCharacters(in: CharacterSet(charactersIn: "*"))
      } ?? []
    return draft.partition.isEmpty || known.contains(draft.partition)
      ? known : known + [draft.partition]
  }
  var body: some View {
    Form {
      if draft.submissionUnknown {
        Section {
          Label(
            "The last submission's result is unknown. Check recent jobs before launching again.",
            systemImage: "exclamationmark.triangle"
          ).foregroundStyle(Theme.amber)
        }
      }
      Section {
        TextField("Job name", text: $draft.name).accessibilityIdentifier("launchName")
          .textInputAutocapitalization(.never).autocorrectionDisabled()
        Picker("Host", selection: $draft.host) {
          if draft.host.isEmpty { Text("Choose").tag("") }
          ForEach(store.hosts) { Text($0.hostname).tag($0.hostname) }
        }
        Picker("Partition", selection: $draft.partition) {
          Text("Default").tag("")
          ForEach(partitions, id: \.self) { Text($0).tag($0) }
        }
      } footer: {
        if let provenance = draft.provenance { Text(provenance) }
      }
      Section("Resources") {
        numberField("CPUs", text: $draft.cpus)
        numberField("Memory", unit: "GB", text: $draft.memory)
        numberField("GPUs per node", text: $draft.gpus)
        numberField("Nodes", text: $draft.nodes)
        numberField(
          "Time limit", unit: Int(draft.minutes).map { Format.duration("\($0):00") } ?? "min",
          text: $draft.minutes)
      }
      Section {
        NavigationLink {
          ScriptEditor(script: $draft.script)
        } label: {
          VStack(alignment: .leading, spacing: 6) {
            Text("Script")
            Text(scriptPreview).font(.system(.caption2, design: .monospaced))
              .foregroundStyle(.secondary).lineLimit(4)
          }
        }
        NavigationLink {
          SourceSyncForm(draft: $draft)
        } label: {
          LabeledContent(
            "Source sync",
            value: draft.syncSource ? (draft.source.isEmpty ? "On" : draft.source) : "Off")
        }
        NavigationLink {
          AdvancedLaunchForm(draft: $draft)
        } label: {
          LabeledContent("Advanced", value: advancedSummary)
        }
      }
      if let error { Section { Text(error).foregroundStyle(Theme.red) } }
    }
    .navigationTitle(draft.name.isEmpty ? "New launch" : draft.name)
    .navigationBarTitleDisplayMode(.inline)
    .toolbar {
      ToolbarItem(placement: .cancellationAction) {
        Button("Cancel") {
          if draft == initial { store.launch = nil } else { confirmClose = true }
        }
      }
      ToolbarItem(placement: .topBarTrailing) {
        Menu {
          Button("Save draft", systemImage: "square.and.arrow.down") {
            if persist() { store.launch = nil }
          }
          Button(recipeSaved ? "Saved as recipe" : "Save as recipe", systemImage: "square.stack") {
            saveRecipe()
          }
        } label: {
          Label("Save", systemImage: "ellipsis")
        }
      }
      ToolbarItem(placement: .confirmationAction) {
        Button("Review") {
          if let validation = draft.validation {
            error = validation
          } else {
            error = nil
            review = true
          }
        }
        .disabled(draft.submissionUnknown)
        .accessibilityIdentifier("reviewLaunch")
      }
    }
    .confirmationDialog("Keep this launch?", isPresented: $confirmClose) {
      Button("Save draft") { if persist() { store.launch = nil } }
      Button("Discard", role: .destructive) { store.launch = nil }
    }
    .navigationDestination(isPresented: $review) {
      LaunchReview(draft: $draft, connectionID: connectionID)
    }
    .onChange(of: store.connection?.id) { _, id in if id != connectionID { store.launch = nil } }
  }
  private var scriptPreview: String {
    draft.script.split(separator: "\n").filter {
      !$0.trimmingCharacters(in: .whitespaces).isEmpty && !$0.hasPrefix("#!")
    }.prefix(4).joined(separator: "\n")
  }
  private var advancedSummary: String {
    let set = [
      draft.account, draft.qos, draft.constraint, draft.gres, draft.output, draft.errorOutput,
      draft.pythonEnvironment, draft.tasksPerNode,
    ].filter { !$0.isEmpty }.count
    return set == 0 ? "Defaults" : "\(set) set"
  }
  private func numberField(_ title: String, unit: String? = nil, text: Binding<String>)
    -> some View
  {
    LabeledContent(title) {
      HStack(spacing: 6) {
        TextField("Default", text: text).keyboardType(.numberPad).multilineTextAlignment(.trailing)
        if let unit, !text.wrappedValue.isEmpty {
          Text(unit).foregroundStyle(.secondary)
        }
      }.frame(maxWidth: 160)
    }
  }
  @discardableResult private func persist() -> Bool {
    do {
      try store.saveDraft(draft, for: connectionID)
      return true
    } catch {
      self.error = error.localizedDescription
      return false
    }
  }
  private func saveRecipe() {
    var recipe = draft
    recipe.id = UUID()
    recipe.launchID = nil
    recipe.submittedJobID = nil
    recipe.submissionUnknown = false
    recipe.provenance = nil
    do {
      try store.saveDraft(recipe, for: connectionID, template: true)
      recipeSaved = true
    } catch { self.error = error.localizedDescription }
  }
}

struct ScriptEditor: View {
  @Binding var script: String
  var body: some View {
    TextEditor(text: $script)
      .font(.system(.footnote, design: .monospaced))
      .textInputAutocapitalization(.never).autocorrectionDisabled()
      .scrollContentBackground(.hidden).background(Theme.code)
      .accessibilityIdentifier("launchScript")
      .navigationTitle("Script").navigationBarTitleDisplayMode(.inline)
  }
}

struct SourceSyncForm: View {
  @Binding var draft: LaunchDraft
  @State private var browsing = false
  var body: some View {
    Form {
      Section {
        Toggle("Sync a source directory", isOn: $draft.syncSource)
      } footer: {
        Text("Copies a directory from the ssync API server (not this iPhone) before submitting.")
      }
      if draft.syncSource {
        Section("Directory") {
          TextField("Path on the API server", text: $draft.source)
          Button("Browse…", systemImage: "folder") { browsing = true }
        }
        Section("Filters") {
          Toggle("Respect .gitignore", isOn: $draft.useGitignore)
          TextField("Include patterns, one per line", text: $draft.include, axis: .vertical)
          TextField("Exclude patterns, one per line", text: $draft.exclude, axis: .vertical)
        }
      }
    }
    .textInputAutocapitalization(.never).autocorrectionDisabled()
    .navigationTitle("Source sync").navigationBarTitleDisplayMode(.inline)
    .sheet(isPresented: $browsing) {
      NavigationStack { ServerDirectoryBrowser(selected: $draft.source) }
    }
  }
}

struct AdvancedLaunchForm: View {
  @Binding var draft: LaunchDraft
  var body: some View {
    Form {
      Section("Scheduler") {
        TextField("Account", text: $draft.account)
        TextField("Quality of service", text: $draft.qos)
        TextField("Constraint", text: $draft.constraint)
        TextField("GRES", text: $draft.gres)
        TextField("Tasks per node", text: $draft.tasksPerNode).keyboardType(.numberPad)
      }
      Section("Output files") {
        TextField("stdout path", text: $draft.output)
        TextField("stderr path", text: $draft.errorOutput)
      }
      Section("Environment") {
        TextField("Python environment", text: $draft.pythonEnvironment)
        Toggle("Stop if setup fails", isOn: $draft.abortOnSetupFailure)
      }
    }
    .textInputAutocapitalization(.never).autocorrectionDisabled()
    .navigationTitle("Advanced").navigationBarTitleDisplayMode(.inline)
  }
}

struct LaunchReview: View {
  @Binding var draft: LaunchDraft
  let connectionID: UUID
  @Environment(AppStore.self) private var store
  @State private var submitting = false
  @State private var status: JSONValue?
  @State private var error: String?
  var body: some View {
    List {
      Section {
        LabeledContent("Host", value: draft.host)
        LabeledContent("Partition", value: draft.partition.isEmpty ? "Default" : draft.partition)
        LabeledContent("Resources", value: resources)
        LabeledContent(
          "Time limit",
          value: draft.minutes.isEmpty ? "Default" : Format.duration("\(draft.minutes):00"))
        LabeledContent("Source sync", value: draft.syncSource ? draft.source : "Off")
      } footer: {
        Text("Values left as default come from the script's #SBATCH lines or the server.")
      }
      Section {
        DisclosureGroup("Script") {
          Text(draft.script).font(.system(.caption, design: .monospaced)).textSelection(.enabled)
        }
        DisclosureGroup("Exact request") {
          Text(draft.requestBody.pretty).font(.system(.caption, design: .monospaced))
            .textSelection(.enabled)
        }
      }
      if let error {
        Label(error, systemImage: "exclamationmark.triangle").foregroundStyle(Theme.amber)
      }
      if let status { statusSection(status.object) }
      Section { footer }
        .listRowBackground(Color.clear).listRowInsets(EdgeInsets())
    }
    .navigationTitle(draft.name.isEmpty ? "Review" : draft.name)
    .navigationSubtitle("Review before submitting")
    .navigationBarTitleDisplayMode(.inline)
    .toolbar {
      if draft.launchID != nil || draft.submittedJobID != nil || draft.submissionUnknown {
        ToolbarItem(placement: .confirmationAction) { Button("Done") { store.launch = nil } }
      }
    }
    .task(id: draft.launchID) { await watchStatus() }
  }
  private var resources: String {
    let parts = [
      draft.cpus.isEmpty ? nil : "\(draft.cpus) CPU",
      draft.memory.isEmpty ? nil : "\(draft.memory) GB",
      draft.gpus.isEmpty ? nil : "\(draft.gpus) GPU/node",
      draft.nodes.isEmpty ? nil : "\(draft.nodes) node",
    ].compactMap { $0 }
    return parts.isEmpty ? "Default" : parts.joined(separator: " · ")
  }
  private func statusSection(_ fields: [String: JSONValue]) -> some View {
    Section("Status") {
      Label(
        fields.text("stage", fallback: "Submitting").replacingOccurrences(of: "_", with: " ")
          .capitalized,
        systemImage: fields.flag("terminal")
          ? "checkmark.circle" : "arrow.trianglehead.2.clockwise.rotate.90")
      ForEach(Array((fields["events"]?.array ?? []).enumerated()), id: \.offset) { _, event in
        Text(event.object.text("message", fallback: event.pretty)).font(.caption)
          .foregroundStyle(.secondary)
      }
    }
  }
  @ViewBuilder private var footer: some View {
    VStack(spacing: 10) {
      if let number = draft.submittedJobID {
        Label("Submitted as #\(number) on \(draft.host)", systemImage: "checkmark.circle.fill")
          .foregroundStyle(Theme.green).font(.headline)
        Button {
          store.launch = nil
          store.tab = .jobs
          store.jobPath.append(.job(JobID(host: draft.host, number: number)))
        } label: {
          Text("Open job").frame(maxWidth: .infinity)
        }.buttonStyle(.borderedProminent).controlSize(.large)
      } else if draft.submissionUnknown {
        Text(
          "The connection dropped during submission, so the result is unknown. Check recent jobs on \(draft.host) before launching again."
        ).font(.subheadline).foregroundStyle(Theme.amber)
      } else if draft.launchID != nil {
        ProgressView("Waiting for \(draft.host)…")
      } else {
        Button {
          Task { await submit() }
        } label: {
          HStack {
            if submitting { ProgressView().tint(.white) }
            Text(store.demo ? "Simulate launch on \(draft.host)" : "Submit to \(draft.host)")
          }.frame(maxWidth: .infinity)
        }
        .buttonStyle(.borderedProminent).controlSize(.large)
        .disabled(submitting || draft.validation != nil)
        .accessibilityIdentifier("submitLaunch")
        Text(
          store.demo
            ? "Demo: this creates a sample job only."
            : "This uses cluster resources. You can close this sheet; progress is kept in Activity."
        ).font(.caption).foregroundStyle(.secondary).multilineTextAlignment(.center)
      }
    }.frame(maxWidth: .infinity).padding(.vertical, 8)
  }
  private func submit() async {
    guard store.connection?.id == connectionID, !submitting, draft.validation == nil,
      draft.launchID == nil, draft.submittedJobID == nil
    else { return }
    submitting = true
    error = nil
    defer { submitting = false }
    do {
      if store.demo {
        let number = String(Int.random(in: 50_000...59_999))
        store.upsert(
          DemoData.job(
            number, name: draft.name.isEmpty ? "New job" : draft.name, host: draft.host,
            state: "PD", partition: draft.partition))
        draft.submittedJobID = number
        try store.saveDraft(draft, for: connectionID)
        return
      }
      guard let api = store.client else { return }
      draft.submissionUnknown = true
      try store.saveDraft(draft, for: connectionID)
      let response: JSONValue = try await api.send(
        "api/jobs/launch", method: "POST", body: draft.requestBody)
      let fields = response.object
      draft.launchID = fields["launch_id"]?.string
      draft.submittedJobID = fields["job_id"]?.string
      draft.submissionUnknown =
        draft.launchID == nil && draft.submittedJobID == nil && fields.flag("success")
      if !fields.flag("success") {
        error = fields.text("message", fallback: "The server did not accept the launch.")
      }
      try store.saveDraft(draft, for: connectionID)
    } catch {
      if let api = error as? APIError, api.status >= 400 && api.status < 500 {
        draft.submissionUnknown = false
      }
      self.error = error.localizedDescription
      try? store.saveDraft(draft, for: connectionID)
    }
  }
  private func watchStatus() async {
    guard store.connection?.id == connectionID, let id = draft.launchID, let api = store.client
    else { return }
    while !Task.isCancelled {
      do {
        let response: JSONValue = try await api.send("api/launches/\(id)")
        status = response
        error = nil
        if response.object.flag("terminal") {
          if let number = response.object["job_id"]?.string { draft.submittedJobID = number }
          if !response.object.flag("success") {
            error = response.object.text("message", fallback: "Launch did not complete.")
          }
          try store.saveDraft(draft, for: connectionID)
          await store.refresh()
          return
        }
        try await Task.sleep(for: .seconds(2))
      } catch {
        if Task.isCancelled { return }
        self.error =
          "Status temporarily unavailable: \(error.localizedDescription). The operation ID is saved."
        do { try await Task.sleep(for: .seconds(5)) } catch { return }
      }
    }
  }
}

struct ServerDirectoryBrowser: View {
  @Binding var selected: String
  @Environment(AppStore.self) private var store
  @Environment(\.dismiss) private var dismiss
  @State private var path = ""
  @State private var entries: [JSONValue] = []
  @State private var error: String?
  @State private var loading = false
  var body: some View {
    List {
      Section {
        TextField("Directory path", text: $path).textInputAutocapitalization(.never)
          .autocorrectionDisabled().onSubmit { Task { await load(path) } }
          .font(.system(.body, design: .monospaced))
      } footer: {
        Text("Folders on the ssync API server.")
      }
      if let error { Text(error).foregroundStyle(Theme.red) }
      Section {
        if !path.isEmpty && path != "/" {
          Button("Parent folder", systemImage: "arrow.turn.left.up") {
            Task { await load((path as NSString).deletingLastPathComponent) }
          }
        }
        ForEach(Array(entries.enumerated()), id: \.offset) { _, entry in
          Button {
            Task { await load(entry.object.text("path")) }
          } label: {
            Label(entry.object.text("name"), systemImage: "folder")
          }.tint(.primary)
        }
      }
    }
    .overlay { if loading { ProgressView() } }
    .navigationTitle(
      (path as NSString).lastPathComponent.isEmpty
        ? "Choose folder" : (path as NSString).lastPathComponent
    )
    .navigationBarTitleDisplayMode(.inline)
    .toolbar {
      ToolbarItem(placement: .cancellationAction) { Button("Cancel") { dismiss() } }
      ToolbarItem(placement: .confirmationAction) {
        Button("Use folder") {
          selected = path
          dismiss()
        }.disabled(path.isEmpty)
      }
    }
    .task { await load(selected) }
  }
  private func load(_ target: String) async {
    loading = true
    error = nil
    defer { loading = false }
    if store.demo {
      path = target.isEmpty ? "/home/alex" : target
      entries = ["folding", "datasets", "experiments"].map {
        .object(["name": .string($0), "path": .string(path + "/" + $0)])
      }
      return
    }
    do {
      let value: JSONValue = try await store.client.orThrow().send(
        "api/local/list", query: ["path": target, "dirs_only": "true", "limit": "300"])
      path = value.object.text("path")
      entries = value.object["entries"]?.array ?? []
    } catch { self.error = error.localizedDescription }
  }
}
