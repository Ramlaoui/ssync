import SwiftUI

struct HostsView: View {
    @State private var hosts: [Host] = []
    @State private var isLoading = true
    
    var body: some View {
        NavigationView {
            List(hosts) { host in
                HostRowView(host: host)
            }
            .navigationTitle("Hosts")
            .refreshable {
                await loadHosts()
            }
            .task {
                await loadHosts()
            }
            .overlay {
                if isLoading && hosts.isEmpty {
                    ProgressView("Loading hosts...")
                }
            }
        }
    }
    
    func loadHosts() async {
        isLoading = true
        // Implementation would fetch hosts from API
        isLoading = false
    }
}

struct HostRowView: View {
    let host: Host
    
    var body: some View {
        HStack {
            Image(systemName: host.isAvailable ? "checkmark.circle.fill" : "xmark.circle.fill")
                .foregroundColor(host.isAvailable ? .green : .red)
            
            VStack(alignment: .leading) {
                Text(host.displayName)
                    .font(.headline)
                Text(host.connectionString)
                    .font(.caption)
                    .foregroundColor(.secondary)
            }
            
            Spacer()
            
            if host.isDefault {
                Text("Default")
                    .font(.caption)
                    .padding(.horizontal, 8)
                    .padding(.vertical, 2)
                    .background(Color.blue.opacity(0.2))
                    .cornerRadius(4)
            }
        }
        .padding(.vertical, 4)
    }
}