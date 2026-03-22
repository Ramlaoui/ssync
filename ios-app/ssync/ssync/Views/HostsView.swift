import SwiftUI

struct HostsView: View {
    @State private var hosts: [Host] = []
    @State private var isLoading = false
    @State private var errorMessage: String?
    @State private var searchText = ""

    var body: some View {
        NavigationView {
            Group {
                if isLoading && hosts.isEmpty {
                    LoadingView(message: "Loading hosts...")
                } else if let errorMessage, hosts.isEmpty {
                    ErrorView(
                        error: errorMessage,
                        retry: { Task { await loadHosts() } }
                    )
                } else if filteredHosts.isEmpty {
                    EmptyStateView(
                        icon: "network.slash",
                        title: "No Hosts",
                        message: hosts.isEmpty ? "No hosts are configured on the server." : "No hosts match '\(searchText)'.",
                        action: hosts.isEmpty ? { Task { await loadHosts() } } : { searchText = "" },
                        actionLabel: hosts.isEmpty ? "Retry" : "Clear Search"
                    )
                } else {
                    List(filteredHosts) { host in
                        HostRowView(host: host)
                    }
                    .listStyle(.insetGrouped)
                }
            }
            .navigationTitle("Hosts")
            .searchable(text: $searchText, prompt: "Search hosts")
            .refreshable {
                await loadHosts()
            }
            .task {
                if hosts.isEmpty {
                    await loadHosts()
                }
            }
        }
    }

    private var filteredHosts: [Host] {
        let query = searchText.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !query.isEmpty else { return hosts }

        return hosts.filter { host in
            host.displayName.localizedCaseInsensitiveContains(query) ||
            host.hostname.localizedCaseInsensitiveContains(query) ||
            host.connectionString.localizedCaseInsensitiveContains(query)
        }
    }

    private func loadHosts() async {
        if isLoading { return }
        isLoading = true
        errorMessage = nil
        defer { isLoading = false }

        do {
            let fetchedHosts = try await APIClient.shared.getHosts().async()
            hosts = fetchedHosts.sorted { lhs, rhs in
                if lhs.isAvailable != rhs.isAvailable {
                    return lhs.isAvailable && !rhs.isAvailable
                }
                if lhs.isDefault != rhs.isDefault {
                    return lhs.isDefault && !rhs.isDefault
                }
                return lhs.displayName.localizedCaseInsensitiveCompare(rhs.displayName) == .orderedAscending
            }
        } catch {
            errorMessage = error.localizedDescription
        }
    }
}

struct HostRowView: View {
    let host: Host

    var body: some View {
        HStack(spacing: 12) {
            Image(systemName: host.isAvailable ? "checkmark.circle.fill" : "xmark.circle.fill")
                .foregroundColor(host.isAvailable ? .green : .red)

            VStack(alignment: .leading, spacing: 4) {
                HStack(spacing: 8) {
                    Text(host.displayName)
                        .font(.headline)
                    if host.isDefault {
                        Text("Default")
                            .font(.caption2)
                            .padding(.horizontal, 6)
                            .padding(.vertical, 2)
                            .background(Color.accentColor.opacity(0.15))
                            .foregroundColor(.accentColor)
                            .clipShape(Capsule())
                    }
                }

                Text(host.connectionString)
                    .font(.caption)
                    .foregroundColor(.secondary)

                if let lastError = host.lastError,
                   !lastError.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
                    Text(lastError)
                        .font(.caption2)
                        .foregroundColor(.red)
                        .lineLimit(2)
                }
            }

            Spacer()
        }
        .padding(.vertical, 4)
    }
}
