import SwiftUI
import Combine

// MARK: - Connection Status Bar
/// A banner that shows connection status and offline mode indicator
struct ConnectionStatusBar: View {
    @StateObject private var appState = AppState.shared
    @State private var isVisible = false
    @State private var lastUpdateTime = Date()

    var body: some View {
        Group {
            if shouldShowBanner {
                bannerContent
                    .transition(.move(edge: .top).combined(with: .opacity))
            }
        }
        .animation(.spring(response: 0.4, dampingFraction: 0.8), value: shouldShowBanner)
        .onChange(of: appState.connectionStatus) { newStatus in
            withAnimation {
                // Show banner when status changes
                isVisible = true
            }

            // Hide success banners after 3 seconds
            if newStatus == .connected {
                DispatchQueue.main.asyncAfter(deadline: .now() + 3) {
                    withAnimation {
                        isVisible = false
                    }
                }
            }
        }
    }

    var shouldShowBanner: Bool {
        switch appState.connectionStatus {
        case .disconnected, .error:
            return true
        case .connecting:
            return true
        case .connected:
            return isVisible
        }
    }

    var bannerContent: some View {
        HStack(spacing: 12) {
            // Status icon
            statusIcon

            // Status text
            VStack(alignment: .leading, spacing: 2) {
                Text(statusTitle)
                    .font(.subheadline)
                    .fontWeight(.semibold)

                Text(statusSubtitle)
                    .font(.caption)
                    .foregroundColor(.white.opacity(0.8))
            }

            Spacer()

            // Action button or progress
            if case .connecting = appState.connectionStatus {
                ProgressView()
                    .progressViewStyle(CircularProgressViewStyle(tint: .white))
                    .scaleEffect(0.8)
            } else if case .disconnected = appState.connectionStatus {
                Button(action: reconnect) {
                    Text("Retry")
                        .font(.caption)
                        .fontWeight(.semibold)
                        .padding(.horizontal, 12)
                        .padding(.vertical, 6)
                        .background(Color.white.opacity(0.2))
                        .cornerRadius(6)
                }
            }
        }
        .foregroundColor(.white)
        .padding(.horizontal, 16)
        .padding(.vertical, 12)
        .background(backgroundColor)
        .cornerRadius(12)
        .shadow(color: .black.opacity(0.1), radius: 5, y: 2)
        .padding(.horizontal)
        .padding(.top, 8)
    }

    @ViewBuilder
    var statusIcon: some View {
        ZStack {
            Circle()
                .fill(Color.white.opacity(0.2))
                .frame(width: 36, height: 36)

            switch appState.connectionStatus {
            case .connected:
                Image(systemName: "checkmark.circle.fill")
                    .font(.title3)
            case .connecting:
                Image(systemName: "wifi")
                    .font(.title3)
            case .disconnected:
                Image(systemName: "wifi.slash")
                    .font(.title3)
            case .error:
                Image(systemName: "exclamationmark.triangle.fill")
                    .font(.title3)
            }
        }
    }

    var statusTitle: String {
        switch appState.connectionStatus {
        case .connected:
            return "Connected"
        case .connecting:
            return "Connecting..."
        case .disconnected:
            return "Disconnected"
        case .error(let message):
            return message.isEmpty ? "Connection Error" : message
        }
    }

    var statusSubtitle: String {
        switch appState.connectionStatus {
        case .connected:
            return "Real-time updates active"
        case .connecting:
            return "Establishing connection"
        case .disconnected:
            return "Tap to reconnect"
        case .error:
            return "Check your network and server"
        }
    }

    var backgroundColor: Color {
        switch appState.connectionStatus {
        case .connected:
            return .green
        case .connecting:
            return .blue
        case .disconnected:
            return .orange
        case .error:
            return .red
        }
    }

    private func reconnect() {
        HapticManager.impact(.medium)
        WebSocketManager.shared.connect()
    }
}

// MARK: - Compact Connection Status
/// A smaller connection indicator for toolbar/navigation bar
struct CompactConnectionStatus: View {
    @StateObject private var appState = AppState.shared
    @State private var isAnimating = false

