import Foundation
import Observation
import WidgetKit

enum AppTab: String, CaseIterable { case jobs, hosts, watchers, launch }
enum Route: Hashable {
  case job(JobID)
  case output(JobID)
  case host(String)
  case partition(String, String)
  case watcher(Int)
  case array(JobID)
}

@MainActor @Observable final class AppStore {
  let storage: LocalStorage
  var connection: Connection?
  var connections: [Connection] = []
  var hosts: [Host] = []
  var jobs: [Job] = []
  var arrays: [ArrayGroup] = []
  var partitions: [PartitionSnapshot] = []
  var watchers: [Watcher] = []
  var pins: Set<JobID> = []
  var acknowledgements: Set<JobID> = []
  var hostErrors: [String: String] = [:]
  var error: String?
  var watcherError: String?
  var receivedAt: Date?
  var refreshing = false
  var socketConnected = false
  var tab: AppTab = .jobs
  var jobPath: [Route] = []
  var hostPath: [Route] = []
  var watcherPath: [Route] = []
  var launchPath: [Route] = []
  var showSettings = false
  var notificationJob: JobID?
  var draftToOpen: LaunchDraft?
  var drafts: [SavedDraft] = []
  var refreshRevision = 0
  var widgetPrivacy = UserDefaults.standard.bool(forKey: "widgetPrivacy") {
    didSet {
      UserDefaults.standard.set(widgetPrivacy, forKey: "widgetPrivacy")
      publishSnapshot()
    }
  }
  @ObservationIgnored private var monitoring: Task<Void, Never>?
  @ObservationIgnored private var websocket: URLSessionWebSocketTask?
  @ObservationIgnored private var websocketTask: Task<Void, Never>?
  @ObservationIgnored private var refreshTask: Task<Void, Never>?
  @ObservationIgnored private var generation = UUID()

  var client: APIClient? {
    connection.flatMap {
      $0.demo ? nil : APIClient(connection: $0, apiKey: CredentialStore.read($0.id))
    }
  }
  var demo: Bool { connection?.demo == true }
  var sortedJobs: [Job] {
    jobs.sorted {
      $0.state.order == $1.state.order
        ? $0.number.localizedStandardCompare($1.number) == .orderedDescending
        : $0.state.order < $1.state.order
    }
  }
  var attentionJobs: [Job] {
    sortedJobs.filter { $0.state.needsAttention && !acknowledgements.contains($0.id) }
  }

  init(inMemory: Bool = false, demo: Bool = false) {
    do { storage = try LocalStorage(inMemory: inMemory) } catch {
      do { storage = try LocalStorage(inMemory: true) } catch {
        fatalError("Unable to create the local draft store: \(error.localizedDescription)")
      }
      self.error = "Local storage could not be opened. Drafts are temporary this session."
    }
    if let data = UserDefaults.standard.data(forKey: "connections"),
      let saved = try? JSONDecoder().decode([Connection].self, from: data)
    {
      connections = saved
    }
    if demo {
      select(.sample)
    } else if let id = UserDefaults.standard.string(forKey: "connection"),
      let saved = connections.first(where: { $0.id.uuidString == id })
    {
      select(saved)
    }
  }

  func connect(_ candidate: Connection, key: String) async throws {
    let api = APIClient(connection: candidate, apiKey: key)
    let verified = try await api.hosts()
    try CredentialStore.save(key, for: candidate.id)
    connections.removeAll { $0.id == candidate.id }
    connections.append(candidate)
    UserDefaults.standard.set(try JSONEncoder().encode(connections), forKey: "connections")
    select(candidate)
    hosts = verified
    await refresh()
    startMonitoring()
  }

