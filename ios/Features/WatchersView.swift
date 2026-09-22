import SwiftUI

struct WatchersView: View {
  @Environment(AppStore.self) private var store
  @State private var filter = "All"
  @State private var search = ""
  var visible: [Watcher] {
    store.watchers.filter {
      (filter == "All" || $0.state.lowercased() == filter.lowercased())
        && (search.isEmpty
          || "\($0.name) \($0.host) \($0.jobID.number)".localizedCaseInsensitiveContains(search))
    }
  }
  var body: some View {
    Screen {
      ConnectionStatus()
      if let error = store.watcherError {
        Notice(title: "Watchers unavailable", detail: error, warning: true)
      }
      Picker("Watcher state", selection: $filter) {
        ForEach(["All", "Active", "Paused"], id: \.self) { Text($0) }
      }.pickerStyle(.segmented)
      ForEach(visible) { watcher in
        NavigationLink(value: Route.watcher(watcher.id)) { WatcherCard(watcher: watcher) }
          .buttonStyle(.plain)
      }
      if visible.isEmpty {
        EmptyState(
          title: "No watchers",
          detail: "Open a job to create a rule for its output or terminal state.", symbol: "eye")
      }
    }.navigationTitle("Watchers").navigationBarTitleDisplayMode(.inline).rootToolbar()
      .searchable(text: $search, prompt: "Name, host or job ID").refreshable {
        await store.refresh()
      }
  }
}
struct WatcherCard: View {
  var watcher: Watcher
  var body: some View {
    Paper {
      VStack(alignment: .leading, spacing: 14) {
        HStack {
          Image("watcher-rule").foregroundStyle(Theme.accent)
          Text(watcher.name).font(.headline)
          Spacer()
          Circle().fill(watcher.state == "active" ? Theme.green : Theme.secondary).frame(
            width: 7, height: 7)
        }
        Text("\(watcher.host) / #\(watcher.jobID.number) · \(watcher.state.capitalized)").font(
          .caption
        ).foregroundStyle(Theme.secondary)
        Divider()
        HStack(alignment: .top) {
          Text("WHEN").font(.caption2.weight(.bold)).foregroundStyle(Theme.secondary).frame(
            width: 44, alignment: .leading)
          Text(watcher.trigger).font(.system(.caption, design: .monospaced)).lineLimit(2)
        }
        HStack(alignment: .top) {
          Text("THEN").font(.caption2.weight(.bold)).foregroundStyle(Theme.secondary).frame(
            width: 44, alignment: .leading)
          Text(watcher.actionSummary.capitalized).font(.caption.weight(.medium))
        }
      }
    }
  }
}
struct WatcherDetailView: View {
  var id: Int
  @Environment(AppStore.self) private var store
  @Environment(\.dismiss) private var dismiss
  @State private var events: [WatcherEvent] = []
  @State private var error: String?
  @State private var action: String?
  @State private var busy = false
  var watcher: Watcher? { store.watchers.first { $0.id == id } }
  var body: some View {
    Screen {
      if let watcher {
        Text(watcher.name).font(.system(.largeTitle, design: .rounded).weight(.bold))
        HStack {
          Text(watcher.state.capitalized).foregroundStyle(Theme.green)
          Spacer()
          Text("\(watcher.fields.integer("trigger_count")) triggers")
        }.font(.subheadline)
        NavigationLink(value: Route.job(watcher.jobID)) {
          Label("\(watcher.host) / #\(watcher.jobID.number)", systemImage: "square.stack.3d.up")
        }
        if let error {
          Notice(title: "Couldn’t complete the request", detail: error, warning: true)
        }
        VStack(alignment: .leading, spacing: 0) {
          ruleStep(
            "WHEN",
            title: watcher.fields.flag("trigger_on_job_end") ? "The job ends" : "Output matches",
            detail: watcher.trigger, last: false)
          ruleStep(
            "USING", title: "Captured values",
            detail: watcher.fields["captures"]?.pretty ?? "No captures", last: false)
          ruleStep(
            "THEN", title: watcher.actionSummary.capitalized,
            detail: watcher.actions.map(\.pretty).joined(separator: "\n"), last: true)
        }.padding(20).background(Theme.surface, in: RoundedRectangle(cornerRadius: 20))
        HStack {
          Button(
            watcher.state == "paused" ? "Resume watcher" : "Pause watcher",
            systemImage: watcher.state == "paused" ? "play" : "pause"
          ) {
            run(watcher.state == "paused" ? "resume" : "pause", watcher: watcher)
          }.buttonStyle(.bordered).disabled(busy)
          Spacer()
          NavigationLink("Edit") { WatcherEditor(jobID: watcher.jobID, existing: watcher) }
        }
        Button("Trigger actions now", systemImage: "bolt") { action = "trigger" }.disabled(busy)
        Text("Manual triggering executes the configured actions. It can cancel or resubmit a job.")
          .font(.caption).foregroundStyle(Theme.secondary)
        SectionHeading(title: "Recent events", detail: "\(events.count)")
        if events.isEmpty {
          Text("No events recorded yet.").font(.subheadline).foregroundStyle(Theme.secondary)
        }
        ForEach(events) { event in
          Paper {
            VStack(alignment: .leading, spacing: 8) {
              Label(
                event.action_type.replacingOccurrences(of: "_", with: " ").capitalized,
                systemImage: event.success ? "checkmark.circle" : "exclamationmark.circle"
              )
              .font(.subheadline.weight(.semibold)).foregroundStyle(
                event.success ? Theme.green : Theme.red)
              Text(event.action_result ?? event.matched_text ?? "No additional details.").font(
                .caption
              ).textSelection(.enabled)
              Text(event.timestamp).font(.caption2).foregroundStyle(Theme.secondary)
              if let captures = event.captured_vars, !captures.isEmpty {
                Text(JSONValue.object(captures).pretty).font(.system(.caption, design: .monospaced))
                  .textSelection(.enabled)
              }
            }
          }
        }
        Button("Delete watcher", role: .destructive) { action = "delete" }.padding(.top)
      } else {
        EmptyState(
          title: "Watcher unavailable", detail: "It may have been removed from the server.",
          symbol: "eye.slash")
      }
    }.navigationTitle("Watcher").navigationBarTitleDisplayMode(.inline)
      .task { await loadEvents() }.refreshable {
        await store.refresh()
        await loadEvents()
      }
      .confirmationDialog(
        action == "delete" ? "Delete this watcher?" : "Execute this watcher’s actions?",
        isPresented: Binding(get: { action != nil }, set: { if !$0 { action = nil } }),
        titleVisibility: .visible
      ) {
        if let action, let watcher {
          Button(action == "delete" ? "Delete watcher" : "Execute actions", role: .destructive) {
            run(action, watcher: watcher)
          }
        }
      }
  }
  private func ruleStep(_ label: String, title: String, detail: String, last: Bool) -> some View {
    HStack(alignment: .top, spacing: 15) {
      VStack(spacing: 0) {
        Circle().fill(Theme.accent).frame(width: 10, height: 10)
        if !last {
          Rectangle().fill(Theme.accent.opacity(0.2)).frame(width: 2).frame(minHeight: 80)
        }
      }
      VStack(alignment: .leading, spacing: 8) {
        Eyebrow(title: label)
        Text(title).font(.headline)
        Text(detail).font(.system(.caption, design: .monospaced)).foregroundStyle(Theme.secondary)
          .textSelection(.enabled)
      }.padding(.bottom, last ? 0 : 28)
    }
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
        self.action = nil
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
  @State private var interval = "30"
  @State private var terminal = false
  @State private var terminalStates = "timeout,failed"
  @State private var actionType = "log_event"
  @State private var parameters = "{}"
  @State private var rawActions: String?
  @State private var error: String?
  @State private var saving = false
  @State private var confirm = false
  private let actions = [
    "log_event", "cancel_job", "resubmit", "store_metric", "notify_email", "run_command",
  ]
  var body: some View {
    Form {
      Section("Job") { Text("\(jobID.host) / #\(jobID.number)") }
      Section("When") {
        TextField("Watcher name", text: $name)
        Toggle("Trigger when the job ends", isOn: $terminal)
        if terminal {
          TextField("Terminal states, comma separated", text: $terminalStates)
            .textInputAutocapitalization(.never)
        }
        TextField("Output pattern (regular expression)", text: $pattern, axis: .vertical).font(
          .system(.body, design: .monospaced)
        ).autocorrectionDisabled().textInputAutocapitalization(.never)
        TextField("Check interval in seconds", text: $interval).keyboardType(.numberPad)
      }
      Section("Using") {
        TextField("Capture names, comma separated", text: $captures).textInputAutocapitalization(
          .never)
        TextField("Condition (optional)", text: $condition, axis: .vertical)
          .textInputAutocapitalization(.never).autocorrectionDisabled()
      }
      Section {
        if let rawActions {
          Text("This watcher has multiple actions. Edit the complete action list.").font(.caption)
            .foregroundStyle(.secondary)
          TextEditor(text: Binding(get: { rawActions }, set: { self.rawActions = $0 })).font(
            .system(.caption, design: .monospaced)
          ).frame(minHeight: 160)
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
          DisclosureGroup("Advanced action parameters") {
            TextEditor(text: $parameters).font(.system(.caption, design: .monospaced)).frame(
              minHeight: 140)
          }
        }
      } header: {
        Text("Then")
      } footer: {
        Text(
          "Actions execute on the server. Email and commands require server configuration. Resubmission must include the parameters expected by your ssync server."
        )
      }
      if let error { Section { Text(error).foregroundStyle(Theme.red) } }
      Section {
        Button(saving ? "Saving…" : "Review & save") { confirm = true }.disabled(
          saving || name.isEmpty || (!terminal && pattern.isEmpty))
      }
    }.navigationTitle(existing == nil ? "New watcher" : "Edit watcher")
      .confirmationDialog("Save this automation?", isPresented: $confirm, titleVisibility: .visible)
    {
      Button("Save watcher") { save() }
    } message: {
      Text(
        "When its condition matches, this watcher will execute its actions for \(jobID.host) / #\(jobID.number)."
      )
    }
      .onAppear {
        guard let existing else { return }
        name = existing.name
        pattern = existing.fields.text("pattern")
        interval = existing.fields.text("interval_seconds", fallback: "30")
        captures =
          existing.fields["captures"]?.array.compactMap(\.string).joined(separator: ",") ?? ""
        condition = existing.fields.text("condition")
        terminal = existing.fields.flag("trigger_on_job_end")
        terminalStates =
          existing.fields["trigger_job_states"]?.array.compactMap(\.string).joined(separator: ",")
          ?? "timeout,failed"
        if existing.actions.count == 1, let action = existing.actions.first {
          actionType = action.object.text("type")
          parameters = (action.object["params"] ?? action.object["config"])?.pretty ?? "{}"
        } else {
          rawActions = JSONValue.array(existing.actions).pretty
        }
      }
  }
  private func save() {
    saving = true
    error = nil
    Task {
      defer { saving = false }
      do {
        guard let seconds = Int(interval), seconds >= 1 else {
          throw APIError(status: 0, message: "Enter a positive check interval.")
        }
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
            captures.split(separator: ",").map { .string($0.trimmingCharacters(in: .whitespaces)) }),
          "condition": condition.isEmpty ? .null : .string(condition),
          "interval_seconds": .number(Double(seconds)), "trigger_on_job_end": .bool(terminal),
          "trigger_job_states": .array(
            terminalStates.split(separator: ",").map {
              .string($0.trimmingCharacters(in: .whitespaces))
            }), "actions": actions,
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