    var body: some View {
        HStack(spacing: 6) {
            Circle()
                .fill(statusColor)
                .frame(width: 8, height: 8)
                .scaleEffect(isAnimating ? 1.2 : 1.0)
                .animation(
                    statusColor == .green
                        ? nil
                        : .easeInOut(duration: 0.8).repeatForever(autoreverses: true),
                    value: isAnimating
                )

            if shouldShowLabel {
                Text(statusLabel)
                    .font(.caption2)
                    .foregroundColor(.secondary)
            }
        }
        .padding(.horizontal, 8)
        .padding(.vertical, 4)
        .background(statusColor.opacity(0.1))
        .cornerRadius(8)
        .onAppear {
            if appState.connectionStatus != .connected {
                isAnimating = true
            }
        }
        .onChange(of: appState.connectionStatus) { newStatus in
            isAnimating = newStatus != .connected
        }
    }

    var statusColor: Color {
        switch appState.connectionStatus {
        case .connected: return .green
        case .connecting: return .blue
        case .disconnected: return .orange
        case .error: return .red
        }
    }

    var shouldShowLabel: Bool {
        appState.connectionStatus != .connected
    }

    var statusLabel: String {
        switch appState.connectionStatus {
        case .connected: return ""
        case .connecting: return "Connecting"
        case .disconnected: return "Offline"
        case .error: return "Error"
        }
    }
}

// MARK: - Offline Mode Banner
struct OfflineModeBanner: View {
    @State private var showDetails = false

    var body: some View {
        VStack(spacing: 0) {
            Button(action: {
                withAnimation(.spring()) {
                    showDetails.toggle()
                }
            }) {
                HStack(spacing: 10) {
                    Image(systemName: "icloud.slash")
                        .font(.subheadline)

                    Text("Working Offline")
                        .font(.subheadline)
                        .fontWeight(.medium)

                    Spacer()

                    Image(systemName: "chevron.down")
                        .font(.caption)
                        .rotationEffect(.degrees(showDetails ? 180 : 0))
                }
                .foregroundColor(.white)
                .padding(.horizontal, 16)
                .padding(.vertical, 10)
                .background(Color.orange)
            }

            if showDetails {
                VStack(alignment: .leading, spacing: 8) {
                    Text("You're viewing cached data. Some features may be unavailable:")
                        .font(.caption)

                    HStack(spacing: 4) {
                        Image(systemName: "xmark.circle.fill")
                            .font(.caption2)
                            .foregroundColor(.red)
                        Text("Real-time updates")
                            .font(.caption)
                    }

                    HStack(spacing: 4) {
                        Image(systemName: "xmark.circle.fill")
                            .font(.caption2)
                            .foregroundColor(.red)
                        Text("Job submission")
                            .font(.caption)
                    }

                    HStack(spacing: 4) {
                        Image(systemName: "checkmark.circle.fill")
                            .font(.caption2)
                            .foregroundColor(.green)
                        Text("View cached jobs")
                            .font(.caption)
                    }
                }
                .padding()
                .frame(maxWidth: .infinity, alignment: .leading)
                .background(Color.orange.opacity(0.1))
                .transition(.asymmetric(
                    insertion: .push(from: .top).combined(with: .opacity),
                    removal: .opacity
                ))
            }
        }
    }
}

// MARK: - Last Sync Indicator
struct LastSyncIndicator: View {
    let lastSyncTime: Date?

    var body: some View {
        if let lastSync = lastSyncTime {
            HStack(spacing: 4) {
                Image(systemName: "arrow.clockwise")
                    .font(.caption2)

                Text("Updated \(formattedTime(lastSync))")
                    .font(.caption2)
            }
            .foregroundColor(.secondary)
        }
    }

    private func formattedTime(_ date: Date) -> String {
        let interval = Date().timeIntervalSince(date)

        if interval < 60 {
            return "just now"
        } else if interval < 3600 {
            let minutes = Int(interval / 60)
            return "\(minutes)m ago"
        } else if interval < 86400 {
            let hours = Int(interval / 3600)
            return "\(hours)h ago"
        } else {
            let formatter = DateFormatter()
            formatter.dateStyle = .short
            formatter.timeStyle = .short
            return formatter.string(from: date)
        }
    }
}

// MARK: - Preview
#Preview("Connection Status Bar") {
    VStack {
        ConnectionStatusBar()

        Spacer()
    }
}

#Preview("Compact Status") {
    HStack {
        CompactConnectionStatus()
        Spacer()
    }
    .padding()
}

#Preview("Offline Banner") {
    VStack {
        OfflineModeBanner()
        Spacer()
    }
}
