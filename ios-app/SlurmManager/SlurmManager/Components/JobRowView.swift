import SwiftUI
import Combine

// MARK: - Enhanced Job Row View with Swipe Actions
struct EnhancedJobRowView: View {
    let job: Job
    var onCancel: (() -> Void)?
    var onRefresh: (() -> Void)?
    var onViewOutput: (() -> Void)?

    @State private var isPressed = false
    @State private var showDetails = false
    @State private var offset: CGFloat = 0
    @State private var lastUpdate = Date()

    // Swipe action thresholds
    private let swipeThreshold: CGFloat = 80
    private let maxSwipe: CGFloat = 160

    var body: some View {
        ZStack {
            // Swipe action backgrounds
            HStack(spacing: 0) {
                // Left swipe actions (trailing)
                if job.isRunning {
                    swipeActionButton(
                        icon: "xmark.circle.fill",
                        label: "Cancel",
                        color: .red
                    ) {
                        onCancel?()
                    }
                }

                Spacer()

                // Right swipe actions (leading)
                swipeActionButton(
                    icon: "arrow.clockwise.circle.fill",
                    label: "Refresh",
                    color: .blue
                ) {
                    onRefresh?()
                }

                swipeActionButton(
                    icon: "doc.text.fill",
                    label: "Output",
                    color: .purple
                ) {
                    onViewOutput?()
                }
            }

            // Main card content
            mainContent
                .offset(x: offset)
                .gesture(swipeGesture)
        }
        .clipShape(RoundedRectangle(cornerRadius: 12))
    }

    // MARK: - Main Content
    var mainContent: some View {
        CardView(padding: 0) {
            VStack(spacing: 0) {
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
                                CachedBadge()
                            }

                            Spacer()

                            // Live time display for running jobs
                            if job.isRunning {
                                LiveTimeDisplay(startTime: job.startTime)
                            } else if let duration = job.formattedDuration {
                                Text(duration)
                                    .font(.caption)
                                    .fontWeight(.medium)
                                    .foregroundColor(.secondary)
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

                            Spacer()

                            // User
                            Label {
                                Text(job.user)
                                    .font(.caption)
                            } icon: {
                                Image(systemName: "person.circle")
                                    .font(.caption2)
                            }
                            .foregroundColor(.secondary)
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
                                        text: "\(nodes) nodes",
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
                                        icon: "bolt.fill",
                                        text: "\(cpus) CPUs",
                                        color: .orange
                                    )
                                }

                                if let timeLimit = job.timeLimit {
                                    ResourceBadge(
                                        icon: "clock",
                                        text: timeLimit,
                                        color: .gray
                                    )
                                }
                            }
                        }
                    }
                    .padding(.vertical, 12)

                    // State badge and actions
                    VStack(spacing: 6) {
                        AnimatedStatusBadge(state: job.state)

                        if job.state == .running {
                            ProgressIndicator()
                                .frame(width: 18, height: 18)
                        }
                    }
                    .padding(.trailing, 12)
                }

                // Expandable quick info
                if showDetails {
                    expandedDetails
                }
            }
        }
        .scaleEffect(isPressed ? 0.98 : 1.0)
        .animation(.spring(response: 0.3, dampingFraction: 0.7), value: isPressed)
        .contentShape(Rectangle())
        .onTapGesture {
            withAnimation(.spring(response: 0.35, dampingFraction: 0.7)) {
                showDetails.toggle()
            }
            HapticManager.impact(.light)
        }
        .simultaneousGesture(
            LongPressGesture(minimumDuration: 0.1)
                .onChanged { _ in isPressed = true }
                .onEnded { _ in isPressed = false }
        )
    }

    // MARK: - Expanded Details
    var expandedDetails: some View {
        VStack(spacing: 0) {
            Divider()
                .padding(.horizontal, 12)

            VStack(alignment: .leading, spacing: 8) {
                if let submitTime = job.submitTime {
                    DetailRow(
                        icon: "calendar.badge.clock",
                        label: "Submitted",
                        value: formatDate(submitTime)
                    )
                }

                if let startTime = job.startTime {
                    DetailRow(
                        icon: "play.circle.fill",
                        label: "Started",
                        value: formatDate(startTime)
                    )
                }

                if let endTime = job.endTime {
                    DetailRow(
                        icon: "stop.circle.fill",
                        label: "Ended",
                        value: formatDate(endTime)
                    )
                }

                if let workDir = job.workDir {
                    DetailRow(
                        icon: "folder.fill",
                        label: "Directory",
                        value: workDir
                    )
                    .lineLimit(1)
                }

                if let qos = job.qos {
                    DetailRow(
                        icon: "gauge.medium",
                        label: "QoS",
                        value: qos
                    )
                }
            }
            .padding(12)
            .transition(.asymmetric(
                insertion: .push(from: .top).combined(with: .opacity),
                removal: .scale.combined(with: .opacity)
            ))
        }
    }

    // MARK: - Swipe Actions
    var swipeGesture: some Gesture {
        DragGesture(minimumDistance: 20, coordinateSpace: .local)
            .onChanged { value in
                let translation = value.translation.width

                // Limit swipe distance with rubber band effect
                if translation > 0 {
                    offset = min(maxSwipe, translation * 0.6)
                } else if job.isRunning {
                    offset = max(-maxSwipe, translation * 0.6)
                }
            }
            .onEnded { value in
                let velocity = value.predictedEndLocation.x - value.location.x

                withAnimation(.spring(response: 0.35, dampingFraction: 0.7)) {
                    // Trigger action if past threshold or high velocity
                    if offset > swipeThreshold || velocity > 300 {
                        // Right swipe - refresh
                        HapticManager.notification(.success)
                        onRefresh?()
                    } else if offset < -swipeThreshold || velocity < -300 {
                        // Left swipe - cancel (if running)
                        if job.isRunning {
                            HapticManager.notification(.warning)
                            onCancel?()
                        }
                    }

                    offset = 0
                }
            }
    }

    @ViewBuilder
    func swipeActionButton(
        icon: String,
        label: String,
        color: Color,
        action: @escaping () -> Void
    ) -> some View {
        Button(action: action) {
            VStack(spacing: 4) {
                Image(systemName: icon)
                    .font(.title2)
                Text(label)
                    .font(.caption2)
            }
            .foregroundColor(.white)
            .frame(width: 80)
            .frame(maxHeight: .infinity)
            .background(color)
        }
    }

    private func formatDate(_ date: Date) -> String {
        let formatter = RelativeDateTimeFormatter()
        formatter.unitsStyle = .abbreviated
        return formatter.localizedString(for: date, relativeTo: Date())
    }
}