  func select(_ selected: Connection) {
    stopMonitoring()
    generation = UUID()
    connection = selected
    UserDefaults.standard.set(selected.id.uuidString, forKey: "connection")
    jobs = []
    hosts = []
    partitions = []
    watchers = []
    arrays = []
    hostErrors = [:]
    pins = []
    acknowledgements = []
    receivedAt = nil
    error = nil
    watcherError = nil
    jobPath = []
    hostPath = []
    watcherPath = []
    launchPath = []
    draftToOpen = nil
    if selected.demo {
      hosts = DemoData.hosts
      jobs = DemoData.jobs
      partitions = DemoData.partitions
      watchers = DemoData.watchers
      receivedAt = .now
      pins = [JobID(host: "Atlas", number: "48192")]
    } else if let saved = storage.snapshot(selected.id) {
      hosts = saved.hosts
      jobs = saved.jobs
      partitions = saved.partitions
      watchers = saved.watchers
      arrays = saved.arrays
      receivedAt = saved.receivedAt
      pins = saved.pins
      acknowledgements = saved.acknowledgements
    }
    reloadDrafts()
    publishSnapshot()
  }

  func disconnect() {
    stopMonitoring()
    generation = UUID()
    connection = nil
    UserDefaults.standard.removeObject(forKey: "connection")
    jobs = []
    hosts = []
    partitions = []
    watchers = []
    arrays = []
    drafts = []
    pins = []
    receivedAt = nil
    jobPath = []
    hostPath = []
    watcherPath = []
    launchPath = []
    publishSnapshot()
  }

  func forget(_ saved: Connection) throws {
    if connection?.id == saved.id { disconnect() }
    try CredentialStore.save("", for: saved.id)
    storage.removeSnapshot(saved.id)
    storage.removeOutputs(connectionID: saved.id)
    for key in UserDefaults.standard.dictionaryRepresentation().keys
    where key.hasPrefix("bookmarks.\(saved.id.uuidString).") {
      UserDefaults.standard.removeObject(forKey: key)
    }
    for draft in storage.drafts(connectionID: saved.id) {
      try storage.deleteDraft(draft.id, connectionID: saved.id)
    }
    connections.removeAll { $0.id == saved.id }
    UserDefaults.standard.set(try JSONEncoder().encode(connections), forKey: "connections")
  }

  func refresh(force: Bool = false) async {
    guard !refreshing, let connection else { return }
    if connection.demo {
      receivedAt = .now
      return
    }
    guard let api = client else { return }
    refreshing = true
    let token = generation
    defer { if token == generation { refreshing = false } }
    async let hostsResult = Result { try await api.hosts() }
    async let jobsResult = Result { try await api.jobs(force: force) }
    async let partitionsResult = Result { try await api.partitions(force: force) }
    async let watchersResult = Result { try await api.watchers() }
    let results = await (hostsResult, jobsResult, partitionsResult, watchersResult)
    guard token == generation else { return }
    if case .success(let value) = results.0 { hosts = value }
    switch results.1 {
    case .success(let snapshots):
      hostErrors = [:]
      for snapshot in snapshots {
        if let message = snapshot.error {
          hostErrors[snapshot.hostname] = message
          continue
        }
        jobs.removeAll { $0.host == snapshot.hostname }
        jobs.append(contentsOf: snapshot.allJobs)
        arrays.removeAll { $0.hostname == snapshot.hostname }
        arrays.append(contentsOf: snapshot.array_groups ?? [])
      }
      receivedAt = .now
      error = nil
    case .failure(let failure): error = failure.localizedDescription
    }
    switch results.2 {
    case .success(let values): partitions = values
    case .failure(let failure):
      for index in partitions.indices {
        partitions[index].stale = true
        partitions[index].error = failure.localizedDescription
      }
    }
    switch results.3 {
    case .success(let response):
      watchers = response.watchers
      watcherError = nil
    case .failure(let failure): watcherError = failure.localizedDescription
    }
    refreshRevision += 1
    save()
    await LiveActivityService.shared.update(jobs: jobs, connection: connection)
  }

