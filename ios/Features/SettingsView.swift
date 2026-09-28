import SwiftUI

struct SettingsView: View {
  @Environment(AppStore.self) private var store
  @Environment(\.dismiss) private var dismiss
  @State private var error: String?
  @State private var forget: Connection?
  @State private var notifications = NotificationService.shared
  @State private var preferences: [String: JSONValue] = [:]
  @State private var providers: JSONValue?
  @State private var saving = false
  @State private var saved = false
  @State private var testSent = false
  @State private var allowedStates: Set<String> = []
  @State private var mutedHosts: Set<String> = []
  @State private var mutedNames = ""
  @State private var allowedUsers = ""
  private let states = [
    ("R", "Started running"), ("PD", "Queued"), ("CD", "Completed"), ("F", "Failed"),
    ("TO", "Timed out"), ("CA", "Cancelled"),
  ]
  private var version: String {
    Bundle.main.object(forInfoDictionaryKey: "CFBundleShortVersionString") as? String ?? "—"
  }

  var body: some View {
    @Bindable var store = store
    Form {
      Section {
        ForEach(store.connections) { connection in
          Button {
            store.select(connection)
            store.startMonitoring()
          } label: {
            HStack {
              VStack(alignment: .leading, spacing: 2) {
                Text(connection.name).foregroundStyle(.primary)
                Text(connection.baseURL).font(.caption).foregroundStyle(.secondary)
              }
              Spacer()
              if connection.id == store.connection?.id {
                Image(systemName: "checkmark").foregroundStyle(Theme.accent)
              }
            }
          }
          .swipeActions {
            Button("Forget", role: .destructive) { forget = connection }
          }
        }
        Button("Add server…", systemImage: "plus") { store.addingConnection = true }
        if store.demo {
          Button("Leave demo", role: .destructive) {
            store.disconnect()
            dismiss()
          }
        }
      } header: {
        Text("Servers")
      } footer: {
        if !store.connections.isEmpty { Text("Swipe a server to forget it on this device.") }
      }

      Section("Notifications") {
        if notifications.status == "Allowed" {
          LabeledContent("This device", value: notifications.registration)
        } else {
          Button("Turn on notifications") {
            Task { await notifications.enable(api: store.client) }
          }.disabled(store.demo)
          if notifications.status == "Not allowed" {
            Button("Open iOS Settings") {
              if let url = URL(string: UIApplication.openNotificationSettingsURLString) {
                UIApplication.shared.open(url)
              }
            }
          }
        }
        if let providers, providers.object["providers"]?.object["apns"]?.bool != true {
          Label("Push isn't configured on the server", systemImage: "exclamationmark.triangle")
            .foregroundStyle(Theme.amber).font(.subheadline)
        }
        if let error = notifications.error {
          Text(error).foregroundStyle(Theme.red).font(.caption)
        }
        Button(testSent ? "Test sent" : "Send a test notification") { sendTest() }
          .disabled(store.demo || testSent)
      }

      if !store.demo && !preferences.isEmpty {
        Section {
          Toggle(
            "Job notifications",
            isOn: Binding(
              get: { preferences["enabled"]?.bool ?? true },
              set: {
                preferences["enabled"] = .bool($0)
                saved = false
              }))
        } footer: {
          Text("Shared by every device using this server's API key.")
        }
        Section {
          ForEach(states, id: \.0) { code, label in
            Toggle(label, isOn: member(code, of: $allowedStates))
          }
        } header: {
          Text("Notify when a job")
        } footer: {
          Text("With none selected, the server notifies for finished jobs.")
        }
        if !store.hosts.isEmpty {
          Section("Hosts") {
            ForEach(store.hosts) { host in
              Toggle(
                host.hostname,
                isOn: Binding(
                  get: { !mutedHosts.contains(host.hostname) },
                  set: {
                    if $0 {
                      mutedHosts.remove(host.hostname)
                    } else {
                      mutedHosts.insert(host.hostname)
                    }
                    saved = false
                  }))
            }
          }
        }
        Section {
          TextField("Muted job names (patterns)", text: $mutedNames)
          TextField("Only these users", text: $allowedUsers)
          Button(saving ? "Saving…" : saved ? "Saved" : "Save notification rules") {
            Task { await savePreferences() }
          }.disabled(saving || saved)
        } footer: {
          Text("Comma separated. Leave users empty to include everyone.")
        }
        .textInputAutocapitalization(.never).autocorrectionDisabled()
        .onChange(of: mutedNames) { _, _ in saved = false }
        .onChange(of: allowedUsers) { _, _ in saved = false }
      }

      Section {
        Toggle("Hide job details in widgets", isOn: $store.widgetPrivacy)
        Button("End all Live Activities") { Task { await LiveActivityService.shared.endAll() } }
      } header: {
        Text("Widgets & Lock Screen")
      } footer: {
        Text("Widgets and Live Activities refresh while ssync is open.")
      }

      Section {
        LabeledContent("Version", value: version)
      } footer: {
        HStack(spacing: 6) {
          RelayMark(size: 18)
          Text("ssync for iOS")
        }.frame(maxWidth: .infinity).padding(.top, 12)
      }
    }
    .navigationTitle("Settings")
    .navigationBarTitleDisplayMode(.inline)
    .toolbar {
      ToolbarItem(placement: .confirmationAction) { Button("Done") { dismiss() } }
    }
    .alert(
      "Something went wrong",
      isPresented: Binding(get: { error != nil }, set: { if !$0 { error = nil } })
    ) {
      Button("OK") {}
    } message: {
      Text(error ?? "")
    }
    .confirmationDialog(
      "Forget \(forget?.name ?? "this server")?",
      isPresented: Binding(get: { forget != nil }, set: { if !$0 { forget = nil } }),
      titleVisibility: .visible
    ) {
      if let forget {
        Button("Forget server", role: .destructive) { forgetConnection(forget) }
      }
    } message: {
      Text("Removes its key, drafts, saved output, and this device's notification registration.")
    }
    .task { await load() }
  }

