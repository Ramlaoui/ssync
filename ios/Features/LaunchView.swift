import SwiftUI

struct LaunchLibraryView: View {
  @Environment(AppStore.self) private var store
  @State private var editing: LaunchDraft?
  @State private var error: String?
  var body: some View {
    Screen {
      ConnectionStatus()
      Button {
        var draft = LaunchDraft()
        draft.host = store.hosts.first?.hostname ?? ""
        editing = draft
      } label: {
        Label("New launch", systemImage: "plus")
      }.buttonStyle(PrimaryButtonStyle()).accessibilityIdentifier("newLaunch")
      if let error { Notice(title: "Draft storage", detail: error, warning: true) }
      SectionHeading(title: "Drafts", detail: "Saved on this device")
      let drafts = store.drafts.filter { !$0.isTemplate }
      if drafts.isEmpty {
        EmptyState(
          title: "No drafts",
          detail: "Start a new launch or prepare a relaunch from a job.", symbol: "arrow.up.right")
      }
      ForEach(drafts) { saved in draftRow(saved, template: false) }
      SectionHeading(title: "Your recipes")
      ForEach(store.drafts.filter(\.isTemplate)) { saved in draftRow(saved, template: true) }
      if store.demo {
        Button {
          editing = .sample
        } label: {
          Paper {
            HStack {
              Image("launch-recipe").foregroundStyle(Theme.accent)
              VStack(alignment: .leading, spacing: 5) {
                Text("Protein folding").font(.headline)
                Text("4 GPUs · 32 CPUs · 8 hours").font(.caption).foregroundStyle(Theme.secondary)
              }
              Spacer()
              Image(systemName: "arrow.up.right")
            }
          }
        }.buttonStyle(.plain)
      }
    }.navigationTitle("Launch").navigationBarTitleDisplayMode(.inline).rootToolbar()
      .sheet(item: $editing, onDismiss: { store.reloadDrafts() }) { draft in
        if let connection = store.connection {
          NavigationStack { LaunchEditor(initial: draft, connectionID: connection.id) }
        }
      }
      .onAppear {
        store.reloadDrafts()
        openPending()
      }
      .onChange(of: store.draftToOpen?.id) { _, _ in openPending() }
  }
  private func openPending() {
    if let draft = store.draftToOpen {
      editing = draft
      store.draftToOpen = nil
    }
  }
  private func draftRow(_ saved: SavedDraft, template: Bool) -> some View {
    Button {
      guard var draft = try? JSONDecoder().decode(LaunchDraft.self, from: saved.payload) else {
        error = "This draft couldn’t be read."
        return
      }
      if template {
        draft.id = UUID()
        draft.launchID = nil
        draft.submittedJobID = nil
        draft.submissionUnknown = false
      }
      editing = draft
    } label: {
      Paper {
        HStack(spacing: 12) {
          Image(systemName: template ? "square.stack" : "doc.text").foregroundStyle(Theme.accent)
          VStack(alignment: .leading, spacing: 6) {
            Text(saved.name.isEmpty ? "Untitled launch" : saved.name).font(.headline)
            Text("Edited \(Format.age(saved.updatedAt).lowercased())").font(.caption)
              .foregroundStyle(Theme.secondary)
          }
          Spacer()
          Image(systemName: "chevron.right").font(.caption)
        }
      }
    }.buttonStyle(.plain).contextMenu {
      Button("Delete \(template ? "recipe" : "draft")", role: .destructive) {
        do {
          if let connection = store.connection {
            try store.storage.deleteDraft(saved.id, connectionID: connection.id)
            store.reloadDrafts()
          }
        } catch { self.error = error.localizedDescription }
      }
    }
  }
}
struct LaunchEditor: View {
  var initial: LaunchDraft
  let connectionID: UUID
  @Environment(AppStore.self) private var store
  @Environment(\.dismiss) private var dismiss
  @State private var draft: LaunchDraft
  @State private var showBrowser = false
  @State private var review = false
  @State private var error: String?
  @State private var recipeSaved = false
  init(initial: LaunchDraft, connectionID: UUID) {
    self.initial = initial
    self.connectionID = connectionID
    _draft = State(initialValue: initial)
  }
  var body: some View {
    Form {
      if let provenance = draft.provenance {
        Section { Text(provenance).font(.caption).foregroundStyle(.secondary) }
      }
      if draft.submissionUnknown {
        Section {
          Text(
            "Submission result unknown. Check recent jobs before launching again. This draft is locked to prevent an accidental duplicate."
          ).foregroundStyle(Theme.amber)
        }
      }
      Section("Destination") {
        TextField("Job name", text: $draft.name).accessibilityIdentifier("launchName")
        Picker("Host", selection: $draft.host) {
          Text("Choose host").tag("")
          ForEach(store.hosts) { Text($0.hostname).tag($0.hostname) }
        }
        TextField("Partition (server default if blank)", text: $draft.partition)
          .textInputAutocapitalization(.never)
      }
      Section {
        Toggle("Sync a source directory", isOn: $draft.syncSource)
        if draft.syncSource {
          TextField("Directory on the API server", text: $draft.source).textInputAutocapitalization(
            .never
          ).autocorrectionDisabled()
          Button("Browse server directories", systemImage: "folder") { showBrowser = true }
          Toggle("Respect .gitignore", isOn: $draft.useGitignore)
          TextField(
            "Additional include patterns (one per line)", text: $draft.include, axis: .vertical
          ).textInputAutocapitalization(.never)
          TextField("Exclude patterns (one per line)", text: $draft.exclude, axis: .vertical)
            .textInputAutocapitalization(.never)
        }
      } header: {
        Text("Source")
      } footer: {
        Text(
          "The source belongs to the ssync API server, not this iPhone. Leave sync off to submit a script without copying a source directory."
        )
      }
      Section("Submission script") {
        TextEditor(text: $draft.script).font(.system(.caption, design: .monospaced))
          .frame(minHeight: 220).textInputAutocapitalization(.never).autocorrectionDisabled()
          .accessibilityIdentifier("launchScript")
      }
      Section {
        numberField("CPUs", text: $draft.cpus)
        numberField("Memory (GB)", text: $draft.memory)
        numberField("Time limit (minutes)", text: $draft.minutes)
        numberField("Nodes", text: $draft.nodes)
        numberField("GPUs per node", text: $draft.gpus)
        numberField("Tasks per node", text: $draft.tasksPerNode)
      } header: {
        Text("Resources")
      } footer: {
        Text(
          "Blank values retain the script or server defaults. Explicit values override script directives. Review final scheduler requests before submitting."
        )
      }
      Section("Advanced") {
        TextField("Account", text: $draft.account)
        TextField("Quality of service", text: $draft.qos)
        TextField("Constraint", text: $draft.constraint)
        TextField("GRES", text: $draft.gres)
        TextField("stdout path", text: $draft.output)
        TextField("stderr path", text: $draft.errorOutput)
        TextField("Python environment", text: $draft.pythonEnvironment)
        Toggle("Stop if environment setup fails", isOn: $draft.abortOnSetupFailure)
      }.textInputAutocapitalization(.never).autocorrectionDisabled()
      if let error { Section { Text(error).foregroundStyle(Theme.red) } }
      Section {
        Button("Review launch", systemImage: "arrow.up.right") {
          if let validation = draft.validation {
            error = validation
          } else {
            persist()
            review = true
          }
        }.disabled(draft.submissionUnknown || draft.submittedJobID != nil || draft.launchID != nil)
          .accessibilityIdentifier("reviewLaunch")
        if draft.launchID != nil || draft.submittedJobID != nil {
          Button("View submission status") { review = true }
        }
        Button(
          recipeSaved ? "Recipe saved" : "Save a copy as a recipe", systemImage: "square.stack"
        ) {
          var recipe = draft
          recipe.id = UUID()
          recipe.launchID = nil
          recipe.submittedJobID = nil
          recipe.submissionUnknown = false
          do {
            try store.saveDraft(recipe, for: connectionID, template: true)
            recipeSaved = true
          } catch { self.error = error.localizedDescription }
        }
      }
    }.navigationTitle(draft.name.isEmpty ? "New launch" : draft.name).navigationBarTitleDisplayMode(
      .inline
    )
    .toolbar {
      ToolbarItem(placement: .cancellationAction) {
        Button("Save & close") {
          persist()
          dismiss()
        }
      }
    }
    .navigationDestination(isPresented: $review) {
      LaunchReview(draft: $draft, connectionID: connectionID)
    }
    .sheet(isPresented: $showBrowser) {
      NavigationStack { ServerDirectoryBrowser(selected: $draft.source) }
    }
    .task(id: draft) {
      do {
        try await Task.sleep(for: .milliseconds(600))
        persist()
      } catch {}
    }
    .onDisappear { persist() }
    .onChange(of: store.tab) { _, tab in if tab != .launch { dismiss() } }
    .onChange(of: store.connection?.id) { _, id in if id != connectionID { dismiss() } }
  }
  private func numberField(_ title: String, text: Binding<String>) -> some View {
    HStack {
      Text(title)
      Spacer()
      TextField("Default", text: text).keyboardType(.numberPad).multilineTextAlignment(.trailing)
        .frame(maxWidth: 120)
    }
  }
  private func persist() {
    do { try store.saveDraft(draft, for: connectionID) } catch {
      self.error = error.localizedDescription
    }
  }
}
struct LaunchReview: View {
  @Binding var draft: LaunchDraft
  let connectionID: UUID
  @Environment(AppStore.self) private var store
  @State private var submitting = false
  @State private var status: JSONValue?
  @State private var error: String?
  @State private var confirmed = false
  var body: some View {
    Screen {
      Text(draft.name.isEmpty ? "Untitled launch" : draft.name).font(
        .system(.largeTitle, design: .rounded).weight(.bold))
      Paper {
        VStack(spacing: 16) {
          DetailRow(name: "Host", value: draft.host)
          DetailRow(
            name: "Partition",
            value: draft.partition.isEmpty ? "Script / server default" : draft.partition)
          DetailRow(name: "Source sync", value: draft.syncSource ? draft.source : "Off")
          Divider()
          DetailRow(name: "CPUs", value: defaultText(draft.cpus))
          DetailRow(
            name: "Memory",
            value: draft.memory.isEmpty ? "Script / server default" : "\(draft.memory) GB")
          DetailRow(
            name: "Wall time",
            value: draft.minutes.isEmpty ? "Script / server default" : "\(draft.minutes) minutes")
          DetailRow(name: "GPUs per node", value: defaultText(draft.gpus))
          DetailRow(name: "Nodes", value: defaultText(draft.nodes))
          DetailRow(name: "Account", value: defaultText(draft.account))
        }
      }
      DisclosureGroup("Submission script") {
        Text(draft.script).font(.system(.caption, design: .monospaced)).textSelection(.enabled)
          .frame(maxWidth: .infinity, alignment: .leading).padding(.top)
      }
      DisclosureGroup("Exact request") {
        Text(draft.requestBody.pretty).font(.system(.caption, design: .monospaced)).textSelection(
          .enabled
        ).frame(maxWidth: .infinity, alignment: .leading).padding(.top)
      }
      if let error { Notice(title: "Launch status", detail: error, warning: true) }
      if let status {
        let fields = status.object
        Notice(
          title: fields.text("stage", fallback: "Submitting").replacingOccurrences(
            of: "_", with: " "
          ).capitalized, detail: fields.text("message"),
          symbol: fields.flag("terminal")
            ? "checkmark.circle" : "arrow.trianglehead.2.clockwise.rotate.90")
        ForEach(Array((fields["events"]?.array ?? []).enumerated()), id: \.offset) { _, event in
          Text(event.object.text("message", fallback: event.pretty)).font(.caption).foregroundStyle(
            Theme.secondary)
        }
      }
      if let number = draft.submittedJobID {
        Notice(
          title: "Job #\(number) submitted", detail: "\(draft.host) has received this job.",
          symbol: "checkmark.circle")
        Button("Open job", systemImage: "arrow.up.right") {
          store.showSettings = false
          store.handle(
            SystemJob(
              host: draft.host, number: number, name: draft.name, state: "", runtime: "",
              pinned: false
            ).url(connection: store.connection?.id))
        }.buttonStyle(PrimaryButtonStyle())
      } else if submitting {
        ProgressView("Submitting to \(draft.host)…").frame(maxWidth: .infinity).padding()
      } else if draft.submissionUnknown {
        Notice(
          title: "Result not yet known",
          detail:
            "A connection failure does not mean submission failed. Check recent jobs on \(draft.host) before preparing another launch.",
          warning: true)
      } else if draft.launchID == nil {
        Toggle("I have reviewed the script and resource request", isOn: $confirmed).font(
          .subheadline)
        Button {
          Task { await submit() }
        } label: {
          HStack {
            if submitting { ProgressView().tint(Theme.onAccent) }
            Text(store.demo ? "Simulate launch" : "Submit to \(draft.host)")
            Image(systemName: "arrow.up.right")
          }
        }
        .buttonStyle(PrimaryButtonStyle()).disabled(
          !confirmed || submitting || draft.validation != nil
        )
        .accessibilityIdentifier("submitLaunch")
        Text(
          store.demo
            ? "This demo creates a sample job only."
            : "Submission can consume cluster resources. ssync will keep the operation ID so you can return to its status."
        )
        .font(.caption).foregroundStyle(Theme.secondary)
      }
    }.navigationTitle("Review launch").navigationBarTitleDisplayMode(.inline)
      .task(id: draft.launchID) { await watchStatus() }
  }
  private func defaultText(_ text: String) -> String {
    text.isEmpty ? "Script / server default" : text
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
        Button("Open path") { Task { await load(path) } }
        Button("Use this directory") {
          selected = path
          dismiss()
        }.disabled(path.isEmpty)
      } header: {
        Text("On the ssync API server")
      }
      if let error { Text(error).foregroundStyle(Theme.red) }
      if loading { ProgressView() }
      if !path.isEmpty {
        Button("Parent directory", systemImage: "arrow.up") {
          Task { await load((path as NSString).deletingLastPathComponent) }
        }
      }
      ForEach(Array(entries.enumerated()), id: \.offset) { _, entry in
        Button {
          Task { await load(entry.object.text("path")) }
        } label: {
          Label(entry.object.text("name"), systemImage: "folder")
        }
      }
    }.navigationTitle("Choose source").toolbar { Button("Cancel") { dismiss() } }
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
      let value: JSONValue = try await store.client!.send(
        "api/local/list", query: ["path": target, "dirs_only": "true", "limit": "300"])
      path = value.object.text("path")
      entries = value.object["entries"]?.array ?? []
    } catch { self.error = error.localizedDescription }
  }
}
