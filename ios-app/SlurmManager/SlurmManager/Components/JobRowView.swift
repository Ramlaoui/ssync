import SwiftUI

struct EnhancedJobRowView: View {
    let job: Job
    @State private var isPressed = false
    @State private var showDetails = false
    
    var body: some View {
        CardView(padding: 0) {
            VStack(spacing: 0) {
                // Main content
                HStack(spacing: 12) {
                    // Status indicator with animation
                    StatusIndicator(state: job.state)
                        .frame(width: 4)
                    
                    // Job info
                    VStack(alignment: .leading, spacing: 6) {
                        // Title row
                        HStack {
                            Text(job.name)
                                .font(.headline)
                                .lineLimit(1)
                                .foregroundColor(.primary)
                            
                            if job.cached {
                                Image(systemName: "clock.arrow.circlepath")
                                    .font(.caption2)
                                    .foregroundColor(.secondary)
                            }
                            
                            Spacer()
                            
                            // Time display
                            if job.isRunning, let duration = job.formattedDuration {
                                TimeDisplay(duration: duration)
                            }
                        }
                        
                        // Job ID and Host
                        HStack(spacing: 12) {
                            Label {
                                Text(job.id)
                                    .font(.caption)
                            } icon: {
                                Image(systemName: "number.circle.fill")
                                    .font(.caption2)
                            }
                            .foregroundColor(.secondary)
                            
                            if let host = job.host.split(separator: ".").first {
                                Label {
                                    Text(String(host))
                                        .font(.caption)
                                } icon: {
                                    Image(systemName: "server.rack")
                                        .font(.caption2)
                                }
                                .foregroundColor(.secondary)
                            }
                        }
                        
                        // Resource badges
                        ScrollView(.horizontal, showsIndicators: false) {
                            HStack(spacing: 8) {
                                if let partition = job.partition {
                                    ResourceBadge(
                                        icon: "square.stack.3d.up",
                                        text: partition,
                                        color: .blue
                                    )
                                }
                                
                                if let nodes = job.nodes {
                                    ResourceBadge(
                                        icon: "cpu",
                                        text: nodes,
                                        color: .purple
                                    )
                                }
                                
                                if let memory = job.memory {
                                    ResourceBadge(
                                        icon: "memorychip",
                                        text: memory,
                                        color: .green
                                    )
                                }
                                
                                if let cpus = job.cpus {
                                    ResourceBadge(
                                        icon: "speedometer",
                                        text: "\(cpus) CPUs",
                                        color: .orange
                                    )
                                }
                            }
                        }
                    }
                    .padding(.vertical, 12)
                    
                    // State badge
                    VStack {
                        StatusBadge(
                            status: job.state.displayName,
                            color: statusColor
                        )
                        
                        if job.state == .running {
                            ProgressIndicator()
                                .frame(width: 20, height: 20)
                                .padding(.top, 4)
                        }
                    }
                    .padding(.trailing, 12)
                }
                
                // Expandable details (if tapped)
                if showDetails {
                    Divider()
                    
                    VStack(alignment: .leading, spacing: 8) {
                        if let submitTime = job.submitTime {
                            DetailRow(
                                label: "Submitted",
                                value: formatDate(submitTime)
                            )
                        }
                        
                        if let workDir = job.workDir {
                            DetailRow(
                                label: "Work Dir",
                                value: workDir
                            )
                            .font(.caption2)
                        }
                    }
                    .padding(12)
                    .transition(.asymmetric(
                        insertion: .push(from: .top).combined(with: .opacity),
                        removal: .push(from: .bottom).combined(with: .opacity)
                    ))
                }
            }
        }
        .scaleEffect(isPressed ? 0.98 : 1.0)
        .animation(.spring(response: 0.3, dampingFraction: 0.6), value: isPressed)
        .onTapGesture {
            withAnimation(.spring()) {
                showDetails.toggle()
            }
            HapticManager.impact(.light)
        }
        .onLongPressGesture(minimumDuration: 0, maximumDistance: .infinity) { _ in
            
        } onPressingChanged: { pressing in
            isPressed = pressing
        }
    }
    