  func startMonitoring() {
    guard monitoring == nil, connection != nil else { return }
    Task { await NotificationService.shared.connect(api: client) }
    monitoring = Task { [weak self] in
      while !Task.isCancelled {
        await self?.refresh()
        do { try await Task.sleep(for: .seconds(30)) } catch { return }
      }
    }
    startSocket()
  }

  func stopMonitoring() {
    monitoring?.cancel()
    monitoring = nil
    websocketTask?.cancel()
    websocketTask = nil
    websocket?.cancel(with: .goingAway, reason: nil)
    websocket = nil
    socketConnected = false
    refreshing = false
  }

  private func startSocket() {
    guard let api = client else { return }
    let token = generation
    websocketTask = Task { [weak self] in
      while !Task.isCancelled {
        do {
          let socket = try api.socket()
          self?.websocket = socket
          socket.resume()
          while !Task.isCancelled {
            let message = try await socket.receive()
            guard let self, token == self.generation else { return }
            self.socketConnected = true
            let data: Data
            switch message {
            case .data(let value): data = value
            case .string(let value): data = Data(value.utf8)
            @unknown default: continue
            }
            if let value = try? JSONDecoder().decode(JSONValue.self, from: data) {
              self.consume(value)
            }
          }
        } catch {
          self?.socketConnected = false
          if Task.isCancelled { return }
          do { try await Task.sleep(for: .seconds(8)) } catch { return }
        }
      }
    }
  }

  private func consume(_ value: JSONValue) {
    let data = value.object
    var incoming: [Job] = []
    switch data.text("type") {
    case "initial":
      for (host, values) in data["jobs"]?.object ?? [:] {
        incoming += values.array.map { item in
          var fields = item.object
          fields["hostname"] = .string(host)
          return Job(fields)
        }
      }
    case "job_update", "state_change":
      var fields = data["job"]?.object ?? [:]
      if fields.text("hostname").isEmpty { fields["hostname"] = data["hostname"] }
      incoming = [Job(fields)]
    case "batch_update":
      incoming = (data["updates"]?.array ?? []).map {
        var fields = $0.object["job"]?.object ?? [:]
        if fields.text("hostname").isEmpty { fields["hostname"] = $0.object["hostname"] }
        return Job(fields)
      }
    default: return
    }
    for job in incoming where !job.host.isEmpty && !job.number.isEmpty {
      if let index = jobs.firstIndex(where: { $0.id == job.id }) {
        jobs[index] = job
      } else {
        jobs.append(job)
      }
    }
    if !incoming.isEmpty {
      receivedAt = .now
      save()
    }
  }

  func job(_ id: JobID) -> Job? { jobs.first { $0.id == id } }
  func upsert(_ job: Job) {
    if let index = jobs.firstIndex(where: { $0.id == job.id }) {
      jobs[index] = job
    } else {
      jobs.append(job)
    }
    save()
  }
  func togglePin(_ id: JobID) {
    if pins.contains(id) { pins.remove(id) } else { pins.insert(id) }
    save()
  }
  func acknowledge(_ id: JobID) {
    acknowledgements.insert(id)
    save()
  }

