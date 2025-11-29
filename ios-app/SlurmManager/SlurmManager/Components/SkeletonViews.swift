import SwiftUI

// MARK: - Skeleton Loading Views
/// App Store quality skeleton views for smooth loading states

// MARK: - Shimmer Effect
struct ShimmerEffect: ViewModifier {
    @State private var phase: CGFloat = 0

    func body(content: Content) -> some View {
        content
            .overlay(
                GeometryReader { geometry in
                    LinearGradient(
                        gradient: Gradient(colors: [
                            Color.white.opacity(0),
                            Color.white.opacity(0.4),
                            Color.white.opacity(0)
                        ]),
                        startPoint: .leading,
                        endPoint: .trailing
                    )
                    .frame(width: geometry.size.width * 2)
                    .offset(x: -geometry.size.width + (phase * geometry.size.width * 3))
                }
            )
            .mask(content)
            .onAppear {
                withAnimation(
                    .linear(duration: 1.5)
                    .repeatForever(autoreverses: false)
                ) {
                    phase = 1
                }
            }
    }
}

extension View {
    func skeletonShimmer() -> some View {
        modifier(ShimmerEffect())
    }
}

// MARK: - Skeleton Shape
struct SkeletonShape: View {
    var width: CGFloat? = nil
    var height: CGFloat = 16
    var cornerRadius: CGFloat = 4

    var body: some View {
        RoundedRectangle(cornerRadius: cornerRadius)
            .fill(Color(.systemGray5))
            .frame(width: width, height: height)
            .skeletonShimmer()
    }
}

// MARK: - Job Row Skeleton
struct JobRowSkeleton: View {
    var body: some View {
        HStack(spacing: 12) {
            // Status indicator
            Circle()
                .fill(Color(.systemGray5))
                .frame(width: 10, height: 10)
                .skeletonShimmer()

            VStack(alignment: .leading, spacing: 8) {
                // Job name
                SkeletonShape(width: 180, height: 18)

                // Job ID and host
                HStack(spacing: 12) {
                    SkeletonShape(width: 80, height: 12)
                    SkeletonShape(width: 60, height: 12)
                }

                // Duration and partition
                HStack(spacing: 12) {
                    SkeletonShape(width: 50, height: 12)
                    SkeletonShape(width: 70, height: 12)
                }
            }

            Spacer()

            // State badge
            SkeletonShape(width: 70, height: 24, cornerRadius: 6)
        }
        .padding(.vertical, 8)
        .padding(.horizontal, 4)
    }
}

// MARK: - Job List Skeleton
struct JobListSkeleton: View {
    var count: Int = 8

    var body: some View {
        List {
            ForEach(0..<count, id: \.self) { index in
                JobRowSkeleton()
                    .listRowSeparator(.hidden)
                    .opacity(1.0 - (Double(index) * 0.08))
            }
        }
        .listStyle(.plain)
    }
}

// MARK: - Job Detail Skeleton
struct JobDetailSkeleton: View {
    var body: some View {
        ScrollView {
            VStack(spacing: 20) {
                // Header
                VStack(spacing: 12) {
                    HStack {
                        Circle()
                            .fill(Color(.systemGray5))
                            .frame(width: 12, height: 12)
                            .skeletonShimmer()

                        SkeletonShape(width: 80, height: 18)

                        Spacer()

                        SkeletonShape(width: 60, height: 14)
                    }

                    SkeletonShape(height: 26)

                    HStack(spacing: 20) {
                        SkeletonShape(width: 70, height: 14)
                        SkeletonShape(width: 60, height: 14)
                        SkeletonShape(width: 80, height: 14)
                    }
                }
                .padding()
                .background(Color(.systemGray6))
                .cornerRadius(12)

                // Tab picker skeleton
                SkeletonShape(height: 32, cornerRadius: 8)

                // Content skeleton
                VStack(spacing: 16) {
                    ForEach(0..<8, id: \.self) { _ in
                        HStack {
                            SkeletonShape(width: 80, height: 14)
                            Spacer()
                            SkeletonShape(width: 120, height: 14)
                        }
                    }
                }
                .padding()
            }
            .padding()
        }
    }
}

