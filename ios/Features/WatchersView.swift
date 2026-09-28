import SwiftUI

/// What happened recently: launches in flight, watcher events, and the rules that produce them.
struct ActivityView: View {
  @Environment(AppStore.self) private var store
  @State private var events: [WatcherEvent] = []
  @State private var eventsError: String?
  var launches: [(SavedDraft, LaunchDraft)] {
    store.drafts.compactMap { saved in
      guard let draft = try? JSONDecoder().decode(LaunchDraft.self, from: saved.payload),
        draft.launchID != nil || draft.submittedJobID != nil || draft.submissionUnknown
      else { return nil }
      return (saved, draft)
    }.sorted { $0.0.updatedAt > $1.0.updatedAt }
  }
  var body: some View {
    List {
      if store.error != nil && !store.demo { ConnectionBanner() }
      let launches = launches.prefix(5)
      if !launches.isEmpty {
        CollapsibleSection("Launches", detail: "\(launches.count)", key: "activity.launches") {
          ForEach(launches, id: \.0.id) { saved, draft in launchRow(saved, draft) }
        }
      }
      CollapsibleSection("Recent events", key: "activity.events") {
        CappedRows(items: Array(events.prefix(50)), limit: 5) { event in
          NavigationLink(value: Route.watcher(event.watcher_id)) { EventRow(event: event) }
        }
        if events.isEmpty {
          Text(eventsError ?? "No watcher events yet").font(.subheadline)
            .foregroundStyle(.secondary)
        }
      }
      CollapsibleSection("Watchers", detail: "\(store.watchers.count)", key: "activity.watchers") {
        CappedRows(items: store.watchers) { watcher in
          NavigationLink(value: Route.watcher(watcher.id)) { WatcherRow(watcher: watcher) }
            .swipeActions {
              let paused = watcher.state == "paused"
              Button(paused ? "Resume" : "Pause", systemImage: paused ? "play" : "pause") {
                Task {
                  try? await store.watcherAction(watcher, action: paused ? "resume" : "pause")
                }
              }.tint(paused ? Theme.green : Theme.amber)
            }
        }
        if store.watchers.isEmpty {
          Text(store.watcherError ?? "Add a watcher from a job to automate what happens next.")
            .font(.subheadline).foregroundStyle(.secondary)
        }
      }
    }
    .navigationTitle("Activity")
    .rootToolbar()
    .task(id: store.refreshRevision) { await loadEvents() }
    .refreshable {
      await store.refresh()
      await loadEvents()
    }
    .onAppear { store.reloadDrafts() }
  }
  private func launchRow(_ saved: SavedDraft, _ draft: LaunchDraft) -> some View {
    Button {
      if let number = draft.submittedJobID {
        store.tab = .jobs
        store.jobPath.append(.job(JobID(host: draft.host, number: number)))
      } else {
        store.openDraft(draft)
      }
    } label: {
      HStack(spacing: 12) {
        Image(
          systemName: draft.submittedJobID != nil
            ? "checkmark.circle.fill"
            : draft.submissionUnknown ? "questionmark.circle" : "arrow.up.circle"
        )
        .foregroundStyle(
          draft.submittedJobID != nil
            ? Theme.green : draft.submissionUnknown ? Theme.amber : Theme.accent
        ).frame(width: 22)
        VStack(alignment: .leading, spacing: 2) {
          Text(draft.name.isEmpty ? "Untitled launch" : draft.name).font(.body.weight(.medium))
          Text(
            draft.submittedJobID.map { "\(draft.host) · #\($0)" }
              ?? (draft.submissionUnknown ? "Result unknown · check \(draft.host)" : "Submitting…")
          ).font(.caption).foregroundStyle(.secondary)
        }
        Spacer()
        Text(Format.age(saved.updatedAt)).font(.caption).foregroundStyle(.secondary)
      }
    }.tint(.primary)
  }
  private func loadEvents() async {
    if store.demo {
      events = DemoData.events(1)
      return
    }
    guard let api = store.client else { return }
    do {
      events = try await api.recentWatcherEvents().events
      eventsError = nil
    } catch { eventsError = "Events unavailable: \(error.localizedDescription)" }
  }
}

struct WatcherRow: View {
  var watcher: Watcher
  var body: some View {
    HStack(spacing: 12) {
      Image(systemName: watcher.state == "paused" ? "pause.circle" : "eye")
        .foregroundStyle(watcher.state == "paused" ? Color.secondary : Theme.accent)
        .frame(width: 22)
      VStack(alignment: .leading, spacing: 2) {
        Text(watcher.name).font(.body.weight(.medium)).lineLimit(1)
        Text("\(watcher.trigger) → \(watcher.actionSummary)")
          .font(.caption).foregroundStyle(.secondary).lineLimit(1)
      }
      Spacer(minLength: 8)
      if watcher.state == "paused" {
        Text("Paused").font(.caption).foregroundStyle(.secondary)
      }
    }
    .accessibilityElement(children: .combine)
  }
}

