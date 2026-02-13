import SwiftUI

// MARK: - Onboarding View
struct OnboardingView: View {
    @Binding var isPresented: Bool
    @State private var currentPage = 0
    @State private var serverURL = "https://localhost:8042"
    @State private var apiKey = ""
    @State private var isConnecting = false
    @State private var connectionError: String?

    let pages: [OnboardingPage] = [
        OnboardingPage(
            title: "Welcome to\nSLURM Manager",
            subtitle: "Monitor and manage your HPC jobs from anywhere",
            icon: "server.rack",
            color: .blue
        ),
        OnboardingPage(
            title: "Real-time Updates",
            subtitle: "Watch your jobs run with live status updates and output streaming",
            icon: "bolt.fill",
            color: .orange
        ),
        OnboardingPage(
            title: "Launch Jobs",
            subtitle: "Submit new jobs directly from your phone with full resource configuration",
            icon: "play.circle.fill",
            color: .green
        ),
        OnboardingPage(
            title: "Stay Notified",
            subtitle: "Get notified when jobs complete, fail, or need attention",
            icon: "bell.badge.fill",
            color: .purple
        )
    ]

    var body: some View {
        VStack(spacing: 0) {
            // Page content
            TabView(selection: $currentPage) {
                ForEach(0..<pages.count, id: \.self) { index in
                    pageView(pages[index])
                        .tag(index)
                }

                // Setup page
                setupView
                    .tag(pages.count)
            }
            .tabViewStyle(.page(indexDisplayMode: .never))
            .animation(.easeInOut, value: currentPage)

            // Page indicator and navigation
            bottomNavigation
        }
        .background(Color(.systemBackground))
    }

    // MARK: - Page View
    func pageView(_ page: OnboardingPage) -> some View {
        VStack(spacing: 40) {
            Spacer()

            // Icon
            ZStack {
                Circle()
                    .fill(page.color.opacity(0.15))
                    .frame(width: 160, height: 160)

                Circle()
                    .fill(page.color.opacity(0.1))
                    .frame(width: 120, height: 120)

                Image(systemName: page.icon)
                    .font(.system(size: 56))
                    .foregroundColor(page.color)
            }

            VStack(spacing: 16) {
                Text(page.title)
                    .font(.largeTitle)
                    .fontWeight(.bold)
                    .multilineTextAlignment(.center)

                Text(page.subtitle)
                    .font(.body)
                    .foregroundColor(.secondary)
                    .multilineTextAlignment(.center)
                    .padding(.horizontal, 32)
            }

            Spacer()
            Spacer()
        }
    }

    // MARK: - Setup View
    var setupView: some View {
        ScrollView {
            VStack(spacing: 32) {
                // Header
                VStack(spacing: 16) {
                    Image(systemName: "link.circle.fill")
                        .font(.system(size: 64))
                        .foregroundColor(.blue)

                    Text("Connect to Server")
                        .font(.title)
                        .fontWeight(.bold)

                    Text("Enter your ssync server details to get started")
                        .font(.body)
                        .foregroundColor(.secondary)
                        .multilineTextAlignment(.center)
                        .padding(.horizontal)
                }
                .padding(.top, 40)

                // Form
                VStack(spacing: 20) {
                    // Server URL
                    VStack(alignment: .leading, spacing: 8) {
                        Label("Server URL", systemImage: "globe")
                            .font(.subheadline)
                            .foregroundColor(.secondary)

                        TextField("https://example.com:8042", text: $serverURL)
                            .textFieldStyle(.plain)
                            .keyboardType(.URL)
                            .autocapitalization(.none)
                            .disableAutocorrection(true)
                            .padding()
                            .background(Color(.systemGray6))
                            .cornerRadius(10)
                    }

                    // API Key
                    VStack(alignment: .leading, spacing: 8) {
                        Label("API Key", systemImage: "key.fill")
                            .font(.subheadline)
                            .foregroundColor(.secondary)

                        SecureField("Enter your API key", text: $apiKey)
                            .textFieldStyle(.plain)
                            .autocapitalization(.none)
                            .disableAutocorrection(true)
                            .padding()
                            .background(Color(.systemGray6))
                            .cornerRadius(10)
                    }

                    // Help text
                    HStack {
                        Image(systemName: "info.circle")
                            .font(.caption)
                        Text("Run `ssync auth create-key` on your server to generate an API key")
                            .font(.caption)
                    }
                    .foregroundColor(.secondary)
                    .padding(.horizontal)

                    // Error message
                    if let error = connectionError {
                        HStack {
                            Image(systemName: "exclamationmark.triangle.fill")
                                .foregroundColor(.red)
                            Text(error)
                                .font(.caption)
                                .foregroundColor(.red)
                        }
                        .padding()
                        .background(Color.red.opacity(0.1))
                        .cornerRadius(8)
                    }
                }
                .padding(.horizontal, 24)

                Spacer(minLength: 100)
            }
        }
    }