// MARK: - Host Card Skeleton
struct HostCardSkeleton: View {
    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack {
                Circle()
                    .fill(Color(.systemGray5))
                    .frame(width: 40, height: 40)
                    .skeletonShimmer()

                VStack(alignment: .leading, spacing: 4) {
                    SkeletonShape(width: 120, height: 18)
                    SkeletonShape(width: 80, height: 12)
                }
            }

            Divider()

            HStack {
                VStack(alignment: .leading, spacing: 4) {
                    SkeletonShape(width: 60, height: 12)
                    SkeletonShape(width: 40, height: 20)
                }

                Spacer()

                VStack(alignment: .trailing, spacing: 4) {
                    SkeletonShape(width: 60, height: 12)
                    SkeletonShape(width: 40, height: 20)
                }
            }
        }
        .padding()
        .background(Color(.secondarySystemBackground))
        .cornerRadius(12)
    }
}

// MARK: - Connection Status Skeleton
struct ConnectionStatusSkeleton: View {
    var body: some View {
        HStack(spacing: 8) {
            Circle()
                .fill(Color(.systemGray5))
                .frame(width: 8, height: 8)
                .skeletonShimmer()

            SkeletonShape(width: 70, height: 12)
        }
    }
}

// MARK: - Full Screen Skeleton
struct FullScreenSkeleton: View {
    var body: some View {
        VStack(spacing: 24) {
            // Logo placeholder
            Circle()
                .fill(Color(.systemGray5))
                .frame(width: 80, height: 80)
                .skeletonShimmer()

            // Title
            SkeletonShape(width: 150, height: 24)

            // Subtitle
            SkeletonShape(width: 200, height: 16)

            // Progress indicator
            SkeletonShape(width: 120, height: 4, cornerRadius: 2)
        }
    }
}

// MARK: - Redacted Modifier for Skeletons
struct RedactedSkeleton: ViewModifier {
    let isLoading: Bool

    func body(content: Content) -> some View {
        if isLoading {
            content
                .redacted(reason: .placeholder)
                .skeletonShimmer()
        } else {
            content
        }
    }
}

extension View {
    func skeleton(isLoading: Bool) -> some View {
        modifier(RedactedSkeleton(isLoading: isLoading))
    }
}

// MARK: - Animated Skeleton List
struct AnimatedSkeletonList<Content: View>: View {
    let isLoading: Bool
    let skeletonCount: Int
    @ViewBuilder let content: () -> Content
    @ViewBuilder let skeleton: () -> some View

    @State private var appeared = false

    var body: some View {
        Group {
            if isLoading && !appeared {
                List {
                    ForEach(0..<skeletonCount, id: \.self) { index in
                        skeleton()
                            .transition(.opacity.combined(with: .move(edge: .leading)))
                            .animation(
                                .easeOut(duration: 0.3).delay(Double(index) * 0.05),
                                value: appeared
                            )
                    }
                }
                .listStyle(.plain)
            } else {
                content()
                    .onAppear {
                        appeared = true
                    }
            }
        }
    }
}

// MARK: - Pulse Animation
struct PulseAnimation: ViewModifier {
    @State private var isPulsing = false

    func body(content: Content) -> some View {
        content
            .scaleEffect(isPulsing ? 1.05 : 1.0)
            .opacity(isPulsing ? 0.8 : 1.0)
            .animation(
                .easeInOut(duration: 1.0).repeatForever(autoreverses: true),
                value: isPulsing
            )
            .onAppear {
                isPulsing = true
            }
    }
}

extension View {
    func pulseAnimation() -> some View {
        modifier(PulseAnimation())
    }
}

// MARK: - Preview
#Preview("Job Row Skeleton") {
    List {
        JobRowSkeleton()
        JobRowSkeleton()
        JobRowSkeleton()
    }
    .listStyle(.plain)
}

#Preview("Job Detail Skeleton") {
    JobDetailSkeleton()
}

#Preview("Host Card Skeleton") {
    VStack {
        HostCardSkeleton()
        HostCardSkeleton()
    }
    .padding()
}