struct EventRow: View {
  var event: WatcherEvent
  @Environment(AppStore.self) private var store
  var body: some View {
    HStack(alignment: .top, spacing: 12) {
      Image(systemName: event.success ? "checkmark.circle.fill" : "exclamationmark.circle.fill")
        .foregroundStyle(event.success ? Theme.green : Theme.red).frame(width: 22)
      VStack(alignment: .leading, spacing: 2) {
        Text(title).font(.subheadline.weight(.medium)).lineLimit(1)
        Text(event.action_result ?? event.matched_text ?? "No details")
          .font(.caption).foregroundStyle(.secondary).lineLimit(2)
      }
      Spacer(minLength: 8)
      Text(Format.age(Format.date(event.timestamp))).font(.caption).foregroundStyle(.secondary)
    }
    .accessibilityElement(children: .combine)
  }
  private var title: String {
    let action = event.action_type.replacingOccurrences(of: "_", with: " ").capitalized
    if let watcher = store.watchers.first(where: { $0.id == event.watcher_id }) {
      return "\(action) · \(watcher.name)"
    }
    return "\(action) · #\(event.job_id)"
  }
}

struct WatcherDetailView: View {
  var id: Int
  @Environment(AppStore.self) private var store
  @Environment(\.dismiss) private var dismiss
  @State private var events: [WatcherEvent] = []
  @State private var error: String?
  @State private var confirm: String?
  @State private var busy = false
  @State private var editing = false
  var watcher: Watcher? { store.watchers.first { $0.id == id } }
  var body: some View {
    Group {
      if let watcher {
        content(watcher)
      } else {
        ContentUnavailableView(
          "Watcher unavailable", systemImage: "eye.slash",
          description: Text("It may have been removed from the server."))
      }
    }
    .navigationTitle(watcher?.name ?? "Watcher")
    .task { await loadEvents() }
    .refreshable {
      await store.refresh()
      await loadEvents()
    }
    .sheet(isPresented: $editing) {
      if let watcher {
        NavigationStack { WatcherEditor(jobID: watcher.jobID, existing: watcher) }
      }
    }
    .confirmationDialog(
      confirm == "delete" ? "Delete this watcher?" : "Run this watcher’s actions now?",
      isPresented: Binding(get: { confirm != nil }, set: { if !$0 { confirm = nil } }),
      titleVisibility: .visible
    ) {
      if let confirm, let watcher {
        Button(confirm == "delete" ? "Delete watcher" : "Run actions", role: .destructive) {
          run(confirm, watcher: watcher)
        }
      }
    } message: {
      if confirm == "trigger" { Text("Actions may cancel or resubmit the job.") }
    }
  }
  private func content(_ watcher: Watcher) -> some View {
    let paused = watcher.state == "paused"
    return List {
      Section {
        HStack {
          Label(
            paused ? "Paused" : "Active", systemImage: paused ? "pause.circle.fill" : "eye.fill"
          )
          .font(.subheadline.weight(.semibold))
          .foregroundStyle(paused ? Color.secondary : Theme.green)
          Spacer()
          Text("Triggered \(watcher.fields.integer("trigger_count"))×").font(.subheadline)
            .foregroundStyle(.secondary)
        }
        NavigationLink(value: Route.job(watcher.jobID)) {
          if let job = store.job(watcher.jobID) {
            JobRow(job: job)
          } else {
            Label(
              "\(watcher.host) · #\(watcher.jobID.number)", systemImage: "list.bullet.rectangle")
          }
        }
      }
      if let error {
        Label(error, systemImage: "exclamationmark.triangle").foregroundStyle(Theme.amber)
          .font(.subheadline)
      }
      Section("Rule") {
        ruleStep(
          "When", watcher.fields.flag("trigger_on_job_end") ? "The job ends" : "Output matches",
          detail: watcher.trigger)
        let captures = watcher.fields["captures"]?.array.compactMap(\.string) ?? []
        if !captures.isEmpty {
          ruleStep("Capture", captures.joined(separator: ", "), detail: nil)
        }
        ruleStep(
          "Then", watcher.actionSummary.capitalized,
          detail: watcher.actions.compactMap {
            let params = $0.object["params"] ?? $0.object["config"]
            return params?.object.isEmpty == false ? params?.pretty : nil
          }.joined(separator: "\n"))
      }
      CollapsibleSection("Recent events", detail: "\(events.count)", key: "watcher.events") {
        CappedRows(items: events, limit: 5) { EventRow(event: $0) }
        if events.isEmpty { Text("No events yet").foregroundStyle(.secondary) }
      }
    }
    .toolbar {
      ToolbarItem(placement: .topBarTrailing) {
        Button("Edit") { editing = true }
      }
      ToolbarItem(placement: .topBarTrailing) {
        Menu {
          Button(paused ? "Resume" : "Pause", systemImage: paused ? "play" : "pause") {
            run(paused ? "resume" : "pause", watcher: watcher)
          }
          Button("Run actions now…", systemImage: "bolt") { confirm = "trigger" }
          Divider()
          Button("Delete watcher…", systemImage: "trash", role: .destructive) {
            confirm = "delete"
          }
        } label: {
          Label("Watcher actions", systemImage: "ellipsis")
        }.disabled(busy)
      }
    }
  }
  private func ruleStep(_ label: String, _ title: String, detail: String?) -> some View {
    VStack(alignment: .leading, spacing: 4) {
      Text(label.uppercased()).font(.caption2.weight(.bold)).foregroundStyle(.secondary)
      Text(title).font(.body.weight(.medium))
      if let detail, !detail.isEmpty {
        Text(detail).font(.system(.caption, design: .monospaced)).foregroundStyle(.secondary)
          .textSelection(.enabled)
      }
    }.padding(.vertical, 2)
  }
  private func loadEvents() async {
    guard let watcher else { return }
    if store.demo {
      events = DemoData.events(id)
      return
    }
    do {
      events =
        try await store.client?.watcherEvents(id).events.filter { $0.hostname == watcher.host }
        ?? []
    } catch { self.error = error.localizedDescription }
  }
  private func run(_ action: String, watcher: Watcher) {
    busy = true
    Task {
      defer {
        busy = false
        confirm = nil
      }
      do {
        try await store.watcherAction(watcher, action: action)
        if action == "delete" { dismiss() } else { await loadEvents() }
      } catch { self.error = error.localizedDescription }
    }
  }
}

