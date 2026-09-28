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
          Tab("Jobs", systemImage: "list.bullet.rectangle", value: .jobs) {
            NavigationStack(path: $store.jobPath) { JobsView().appDestinations() }
          }
          Tab("Cluster", systemImage: "server.rack", value: .cluster) {
            NavigationStack(path: $store.clusterPath) { ClusterView().appDestinations() }
          }
          Tab("Activity", systemImage: "bolt.horizontal", value: .activity) {
            NavigationStack(path: $store.activityPath) { ActivityView().appDestinations() }
          }
        }
        .sheet(isPresented: $store.showSettings) { NavigationStack { SettingsView() } }
        .sheet(isPresented: $store.addingConnection) { ConnectionView(adding: true) }
        .sheet(item: $store.launch) { request in
          if let connection = store.connection {
            LaunchFlow(initial: request.draft, connectionID: connection.id)
          }
        }
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
      case .history: JobHistoryView()
      }
    }
  }
  func rootToolbar() -> some View { modifier(RootToolbar()) }
}
/// Every root screen shares the server menu (switch, add, settings) and the launch entry point.
struct RootToolbar: ViewModifier {
  @Environment(AppStore.self) private var store
  func body(content: Content) -> some View {
    content
      .navigationSubtitle(subtitle)
      .toolbar {
        ToolbarItem(placement: .topBarLeading) { ServerMenu() }
        ToolbarItem(placement: .topBarTrailing) {
          Button("New launch", systemImage: "plus") { store.openDraft() }
            .accessibilityIdentifier("newLaunch")
        }
      }
  }
  private var subtitle: String {
    guard let connection = store.connection else { return "" }
    if connection.demo { return "Demo · sample data" }
    if store.error != nil { return "\(connection.name) · offline" }
    return connection.name
  }
}
struct ServerMenu: View {
  @Environment(AppStore.self) private var store
  var body: some View {
    Menu {
      Section(store.connection?.demo == true ? "Demo workspace" : "Servers") {
        ForEach(store.connections) { connection in
          Button {
            guard connection.id != store.connection?.id else { return }
            store.select(connection)
            store.startMonitoring()
          } label: {
            if connection.id == store.connection?.id {
              Label(connection.name, systemImage: "checkmark")
            } else {
              Text(connection.name)
            }
          }
        }
        Button("Add server…", systemImage: "plus") { store.addingConnection = true }
      }
      Button("Settings", systemImage: "gearshape") { store.showSettings = true }
    } label: {
      Label("Servers and settings", systemImage: "person.crop.circle")
    }
    .accessibilityIdentifier("settings")
  }
}
/// A single, quiet line that only appears when the data is not live.
struct ConnectionBanner: View {
  @Environment(AppStore.self) private var store
  var body: some View {
    if let error = store.error, !store.demo {
      Label {
        VStack(alignment: .leading, spacing: 2) {
          Text("Showing saved data · \(Format.age(store.receivedAt).lowercased())")
            .font(.subheadline.weight(.semibold))
          Text(error).font(.caption).foregroundStyle(.secondary).lineLimit(2)
        }
      } icon: {
        Image(systemName: "wifi.slash").foregroundStyle(Theme.amber)
      }
    }
  }
}