// MARK: - Animated Status Badge
struct AnimatedStatusBadge: View {
    let state: JobState
    @State private var isAnimating = false

    var body: some View {
        Text(state.displayName)
            .font(.caption)
            .fontWeight(.semibold)
            .padding(.horizontal, 10)
            .padding(.vertical, 5)
            .background(
                ZStack {
                    // Base color
                    color.opacity(0.15)

                    // Animated glow for running
                    if state == .running {
                        color.opacity(isAnimating ? 0.3 : 0.1)
                            .animation(
                                .easeInOut(duration: 1.5)
                                .repeatForever(autoreverses: true),
                                value: isAnimating
                            )
                    }
                }
            )
            .foregroundColor(color)
            .cornerRadius(8)
            .overlay(
                RoundedRectangle(cornerRadius: 8)
                    .strokeBorder(color.opacity(0.3), lineWidth: 1)
            )
            .onAppear {
                if state == .running {
                    isAnimating = true
                }
            }
    }

    var color: Color {
        state.color
    }
}

// MARK: - Live Time Display
struct LiveTimeDisplay: View {
    let startTime: Date?
    @State private var currentTime = Date()
    @State private var pulse = false

    private let timer = Timer.publish(every: 1, on: .main, in: .common).autoconnect()

    var body: some View {
        HStack(spacing: 4) {
            Circle()
                .fill(Color.green)
                .frame(width: 6, height: 6)
                .scaleEffect(pulse ? 1.3 : 0.8)
                .animation(
                    .easeInOut(duration: 1)
                    .repeatForever(autoreverses: true),
                    value: pulse
                )

            Text(formattedDuration)
                .font(.system(.caption, design: .monospaced))
                .fontWeight(.medium)
                .foregroundColor(.blue)
        }
        .onReceive(timer) { time in
            currentTime = time
        }
        .onAppear {
            pulse = true
        }
    }

    var formattedDuration: String {
        guard let start = startTime else { return "--:--" }
        let duration = currentTime.timeIntervalSince(start)

        let hours = Int(duration) / 3600
        let minutes = (Int(duration) % 3600) / 60
        let seconds = Int(duration) % 60

        if hours > 0 {
            return String(format: "%02d:%02d:%02d", hours, minutes, seconds)
        } else {
            return String(format: "%02d:%02d", minutes, seconds)
        }
    }
}

// MARK: - Cached Badge
struct CachedBadge: View {
    var body: some View {
        HStack(spacing: 2) {
            Image(systemName: "clock.arrow.circlepath")
            Text("cached")
        }
        .font(.system(size: 9))
        .foregroundColor(.secondary)
        .padding(.horizontal, 5)
        .padding(.vertical, 2)
        .background(Color(.systemGray6))
        .cornerRadius(4)
    }
}

// MARK: - Supporting Components
struct StatusIndicator: View {
    let state: JobState
    @State private var isAnimating = false

    var body: some View {
        GeometryReader { geometry in
            Rectangle()
                .fill(color)
                .overlay(
                    Group {
                        if state == .running {
                            Rectangle()
                                .fill(
                                    LinearGradient(
                                        colors: [color.opacity(0), color.opacity(0.8), color.opacity(0)],
                                        startPoint: .top,
                                        endPoint: .bottom
                                    )
                                )
                                .frame(height: geometry.size.height * 0.5)
                                .offset(y: isAnimating ? geometry.size.height : -geometry.size.height)
                                .animation(
                                    .linear(duration: 1.5)
                                    .repeatForever(autoreverses: false),
                                    value: isAnimating
                                )
                        }
                    }
                )
                .mask(Rectangle())
        }
        .onAppear {
            if state == .running {
                isAnimating = true
            }
        }
    }

