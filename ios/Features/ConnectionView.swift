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
      Screen {
        HStack(spacing: 8) {
          RelayMark(size: 44)
          Text("ssync").font(.system(.largeTitle, design: .rounded).weight(.bold))
        }.padding(.vertical, 12)
        if !store.connections.isEmpty {
          Eyebrow(title: "Saved connections")
          ForEach(store.connections) { connection in
            Button {
              store.select(connection)
              store.startMonitoring()
              if adding { dismiss() }
            } label: {
              Paper {
                HStack {
                  Image(systemName: "server.rack")
                  Text(connection.name)
                  Spacer()
                  Image(systemName: "arrow.right")
                }
              }
            }.buttonStyle(.plain)
          }
        }
        Paper {
          VStack(alignment: .leading, spacing: 16) {
            Eyebrow(title: "Connect to ssync")
            TextField("Connection name", text: $name).textContentType(.organizationName)
            Divider()
            TextField("https://ssync.example.com:8042", text: $address)
              .keyboardType(.URL).textContentType(.URL).textInputAutocapitalization(.never)
              .autocorrectionDisabled()
              .accessibilityIdentifier("serverURL")
            Divider()
            SecureField("API key (if enabled)", text: $key).textInputAutocapitalization(.never)
            Text(
              "Enter your ssync server URL. HTTPS requires a certificate trusted by iOS."
            )
            .font(.caption).foregroundStyle(Theme.secondary)
          }
        }
        if let error { Notice(title: "Couldn’t connect", detail: error, warning: true) }
        Button {
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
        } label: {
          HStack {
            if busy { ProgressView().tint(Theme.onAccent) }
            Text(busy ? "Checking connection…" : "Connect")
          }
        }.buttonStyle(PrimaryButtonStyle()).disabled(busy || address.isEmpty)
        Button("Explore the demo") {
          store.select(.sample)
          if adding { dismiss() }
        }
        .font(.headline).frame(maxWidth: .infinity).padding(12).accessibilityIdentifier(
          "exploreDemo")
      }
      .toolbar {
        if adding { ToolbarItem(placement: .cancellationAction) { Button("Close") { dismiss() } } }
      }
    }
  }
}