  func cancel(_ id: JobID) async throws {
    if demo {
      if let index = jobs.firstIndex(where: { $0.id == id }) {
        jobs[index].fields["state"] = .string("CA")
      }
    } else {
      try await client?.cancel(id)
      await refresh(force: true)
    }
    save()
  }
  func watcherAction(_ watcher: Watcher, action: String) async throws {
    if demo {
      if action == "delete" {
        watchers.removeAll { $0.id == watcher.id }
      } else if let index = watchers.firstIndex(where: { $0.id == watcher.id }) {
        watchers[index].fields["state"] = .string(action == "pause" ? "paused" : "active")
      }
    } else {
      let path =
        action == "delete" ? "api/watchers/\(watcher.id)" : "api/watchers/\(watcher.id)/\(action)"
      try await client?.perform(path, method: action == "delete" ? "DELETE" : "POST")
      await refresh()
    }
    save()
  }
  func reloadDrafts() { drafts = connection.map { storage.drafts(connectionID: $0.id) } ?? [] }
  func saveDraft(_ draft: LaunchDraft, for connectionID: UUID? = nil, template: Bool = false) throws
  {
    guard let id = connectionID ?? connection?.id else { return }
    try storage.saveDraft(draft, connectionID: id, template: template)
    reloadDrafts()
  }
  func openDraft(_ draft: LaunchDraft) {
    draftToOpen = draft
    tab = .launch
  }
  func handleNotification(_ url: URL) {
    guard let parts = URLComponents(url: url, resolvingAgainstBaseURL: false),
      let host = parts.queryItems?.first(where: { $0.name == "host" })?.value,
      let number = parts.queryItems?.first(where: { $0.name == "id" })?.value
    else { return }
    showSettings = false
    if connections.count == 1, let only = connections.first {
      if connection?.id != only.id {
        select(only)
        startMonitoring()
      }
      handle(url)
    } else {
      // Current APNs payloads identify a host and job, but not a server.
      // Never open a same-numbered job on an arbitrary saved connection.
      notificationJob = JobID(host: host, number: number)
    }
  }
  func handle(_ url: URL) {
    guard url.scheme == "ssync", let parts = URLComponents(url: url, resolvingAgainstBaseURL: false)
    else { return }
    let query = Dictionary(
      parts.queryItems?.map { ($0.name, $0.value ?? "") } ?? [],
      uniquingKeysWith: { _, last in last })
    if let id = query["connection"], connection?.id.uuidString != id {
      guard let target = connections.first(where: { $0.id.uuidString == id }) else {
        error = "Connect to the server associated with this link."
        return
      }
      select(target)
      startMonitoring()
    }
    switch url.host {
    case "job":
      guard let host = query["host"], let number = query["id"], !host.isEmpty, !number.isEmpty
      else { return }
      tab = .jobs
      jobPath = [.job(JobID(host: host, number: number))]
    case "host":
      if let host = query["name"] {
        tab = .hosts
        hostPath = [.host(host)]
      }
    case "launch": tab = .launch
    default: tab = .jobs
    }
  }
  func save() {
    guard let connection else { return }
    if !connection.demo {
      do {
        try storage.save(
          SavedSession(
            connection: connection, hosts: hosts, jobs: jobs, partitions: partitions,
            watchers: watchers, arrays: arrays, receivedAt: receivedAt, pins: pins,
            acknowledgements: acknowledgements))
      } catch { self.error = "Could not save the offline snapshot: \(error.localizedDescription)" }
    }
    publishSnapshot()
  }
  private func publishSnapshot() {
    let value: SystemSnapshot
    if widgetPrivacy || connection == nil {
      value = .empty
    } else {
      value = SystemSnapshot(
        connectionID: connection?.id, name: demo ? "Demo · Sample data" : connection!.name,
        updatedAt: receivedAt,
        running: jobs.filter { $0.state == .running }.count,
        pending: jobs.filter { $0.state == .pending }.count, attention: attentionJobs.count,
        jobs: sortedJobs.map {
          SystemJob(
            host: $0.host, number: $0.number, name: $0.name, state: $0.state.label,
            runtime: Format.duration($0.runtime), pinned: pins.contains($0.id))
        },
        partitions: partitions.flatMap { snapshot in
          snapshot.partitions.map {
            SystemPartition(
              host: snapshot.hostname, name: $0.partition, allocated: $0.cpus_alloc,
              idle: $0.cpus_idle, other: $0.cpus_other, total: $0.cpus_total,
              updatedAt: snapshot.observedAt)
          }
        })
    }
    try? value.write()
    WidgetCenter.shared.reloadAllTimelines()
  }
}

extension Result where Failure == any Error {
  init(catching operation: () async throws -> Success) async {
    do { self = .success(try await operation()) } catch { self = .failure(error) }
  }
}
