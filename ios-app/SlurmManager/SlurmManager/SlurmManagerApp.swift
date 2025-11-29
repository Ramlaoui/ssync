import SwiftUI

@main
struct SlurmManagerApp: App {
    @UIApplicationDelegateAdaptor(AppDelegate.self) var appDelegate
    @StateObject private var authManager = AuthenticationManager.shared
    @StateObject private var appState = AppState.shared

    @State private var showOnboarding = false
    @AppStorage("hasCompletedOnboarding") private var hasCompletedOnboarding = false
    @AppStorage("preferredColorScheme") private var preferredColorScheme = 0

    var body: some Scene {
        WindowGroup {
            ZStack {
                // Main content
                if authManager.isAuthenticated {
                    MainTabView()
                        .environmentObject(authManager)
                        .environmentObject(appState)
                        .overlay(alignment: .top) {
                            ConnectionStatusBar()
                        }
                } else {
                    AuthenticationView()
                        .environmentObject(authManager)
                }

                // Toast overlay
                ToastOverlay()
            }
            .preferredColorScheme(colorScheme)
            .fullScreenCover(isPresented: $showOnboarding) {
                OnboardingView(isPresented: $showOnboarding)
            }
            .onAppear {
                setupApp()
            }
        }
    }

    var colorScheme: ColorScheme? {
        switch preferredColorScheme {
        case 1: return .light
        case 2: return .dark
        default: return nil
        }
    }

    private func setupApp() {
        // Configure app on launch
        authManager.loadStoredCredentials()

        // Show onboarding for first-time users
        if !hasCompletedOnboarding && !authManager.isAuthenticated {
            showOnboarding = true
        }

        // Setup notification handlers
        NotificationManager.shared.requestAuthorization()
        NotificationManager.shared.setupNotificationCategories()

        // Start WebSocket connection if authenticated
        if authManager.isAuthenticated {
            WebSocketManager.shared.connect()

            // Preload cache
            Task {
                await CacheManager.shared.pruneExpired()
            }
        }
    }
}

// MARK: - App Delegate for Quick Actions
class AppDelegate: NSObject, UIApplicationDelegate {
    func application(
        _ application: UIApplication,
        didFinishLaunchingWithOptions launchOptions: [UIApplication.LaunchOptionsKey: Any]? = nil
    ) -> Bool {
        // Setup Quick Actions
        setupQuickActions()
        return true
    }

    func application(
        _ application: UIApplication,
        configurationForConnecting connectingSceneSession: UISceneSession,
        options: UIScene.ConnectionOptions
    ) -> UISceneConfiguration {
        // Handle Quick Action if app was launched via one
        if let shortcutItem = options.shortcutItem {
            handleQuickAction(shortcutItem)
        }

        return UISceneConfiguration(
            name: "Default Configuration",
            sessionRole: connectingSceneSession.role
        )
    }

    func setupQuickActions() {
        UIApplication.shared.shortcutItems = [
            UIApplicationShortcutItem(
                type: "com.slurmmanager.viewJobs",
                localizedTitle: "View Jobs",
                localizedSubtitle: "See all running jobs",
                icon: UIApplicationShortcutIcon(systemImageName: "list.bullet.rectangle"),
                userInfo: nil
            ),
            UIApplicationShortcutItem(
                type: "com.slurmmanager.launchJob",
                localizedTitle: "Launch Job",
                localizedSubtitle: "Submit a new job",
                icon: UIApplicationShortcutIcon(systemImageName: "play.circle.fill"),
                userInfo: nil
            ),
            UIApplicationShortcutItem(
                type: "com.slurmmanager.refresh",
                localizedTitle: "Refresh",
                localizedSubtitle: "Update job status",
                icon: UIApplicationShortcutIcon(systemImageName: "arrow.clockwise"),
                userInfo: nil
            )
        ]
    }

    func handleQuickAction(_ shortcutItem: UIApplicationShortcutItem) {
        switch shortcutItem.type {
        case "com.slurmmanager.viewJobs":
            QuickActionManager.shared.pendingAction = .viewJobs
        case "com.slurmmanager.launchJob":
            QuickActionManager.shared.pendingAction = .launchJob
        case "com.slurmmanager.refresh":
            QuickActionManager.shared.pendingAction = .refresh
        default:
            break
        }
    }

