import SwiftUI

@main struct SsyncApp: App {
  @UIApplicationDelegateAdaptor(NotificationDelegate.self) private var delegate
  @State private var store = AppStore(demo: ProcessInfo.processInfo.arguments.contains("--demo"))
  @Environment(\.scenePhase) private var phase
  var body: some Scene {
    WindowGroup {
      AppRoot().environment(store).tint(Theme.accent)
        .onOpenURL { store.handle($0) }
        .onReceive(NotificationCenter.default.publisher(for: .ssyncDeepLink)) { notification in
          if let url = notification.object as? URL { store.handle(url) }
        }
        .task { store.startMonitoring() }
        .onChange(of: phase) { _, phase in
          if phase == .active { store.startMonitoring() } else { store.stopMonitoring() }
        }
    }
  }
}

struct AppRoot: View {
  @Environment(AppStore.self) private var store
  @State private var notifications = NotificationService.shared
  var body: some View {
    @Bindable var store = store
    Group {
      if store.connection == nil {
        ConnectionView()
      } else {
        TabView(selection: $store.tab) {
          Tab("Jobs", systemImage: "square.stack.3d.up", value: .jobs) {
            NavigationStack(path: $store.jobPath) { JobsView().appDestinations() }
          }
          Tab("Hosts", systemImage: "server.rack", value: .hosts) {
            NavigationStack(path: $store.hostPath) { HostsView().appDestinations() }
          }
          Tab("Watchers", systemImage: "eye", value: .watchers) {
            NavigationStack(path: $store.watcherPath) { WatchersView().appDestinations() }
          }
          Tab("Launch", systemImage: "arrow.up.right", value: .launch) {
            NavigationStack(path: $store.launchPath) { LaunchLibraryView().appDestinations() }
          }
        }
        .sheet(isPresented: $store.showSettings) { NavigationStack { SettingsView() } }
      }
    }
    .onChange(of: notifications.pendingURL) { _, url in
      if let url {
        store.handleNotification(url)
        notifications.pendingURL = nil
      }
    }
    .task {
      if let url = notifications.pendingURL {
        store.handleNotification(url)
        notifications.pendingURL = nil
      }
    }
    .sheet(item: $store.notificationJob) { id in
      NavigationStack {
        List {
          Section {
            Text("Choose the server for \(id.host) / #\(id.number).")
            ForEach(store.connections) { connection in
              Button(connection.name) {
                store.select(connection)
                store.startMonitoring()
                store.notificationJob = nil
                store.handle(
                  SystemJob(
                    host: id.host, number: id.number, name: "", state: "", runtime: "",
                    pinned: false
                  ).url(connection: connection.id))
              }
            }
            if store.connections.isEmpty {
              Text("Connect your ssync server first, then open the notification again.")
                .foregroundStyle(.secondary)
            }
          }
        }.navigationTitle("Open job").toolbar { Button("Close") { store.notificationJob = nil } }
      }.presentationDetents([.medium])
    }
  }
}

extension View {
  func appDestinations() -> some View {
    navigationDestination(for: Route.self) { route in
      switch route {
      case .job(let id): JobDetailView(id: id)
      case .output(let id): OutputView(id: id)
      case .host(let name): HostDetailView(host: name)
      case .partition(let host, let name): PartitionDetailView(host: host, name: name)
      case .watcher(let id): WatcherDetailView(id: id)
      case .array(let id): ArrayDetailView(id: id)
      }
    }
  }
  func rootToolbar() -> some View { modifier(RootToolbar()) }
}
struct RootToolbar: ViewModifier {
  @Environment(AppStore.self) private var store
  func body(content: Content) -> some View {
    content.toolbar {
      ToolbarItem(placement: .topBarLeading) {
        HStack(spacing: 5) {
          RelayMark(size: 27)
          Text("ssync").font(.system(.title3, design: .rounded).weight(.bold))
        }
        .fixedSize()
        .padding(.horizontal, 4)
        .accessibilityElement(children: .ignore)
        .accessibilityLabel("ssync")
      }
      .sharedBackgroundVisibility(.hidden)
      ToolbarItem(placement: .topBarTrailing) {
        Button("Settings", systemImage: "gearshape") { store.showSettings = true }
          .accessibilityIdentifier("settings")
      }
    }
  }
}
struct ConnectionStatus: View {
  @Environment(AppStore.self) private var store
  var body: some View {
    if store.demo {
      Notice(
        title: "Demo workspace",
        detail: "Sample jobs and capacity. Actions here do not affect a cluster.",
        symbol: "sparkles")
    } else if let error = store.error {
      Notice(title: "Showing saved data", detail: error, symbol: "wifi.slash", warning: true)
    } else {
      HStack(spacing: 6) {
        Circle().fill(store.socketConnected ? Theme.green : Theme.secondary).frame(
          width: 6, height: 6)
        Text(store.socketConnected ? "Connected" : "Checking every 30 seconds")
        Spacer()
        TimelineView(.periodic(from: .now, by: 30)) { _ in Text(Format.age(store.receivedAt)) }
      }.font(.caption).foregroundStyle(Theme.secondary)
    }
  }
}
