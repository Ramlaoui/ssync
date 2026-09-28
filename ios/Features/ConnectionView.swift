import SwiftUI

struct ConnectionView: View {
  @Environment(AppStore.self) private var store
  @Environment(\.dismiss) private var dismiss
  var adding = false
  @State private var name = ""
  @State private var address = ""
  @State private var key = ""
  @State private var busy = false
  @State private var error: String?
  var body: some View {
    NavigationStack {
      Form {
        Section {
          VStack(spacing: 10) {
            RelayMark(size: 56)
            Text("ssync").font(.largeTitle.weight(.bold))
            Text("Your cluster work, within reach.").font(.subheadline)
              .foregroundStyle(.secondary)
          }
          .frame(maxWidth: .infinity).padding(.vertical, 8)
          .listRowBackground(Color.clear)
        }
        if !adding && !store.connections.isEmpty {
          Section("Saved servers") {
            ForEach(store.connections) { connection in
              Button {
                store.select(connection)
                store.startMonitoring()
              } label: {
                LabeledContent(connection.name, value: URL(string: connection.baseURL)?.host ?? "")
              }.tint(.primary)
            }
          }
        }
        Section {
          TextField("https://ssync.example.com:8042", text: $address)
            .keyboardType(.URL).textContentType(.URL).textInputAutocapitalization(.never)
            .autocorrectionDisabled()
            .accessibilityIdentifier("serverURL")
          SecureField("API key (if enabled)", text: $key).textInputAutocapitalization(.never)
          TextField("Name (optional)", text: $name)
        } header: {
          Text(adding ? "Add a server" : "Connect to your server")
        } footer: {
          Text("The address of your ssync API server. HTTPS needs a certificate trusted by iOS.")
        }
        if let error {
          Section {
            Label(error, systemImage: "exclamationmark.triangle").foregroundStyle(Theme.amber)
          }
        }
        Section {
          Button(action: connect) {
            HStack {
              if busy { ProgressView() }
              Text(busy ? "Checking…" : "Connect").frame(maxWidth: .infinity)
            }
          }
          .buttonStyle(.borderedProminent).controlSize(.large)
          .disabled(busy || address.isEmpty)
          .listRowBackground(Color.clear).listRowInsets(EdgeInsets())
          if !adding {
            Button("Explore the demo") { store.select(.sample) }
              .frame(maxWidth: .infinity)
              .listRowBackground(Color.clear)
              .accessibilityIdentifier("exploreDemo")
          }
        }
      }
      .toolbar {
        if adding { ToolbarItem(placement: .cancellationAction) { Button("Cancel") { dismiss() } } }
      }
    }
  }
  private func connect() {
    busy = true
    error = nil
    Task {
      do {
        var url = address.trimmingCharacters(in: .whitespacesAndNewlines)
        if !url.contains("://") { url = "https://" + url }
        let connection = Connection(
          name: name.isEmpty ? (URL(string: url)?.host ?? "ssync") : name, baseURL: url)
        try await store.connect(connection, key: key)
        if adding { dismiss() }
      } catch { self.error = error.localizedDescription }
      busy = false
    }
  }
}