  private func member(_ code: String, of set: Binding<Set<String>>) -> Binding<Bool> {
    Binding(
      get: { set.wrappedValue.contains(code) },
      set: {
        if $0 { set.wrappedValue.insert(code) } else { set.wrappedValue.remove(code) }
        saved = false
      })
  }
  private func sendTest() {
    Task {
      do {
        guard let token = UserDefaults.standard.string(forKey: "apnsToken"),
          let api = store.client
        else {
          throw APIError(status: 0, message: "Turn on notifications for this device first.")
        }
        try await api.perform(
          "api/notifications/test",
          body: .object([
            "title": .string("ssync is connected"),
            "body": .string("Your job updates will arrive here."), "token": .string(token),
            "token_type": .string("apns"),
          ]))
        testSent = true
      } catch { self.error = error.localizedDescription }
    }
  }
  private func forgetConnection(_ connection: Connection) {
    Task {
      do {
        if let token = UserDefaults.standard.string(forKey: "apnsToken") {
          let api = APIClient(connection: connection, apiKey: CredentialStore.read(connection.id))
          try await api.perform("api/notifications/devices/\(token)", method: "DELETE")
        }
        try store.forget(connection)
        forget = nil
        if store.connection == nil { dismiss() }
      } catch {
        self.error = "Couldn’t remove this device registration: \(error.localizedDescription)"
      }
    }
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
      func list(_ name: String) -> [String] {
        preferences[name]?.array.compactMap(\.string) ?? []
      }
      allowedStates = Set(list("allowed_states"))
      mutedHosts = Set(list("muted_hosts"))
      mutedNames = list("muted_job_name_patterns").joined(separator: ", ")
      allowedUsers = list("allowed_users").joined(separator: ", ")
      providers = try await api.send("api/notifications/status")
      saved = true
    } catch { self.error = error.localizedDescription }
  }
  private func savePreferences() async {
    saving = true
    defer { saving = false }
    func split(_ text: String) -> JSONValue {
      .array(
        text.split(separator: ",").map { .string($0.trimmingCharacters(in: .whitespaces)) }
          .filter { $0.string?.isEmpty == false })
    }
    preferences["allowed_states"] =
      allowedStates.isEmpty ? .null : .array(allowedStates.sorted().map { .string($0) })
    preferences["muted_hosts"] = .array(mutedHosts.sorted().map { .string($0) })
    preferences["muted_job_name_patterns"] = split(mutedNames)
    preferences["allowed_users"] = split(allowedUsers)
    do {
      try await store.client?.perform(
        "api/notifications/preferences", method: "PATCH", body: .object(preferences))
      saved = true
    } catch { self.error = error.localizedDescription }
  }
}