    var statusColor: Color {
        switch job.state {
        case .running: return .blue
        case .pending: return .orange
        case .completed: return .green
        case .failed, .timeout, .nodeFailure, .outOfMemory: return .red
        case .cancelled: return .gray
        default: return .gray
        }
    }
    
    private func formatDate(_ date: Date) -> String {
        let formatter = RelativeDateTimeFormatter()
        formatter.unitsStyle = .abbreviated
        return formatter.localizedString(for: date, relativeTo: Date())
    }
}

// MARK: - Supporting Components

struct StatusIndicator: View {
    let state: JobState
    @State private var isAnimating = false
    
    var body: some View {
        Rectangle()
            .fill(color)
            .overlay(
                Group {
                    if state == .running {
                        Rectangle()
                            .fill(
                                LinearGradient(
                                    colors: [color.opacity(0), color, color.opacity(0)],
                                    startPoint: .top,
                                    endPoint: .bottom
                                )
                            )
                            .offset(y: isAnimating ? 30 : -30)
                            .animation(
                                Animation.linear(duration: 1.5)
                                    .repeatForever(autoreverses: false),
                                value: isAnimating
                            )
                    }
                }
            )
            .mask(Rectangle())
            .onAppear {
                if state == .running {
                    isAnimating = true
                }
            }
    }
    
    var color: Color {
        switch state {
        case .running: return .blue
        case .pending: return .orange
        case .completed: return .green
        case .failed, .timeout, .nodeFailure, .outOfMemory: return .red
        case .cancelled: return .gray
        default: return .gray
        }
    }
}

struct ResourceBadge: View {
    let icon: String
    let text: String
    let color: Color
    
    var body: some View {
        HStack(spacing: 4) {
            Image(systemName: icon)
                .font(.caption2)
            Text(text)
                .font(.caption2)
                .fontWeight(.medium)
        }
        .padding(.horizontal, 8)
        .padding(.vertical, 4)
        .background(color.opacity(0.15))
        .foregroundColor(color)
        .cornerRadius(6)
    }
}

struct TimeDisplay: View {
    let duration: String
    @State private var pulse = false
    
    var body: some View {
        HStack(spacing: 4) {
            Circle()
                .fill(Color.green)
                .frame(width: 6, height: 6)
                .scaleEffect(pulse ? 1.2 : 0.8)
                .animation(
                    Animation.easeInOut(duration: 1)
                        .repeatForever(autoreverses: true),
                    value: pulse
                )
            
            Text(duration)
                .font(.caption)
                .fontWeight(.medium)
                .foregroundColor(.blue)
        }
        .onAppear {
            pulse = true
        }
    }
}

struct ProgressIndicator: View {
    @State private var rotation = 0.0
    
    var body: some View {
        Circle()
            .trim(from: 0.0, to: 0.7)
            .stroke(
                AngularGradient(
                    colors: [.blue, .blue.opacity(0.5), .blue.opacity(0)],
                    center: .center
                ),
                lineWidth: 2
            )
            .rotationEffect(.degrees(rotation))
            .animation(
                Animation.linear(duration: 1)
                    .repeatForever(autoreverses: false),
                value: rotation
            )
            .onAppear {
                rotation = 360
            }
    }
}

struct DetailRow: View {
    let label: String
    let value: String
    
    var body: some View {
        HStack {
            Text(label)
                .font(.caption)
                .foregroundColor(.secondary)
            Spacer()
            Text(value)
                .font(.caption)
                .foregroundColor(.primary)
        }
    }
}

struct ConnectionStatusBadge: View {
    @EnvironmentObject var appState: AppState
    
    var body: some View {
        HStack(spacing: 4) {
            Circle()
                .fill(appState.connectionStatus.color)
                .frame(width: 8, height: 8)
            
            if appState.connectionStatus == .connecting {
                ProgressView()
                    .scaleEffect(0.5)
            }
        }
        .padding(.horizontal, 8)
        .padding(.vertical, 4)
        .background(appState.connectionStatus.color.opacity(0.15))
        .cornerRadius(12)
    }
}