struct WatcherEditor: View {
  var jobID: JobID
  var existing: Watcher? = nil
  @Environment(AppStore.self) private var store
  @Environment(\.dismiss) private var dismiss
  @State private var name = ""
  @State private var pattern = ""
  @State private var captures = ""
  @State private var condition = ""
  @State private var interval = 30
  @State private var terminal = false
  @State private var terminalStates: Set<String> = ["timeout", "failed"]
  @State private var actionType = "log_event"
  @State private var parameters = "{}"
  @State private var rawActions: String?
  @State private var error: String?
  @State private var saving = false
  private let knownStates = ["completed", "failed", "timeout", "cancelled", "out_of_memory"]
  private let actions = [
    "log_event", "cancel_job", "resubmit", "store_metric", "notify_email", "run_command",
  ]
  var body: some View {
    Form {
      Section {
        TextField("Name", text: $name)
        LabeledContent("Job", value: "\(jobID.host) · #\(jobID.number)")
      }
      Section {
        Picker("Trigger", selection: $terminal) {
          Text("Output matches").tag(false)
          Text("Job ends").tag(true)
        }.pickerStyle(.segmented)
        if terminal {
          ForEach(knownStates, id: \.self) { state in
            Toggle(
              state.replacingOccurrences(of: "_", with: " ").capitalized,
              isOn: Binding(
                get: { terminalStates.contains(state) },
                set: {
                  if $0 { terminalStates.insert(state) } else { terminalStates.remove(state) }
                }
              ))
          }
        }
        TextField(
          terminal ? "Pattern to capture (optional)" : "Pattern (regular expression)",
          text: $pattern, axis: .vertical
        )
        .font(.system(.body, design: .monospaced))
        .autocorrectionDisabled().textInputAutocapitalization(.never)
        Stepper("Check every \(interval) s", value: $interval, in: 5...3600, step: 5)
      } header: {
        Text("When")
      }
      Section {
        TextField("Capture names, comma separated", text: $captures)
        TextField("Condition (optional)", text: $condition, axis: .vertical)
      } header: {
        Text("Capture")
      } footer: {
        Text("Name the regex groups to reuse them in actions.")
      }.textInputAutocapitalization(.never).autocorrectionDisabled()
      Section {
        if let rawActions {
          Text("This watcher has several actions. Edit them as JSON.").font(.caption)
            .foregroundStyle(.secondary)
          TextEditor(text: Binding(get: { rawActions }, set: { self.rawActions = $0 }))
            .font(.system(.caption, design: .monospaced)).frame(minHeight: 160)
        } else {
          Picker(
            "Action",
            selection: Binding(
              get: { actionType },
              set: { value in
                actionType = value
                parameters =
                  value == "resubmit"
                  ? "{\"remaining_resubmits\":1,\"cancel_previous\":true}" : "{}"
              })
          ) {
            ForEach(actions, id: \.self) {
              Text($0.replacingOccurrences(of: "_", with: " ").capitalized).tag($0)
            }
          }
          WatcherActionFields(type: actionType, parameters: $parameters)
          NavigationLink("Parameters (JSON)") {
            TextEditor(text: $parameters).font(.system(.caption, design: .monospaced))
              .textInputAutocapitalization(.never).autocorrectionDisabled()
              .padding().navigationTitle("Parameters")
          }
        }
      } header: {
        Text("Then")
      } footer: {
        Text("Actions run on the ssync server. Email and commands need server configuration.")
      }
      if let error { Section { Text(error).foregroundStyle(Theme.red) } }
    }
    .navigationTitle(existing == nil ? "New watcher" : "Edit watcher")
    .navigationBarTitleDisplayMode(.inline)
    .toolbar {
      ToolbarItem(placement: .cancellationAction) { Button("Cancel") { dismiss() } }
      ToolbarItem(placement: .confirmationAction) {
        Button("Save") { save() }
          .disabled(saving || name.isEmpty || (!terminal && pattern.isEmpty))
      }
    }
    .onAppear(perform: loadExisting)
  }
  private func loadExisting() {
    guard let existing else { return }
    name = existing.name
    pattern = existing.fields.text("pattern")
    interval = Int(existing.fields.text("interval_seconds", fallback: "30")) ?? 30
    captures = existing.fields["captures"]?.array.compactMap(\.string).joined(separator: ", ") ?? ""
    condition = existing.fields.text("condition")
    terminal = existing.fields.flag("trigger_on_job_end")
    if let states = existing.fields["trigger_job_states"]?.array.compactMap(\.string) {
      terminalStates = Set(states)
    }
    if existing.actions.count == 1, let action = existing.actions.first {
      actionType = action.object.text("type")
      parameters = (action.object["params"] ?? action.object["config"])?.pretty ?? "{}"
    } else {
      rawActions = JSONValue.array(existing.actions).pretty
    }
  }
  private func save() {
    saving = true
    error = nil
    Task {
      defer { saving = false }
      do {
        if !pattern.isEmpty { _ = try NSRegularExpression(pattern: pattern) }
        let actions: JSONValue
        if let rawActions {
          actions = try JSONDecoder().decode(JSONValue.self, from: Data(rawActions.utf8))
          guard case .array = actions else {
            throw APIError(status: 0, message: "Actions must be a JSON array.")
          }
        } else {
          let params = try JSONDecoder().decode(JSONValue.self, from: Data(parameters.utf8))
          guard case .object = params else {
            throw APIError(status: 0, message: "Action parameters must be a JSON object.")
          }
          var action = existing?.actions.first?.object ?? [:]
          action["type"] = .string(actionType)
          action["params"] = params
          action.removeValue(forKey: "config")
          actions = .array([.object(action)])
        }
        var fields = existing?.fields ?? [:]
        fields.merge([
          "name": .string(name), "hostname": .string(jobID.host), "job_id": .string(jobID.number),
          "pattern": .string(pattern),
          "captures": .array(
            captures.split(separator: ",").map {
              .string($0.trimmingCharacters(in: .whitespaces))
            }),
          "condition": condition.isEmpty ? .null : .string(condition),
          "interval_seconds": .number(Double(interval)), "trigger_on_job_end": .bool(terminal),
          "trigger_job_states": .array(terminalStates.sorted().map { .string($0) }),
          "actions": actions,
        ]) { _, new in new }
        if store.demo {
          fields["id"] = .number(
            Double(existing?.id ?? ((store.watchers.map(\.id).max() ?? 0) + 1)))
          fields["state"] = .string(existing?.state ?? "active")
          let watcher = Watcher(fields)
          store.watchers.removeAll { $0.id == watcher.id }
          store.watchers.append(watcher)
        } else {
          try await store.client?.perform(
            existing.map { "api/watchers/\($0.id)" } ?? "api/watchers",
            method: existing == nil ? "POST" : "PUT", body: .object(fields))
          await store.refresh()
        }
        dismiss()
      } catch { self.error = error.localizedDescription }
    }
  }
}