    // MARK: - Bottom Navigation
    var bottomNavigation: some View {
        VStack(spacing: 20) {
            // Page indicators
            HStack(spacing: 8) {
                ForEach(0..<pages.count + 1, id: \.self) { index in
                    Circle()
                        .fill(currentPage == index ? Color.blue : Color.gray.opacity(0.3))
                        .frame(width: 8, height: 8)
                        .animation(.easeInOut, value: currentPage)
                }
            }

            // Buttons
            HStack(spacing: 16) {
                // Skip/Back button
                if currentPage > 0 {
                    Button(action: {
                        withAnimation {
                            currentPage -= 1
                        }
                    }) {
                        Text("Back")
                            .fontWeight(.medium)
                            .frame(maxWidth: .infinity)
                            .padding()
                            .background(Color(.systemGray6))
                            .foregroundColor(.primary)
                            .cornerRadius(12)
                    }
                } else {
                    Button(action: {
                        withAnimation {
                            currentPage = pages.count // Skip to setup
                        }
                    }) {
                        Text("Skip")
                            .fontWeight(.medium)
                            .frame(maxWidth: .infinity)
                            .padding()
                            .background(Color(.systemGray6))
                            .foregroundColor(.primary)
                            .cornerRadius(12)
                    }
                }

                // Next/Connect button
                Button(action: {
                    if currentPage < pages.count {
                        withAnimation {
                            currentPage += 1
                        }
                    } else {
                        connect()
                    }
                }) {
                    HStack {
                        if isConnecting {
                            ProgressView()
                                .progressViewStyle(CircularProgressViewStyle(tint: .white))
                                .scaleEffect(0.8)
                        } else {
                            Text(currentPage == pages.count ? "Connect" : "Next")
                                .fontWeight(.semibold)

                            if currentPage < pages.count {
                                Image(systemName: "arrow.right")
                            }
                        }
                    }
                    .frame(maxWidth: .infinity)
                    .padding()
                    .background(canConnect ? Color.blue : Color.gray)
                    .foregroundColor(.white)
                    .cornerRadius(12)
                }
                .disabled(currentPage == pages.count && !canConnect)
            }
            .padding(.horizontal, 24)
        }
        .padding(.vertical, 24)
        .background(Color(.systemBackground))
    }

    // MARK: - Helper Properties
    var canConnect: Bool {
        currentPage < pages.count ||
        (!serverURL.isEmpty && !apiKey.isEmpty && !isConnecting)
    }

    // MARK: - Actions
    func connect() {
        guard !serverURL.isEmpty, !apiKey.isEmpty else { return }

        isConnecting = true
        connectionError = nil

        // Store credentials
        AuthenticationManager.shared.serverURL = serverURL
        AuthenticationManager.shared.apiKey = apiKey

        // Test connection
        AuthenticationManager.shared.testConnection { success, error in
            DispatchQueue.main.async {
                isConnecting = false

                if success {
                    // Save credentials
                    if AuthenticationManager.shared.saveCredentials() {
                        HapticManager.notification(.success)

                        // Mark onboarding as complete
                        UserDefaults.standard.set(true, forKey: "hasCompletedOnboarding")

                        withAnimation {
                            isPresented = false
                        }
                    } else {
                        connectionError = "Failed to save credentials"
                        HapticManager.notification(.error)
                    }
                } else {
                    connectionError = error ?? "Failed to connect to server"
                    HapticManager.notification(.error)
                }
            }
        }
    }
}

// MARK: - Onboarding Page Model
struct OnboardingPage {
    let title: String
    let subtitle: String
    let icon: String
    let color: Color
}

// MARK: - Feature Highlight View (for What's New)
struct FeatureHighlightView: View {
    @Environment(\.dismiss) var dismiss
    let features: [Feature]

    var body: some View {
        NavigationView {
            ScrollView {
                VStack(spacing: 24) {
                    // Header
                    VStack(spacing: 12) {
                        Image(systemName: "sparkles")
                            .font(.system(size: 48))
                            .foregroundColor(.blue)

                        Text("What's New")
                            .font(.largeTitle)
                            .fontWeight(.bold)

                        Text("in SLURM Manager")
                            .font(.title3)
                            .foregroundColor(.secondary)
                    }
                    .padding(.top, 20)

                    // Features
                    VStack(spacing: 20) {
                        ForEach(features) { feature in
                            FeatureRow(feature: feature)
                        }
                    }
                    .padding(.horizontal)

                    Spacer(minLength: 40)
                }
            }
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .navigationBarTrailing) {
                    Button("Done") {
                        dismiss()
                    }
                    .fontWeight(.semibold)
                }
            }
        }
    }
}

struct Feature: Identifiable {
    let id = UUID()
    let icon: String
    let title: String
    let description: String
    let color: Color
}

struct FeatureRow: View {
    let feature: Feature

    var body: some View {
        HStack(alignment: .top, spacing: 16) {
            ZStack {
                Circle()
                    .fill(feature.color.opacity(0.15))
                    .frame(width: 50, height: 50)

                Image(systemName: feature.icon)
                    .font(.title3)
                    .foregroundColor(feature.color)
            }

            VStack(alignment: .leading, spacing: 4) {
                Text(feature.title)
                    .font(.headline)

                Text(feature.description)
                    .font(.subheadline)
                    .foregroundColor(.secondary)
            }

            Spacer()
        }
        .padding()
        .background(Color(.secondarySystemGroupedBackground))
        .cornerRadius(12)
    }
}

// MARK: - Preview
#Preview("Onboarding") {
    OnboardingView(isPresented: .constant(true))
}

#Preview("What's New") {
    FeatureHighlightView(features: [
        Feature(
            icon: "hand.draw.fill",
            title: "Swipe Actions",
            description: "Swipe on jobs to quickly cancel, refresh, or view output",
            color: .blue
        ),
        Feature(
            icon: "bolt.fill",
            title: "Faster Loading",
            description: "Improved caching for instant job list display",
            color: .orange
        ),
        Feature(
            icon: "waveform.path.ecg",
            title: "Live Output",
            description: "Watch job output in real-time as it runs",
            color: .green
        )
    ])
}
