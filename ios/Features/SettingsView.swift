import SwiftUI

struct SettingsView: View {
  @Environment(AppStore.self) private var store
  @Environment(\.dismiss) private var dismiss
  @State private var adding = false
  @State private var error: String?
  @State private var forget: Connection?
  @State private var notifications = NotificationService.shared
  @State private var preferences: [String: JSONValue] = [:]
  @State private var providers: JSONValue?
  @State private var saving = false
  @State private var allowedStates = ""
  @State private var mutedHosts = ""
  @State private var mutedNames = ""
  @State private var allowedUsers = ""
  @State private var toast: String?
  var body: some View {
    @Bindable var store = store
    Form {
      Section("Connection") {
        if let connection = store.connection {
          LabeledContent("Workspace", value: connection.demo ? "Demo workspace" : connection.name)
          if !connection.demo { Text(connection.baseURL).font(.caption).textSelection(.enabled) }
        }
        Button("Add or switch connection", systemImage: "server.rack") { adding = true }
        Button("Disconnect", role: .destructive) {
          store.disconnect()
          dismiss()
        }
        ForEach(store.connections) { connection in
          Button("Forget \(connection.name)", role: .destructive) { forget = connection }
        }
      }
      Section {
        LabeledContent("Permission", value: notifications.status)
        LabeledContent(
          "Device", value: store.demo ? "Demo — no registration" : notifications.registration)
        Button("Enable notifications") { Task { await notifications.enable(api: store.client) } }
          .disabled(store.demo)
        Button("Open iOS notification settings") {
          if let url = URL(string: UIApplication.openNotificationSettingsURLString) {
            UIApplication.shared.open(url)
          }
        }
        if let error = notifications.error { Text(error).foregroundStyle(Theme.red).font(.caption) }
        if let providers {
          LabeledContent(
            "Server push delivery",
            value: providers.object["providers"]?.object["apns"]?.bool == true
              ? "Configured" : "Not configured")
        }
        Button("Send a test notification") {
          Task {
            do {
              guard let token = UserDefaults.standard.string(forKey: "apnsToken"),
                let api = store.client
              else {
                throw APIError(
                  status: 0, message: "Enable notifications and register this device first.")
              }
              try await api.perform(
                "api/notifications/test",
                body: .object([
                  "title": .string("ssync is connected"),
                  "body": .string("Your job updates will arrive here."), "token": .string(token),
                  "token_type": .string("apns"),
                ]))
              toast = "Test notification requested."
            } catch { self.error = error.localizedDescription }
          }
        }.disabled(store.demo)
      } header: {
        Text("Notifications")
      }
      if !store.demo && !preferences.isEmpty {
        Section {
          Toggle(
            "Job notifications",
            isOn: Binding(
              get: { preferences["enabled"]?.bool ?? true },
              set: { preferences["enabled"] = .bool($0) }))
          TextField("States: R, PD, CD, F, CA, TO", text: $allowedStates)
          TextField("Muted hosts, comma separated", text: $mutedHosts)
          TextField("Muted name patterns, comma separated", text: $mutedNames)
          TextField("Allowed users, comma separated", text: $allowedUsers)
          Button(saving ? "Saving…" : "Save server preferences") {
            Task { await savePreferences() }
          }.disabled(saving)
        } header: {
          Text("Server delivery rules")
        } footer: {
          Text(
            "These preferences are shared by clients using this API key. Blank states use the server’s terminal-state default. A blank user list allows all users."
          )
        }
        .textInputAutocapitalization(.never).autocorrectionDisabled()
      }
      Section("Widgets & Lock Screen") {
        Toggle("Hide job data in widgets", isOn: $store.widgetPrivacy)
        Button("End Live Activities") { Task { await LiveActivityService.shared.endAll() } }
        Text(
          "Widgets and Live Activities update while ssync is open. Check their last-update time."
        )
        .font(.caption).foregroundStyle(.secondary)
      }
      Section("About") {
        HStack {
          RelayMark()
          Text("ssync for iOS").font(.headline)
          Spacer()
          Text("0.1").foregroundStyle(.secondary)
        }
      }
      if let error { Section { Text(error).foregroundStyle(Theme.red) } }
      if let toast { Section { Text(toast).foregroundStyle(Theme.green) } }
    }.navigationTitle("Settings").toolbar {
      ToolbarItem(placement: .confirmationAction) { Button("Done") { dismiss() } }
    }
    .sheet(isPresented: $adding) { ConnectionView(adding: true) }
    .confirmationDialog(
      "Forget this connection and its local drafts?",
      isPresented: Binding(get: { forget != nil }, set: { if !$0 { forget = nil } }),
      titleVisibility: .visible
    ) {
      if let forget {
        Button("Forget connection", role: .destructive) {
          Task {
            do {
              if let token = UserDefaults.standard.string(forKey: "apnsToken") {
                let api = APIClient(connection: forget, apiKey: CredentialStore.read(forget.id))
                try await api.perform("api/notifications/devices/\(token)", method: "DELETE")
              }
              try store.forget(forget)
              self.forget = nil
            } catch {
              self.error = "Couldn’t remove this device registration: \(error.localizedDescription)"
            }
          }
        }
      }
    }
    .task { await load() }
  }
  private func load() async {
    await notifications.refresh()
    guard let api = store.client else { return }
    notifications.api = api
    if notifications.status == "Allowed",
      let token = UserDefaults.standard.string(forKey: "apnsToken")
    {
      await notifications.register(token: token)
    }
    do {
      let response: JSONValue = try await api.send("api/notifications/preferences")
      preferences = response.object
      func list(_ name: String) -> String {
        preferences[name]?.array.compactMap(\.string).joined(separator: ",") ?? ""
      }
      allowedStates = list("allowed_states")
      mutedHosts = list("muted_hosts")
      mutedNames = list("muted_job_name_patterns")
      allowedUsers = list("allowed_users")
      providers = try await api.send("api/notifications/status")
    } catch { self.error = error.localizedDescription }
  }
  private func savePreferences() async {
    saving = true
    defer { saving = false }
    for (key, text) in [
      ("allowed_states", allowedStates), ("muted_hosts", mutedHosts),
      ("muted_job_name_patterns", mutedNames), ("allowed_users", allowedUsers),
    ] {
      preferences[key] = .array(
        text.split(separator: ",").map { .string($0.trimmingCharacters(in: .whitespaces)) })
    }
    if allowedStates.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
      preferences["allowed_states"] = .null
    }
    do {
      try await store.client?.perform(
        "api/notifications/preferences", method: "PATCH", body: .object(preferences))
      toast = "Server preferences saved."
    } catch { self.error = error.localizedDescription }
  }
}