    func applicationWillResignActive(_ application: UIApplication) {
        // Update dynamic shortcuts based on current state
        updateDynamicShortcuts()
    }

    func updateDynamicShortcuts() {
        Task {
            let cachedJobs = await CacheManager.shared.getAllJobs()
            let runningCount = cachedJobs.filter { $0.state == .running }.count

            await MainActor.run {
                var shortcuts = UIApplication.shared.shortcutItems ?? []

                // Update or add running jobs shortcut
                if runningCount > 0 {
                    let runningShortcut = UIApplicationShortcutItem(
                        type: "com.slurmmanager.runningJobs",
                        localizedTitle: "Running Jobs",
                        localizedSubtitle: "\(runningCount) jobs running",
                        icon: UIApplicationShortcutIcon(systemImageName: "play.fill"),
                        userInfo: nil
                    )

                    if let index = shortcuts.firstIndex(where: { $0.type == "com.slurmmanager.runningJobs" }) {
                        shortcuts[index] = runningShortcut
                    } else if shortcuts.count < 4 {
                        shortcuts.append(runningShortcut)
                    }

                    UIApplication.shared.shortcutItems = shortcuts
                }
            }
        }
    }
}

// MARK: - Quick Action Manager
class QuickActionManager: ObservableObject {
    static let shared = QuickActionManager()

    enum QuickAction {
        case viewJobs
        case launchJob
        case refresh
        case runningJobs
    }

    @Published var pendingAction: QuickAction?
}

// MARK: - Main Tab View
struct MainTabView: View {
    @State private var selectedTab = 0
    @StateObject private var quickActionManager = QuickActionManager.shared
    @State private var showLaunchJob = false

    var body: some View {
        TabView(selection: $selectedTab) {
            // Jobs Tab
            NavigationView {
                JobListView()
            }
            .tabItem {
                Label("Jobs", systemImage: "list.bullet.rectangle")
            }
            .tag(0)

            // Hosts Tab
            NavigationView {
                HostsView()
            }
            .tabItem {
                Label("Hosts", systemImage: "server.rack")
            }
            .tag(1)

            // Launch Tab (opens sheet)
            Text("")
                .tabItem {
                    Label("Launch", systemImage: "plus.circle.fill")
                }
                .tag(2)

            // Settings Tab
            SettingsView()
                .tabItem {
                    Label("Settings", systemImage: "gearshape")
                }
                .tag(3)
        }
        .onChange(of: selectedTab) { newTab in
            if newTab == 2 {
                // Reset to previous tab and show launch sheet
                selectedTab = 0
                showLaunchJob = true
            }
        }
        .onChange(of: quickActionManager.pendingAction) { action in
            handleQuickAction(action)
        }
        .sheet(isPresented: $showLaunchJob) {
            LaunchJobView()
        }
        .onAppear {
            // Check for pending quick action
            if let action = quickActionManager.pendingAction {
                handleQuickAction(action)
            }
        }
    }

    func handleQuickAction(_ action: QuickAction?) {
        guard let action = action else { return }

        DispatchQueue.main.async {
            switch action {
            case .viewJobs, .runningJobs:
                selectedTab = 0
            case .launchJob:
                selectedTab = 0
                showLaunchJob = true
            case .refresh:
                // Trigger refresh in JobListView
                NotificationCenter.default.post(name: .refreshJobs, object: nil)
            }

            // Clear the action
            quickActionManager.pendingAction = nil
        }
    }
}

// MARK: - Toast Overlay
struct ToastOverlay: View {
    @StateObject private var toastManager = ToastManager.shared

    var body: some View {
        VStack {
            Spacer()

            if let toast = toastManager.currentToast {
                ToastView(
                    message: toast.message,
                    type: toast.type
                )
                .transition(.move(edge: .bottom).combined(with: .opacity))
                .padding(.bottom, 100)
            }
        }
        .animation(.spring(), value: toastManager.currentToast?.id)
    }
}

// MARK: - Notification Names
extension Notification.Name {
    static let refreshJobs = Notification.Name("refreshJobs")
    static let navigateToJob = Notification.Name("navigateToJob")
}