    var color: Color {
        state.color
    }
}

struct ResourceBadge: View {
    let icon: String
    let text: String
    let color: Color

    var body: some View {
        HStack(spacing: 4) {
            Image(systemName: icon)
                .font(.system(size: 9))
            Text(text)
                .font(.system(size: 10, weight: .medium))
        }
        .padding(.horizontal, 8)
        .padding(.vertical, 4)
        .background(color.opacity(0.12))
        .foregroundColor(color)
        .cornerRadius(6)
    }
}

struct ProgressIndicator: View {
    @State private var rotation = 0.0

    var body: some View {
        Circle()
            .trim(from: 0.0, to: 0.7)
            .stroke(
                AngularGradient(
                    colors: [.blue, .blue.opacity(0.3), .blue.opacity(0)],
                    center: .center
                ),
                style: StrokeStyle(lineWidth: 2, lineCap: .round)
            )
            .rotationEffect(.degrees(rotation))
            .onAppear {
                withAnimation(
                    .linear(duration: 1)
                    .repeatForever(autoreverses: false)
                ) {
                    rotation = 360
                }
            }
    }
}

struct DetailRow: View {
    var icon: String = ""
    let label: String
    let value: String

    var body: some View {
        HStack(spacing: 8) {
            if !icon.isEmpty {
                Image(systemName: icon)
                    .font(.caption2)
                    .foregroundColor(.secondary)
                    .frame(width: 14)
            }
            Text(label)
                .font(.caption)
                .foregroundColor(.secondary)
            Spacer()
            Text(value)
                .font(.caption)
                .foregroundColor(.primary)
                .lineLimit(1)
        }
    }
}

struct ConnectionStatusBadge: View {
    @StateObject private var appState = AppState.shared

    var body: some View {
        HStack(spacing: 6) {
            Circle()
                .fill(statusColor)
                .frame(width: 8, height: 8)
                .shadow(color: statusColor.opacity(0.5), radius: 2)

            if case .connecting = appState.connectionStatus {
                ProgressView()
                    .scaleEffect(0.5)
                    .frame(width: 12, height: 12)
            }
        }
        .padding(.horizontal, 10)
        .padding(.vertical, 6)
        .background(statusColor.opacity(0.12))
        .cornerRadius(12)
        .animation(.easeInOut(duration: 0.3), value: appState.connectionStatus.displayText)
    }

    var statusColor: Color {
        appState.connectionStatus.color
    }
}

// MARK: - JobState Color Extension
extension JobState {
    var color: Color {
        switch self {
        case .running: return .blue
        case .pending: return .orange
        case .completed: return .green
        case .failed, .timeout, .nodeFailure, .outOfMemory, .bootFail: return .red
        case .cancelled: return .gray
        case .completing, .configuring: return .cyan
        case .suspended, .preempted: return .yellow
        case .deadline: return .pink
        }
    }
}

// MARK: - Preview
#Preview {
    VStack(spacing: 12) {
        EnhancedJobRowView(
            job: Job(
                id: "12345",
                name: "training_model_v2",
                user: "jsmith",
                state: .running,
                submitTime: Date().addingTimeInterval(-3600),
                startTime: Date().addingTimeInterval(-1800),
                endTime: nil,
                partition: "gpu",
                nodes: "4",
                cpus: 32,
                memory: "128G",
                timeLimit: "24:00:00",
                workDir: "/home/jsmith/projects/ml-training",
                command: nil,
                array: nil,
                qos: "normal",
                account: "research",
                host: "cluster1.example.com",
                cached: false
            ),
            onCancel: { print("Cancel") },
            onRefresh: { print("Refresh") },
            onViewOutput: { print("View Output") }
        )

        EnhancedJobRowView(
            job: Job(
                id: "12346",
                name: "data_preprocessing",
                user: "jsmith",
                state: .completed,
                submitTime: Date().addingTimeInterval(-7200),
                startTime: Date().addingTimeInterval(-6000),
                endTime: Date().addingTimeInterval(-3600),
                partition: "batch",
                nodes: "1",
                cpus: 8,
                memory: "16G",
                timeLimit: "02:00:00",
                workDir: nil,
                command: nil,
                array: nil,
                qos: nil,
                account: nil,
                host: "cluster2.example.com",
                cached: true
            )
        )

        EnhancedJobRowView(
            job: Job(
                id: "12347",
                name: "waiting_job",
                user: "jsmith",
                state: .pending,
                submitTime: Date().addingTimeInterval(-300),
                startTime: nil,
                endTime: nil,
                partition: "gpu",
                nodes: "8",
                cpus: 64,
                memory: "256G",
                timeLimit: "48:00:00",
                workDir: nil,
                command: nil,
                array: nil,
                qos: "high",
                account: nil,
                host: "cluster1.example.com",
                cached: false
            )
        )
    }
    .padding()
}
