import SwiftUI

enum JobFilter: Hashable { case running, queued, failed }

struct JobsView: View {
  @Environment(AppStore.self) private var store
  @State private var query = ""
  @State private var filter: JobFilter?
  @State private var host: String?
  private let recentLimit = 8

  private var scoped: [Job] {
    store.listedJobs.filter { job in
      (host == nil || job.host == host)
        && (query.isEmpty
          || "\(job.name) \(job.number) \(job.host) \(job.partition) \(job.user)"
            .localizedCaseInsensitiveContains(query))
    }
  }
  private var scopedArrays: [ArrayGroup] {
    store.arrays.filter { group in
      (host == nil || group.hostname == host)
        && (query.isEmpty
          || "\(group.job_name) \(group.array_job_id) \(group.hostname)"
            .localizedCaseInsensitiveContains(query))
    }
  }
  var body: some View {
    let jobs = scoped
    let arrays = scopedArrays
    let pinned = jobs.filter { store.pins.contains($0.id) }
    let rest = jobs.filter { !store.pins.contains($0.id) }
    let running = rest.filter { $0.state == .running }
    let queued = rest.filter { $0.state == .pending }
    let recent = rest.filter { !$0.state.active }
    let runningArrays = arrays.filter { $0.running_count > 0 }
    let queuedArrays = arrays.filter { $0.running_count == 0 && $0.pending_count > 0 }
    List {
      if store.error != nil && !store.demo { ConnectionBanner() }
      Section {
        chips(jobs: jobs, arrays: arrays)
          .listRowInsets(EdgeInsets(top: 4, leading: 0, bottom: 4, trailing: 0))
          .listRowBackground(Color.clear)
      }
      if let filter {
        let filtered = jobs.filter { matches($0, filter) }
        let filteredArrays =
          filter == .running ? runningArrays : filter == .queued ? queuedArrays : []
        Section {
          CappedRows(items: entries(filteredArrays, filtered), limit: 25) { row($0) }
        }
      } else {
        if !pinned.isEmpty {
          CollapsibleSection("Pinned", detail: "\(pinned.count)", key: "jobs.pinned") {
            CappedRows(items: entries([], pinned)) { row($0) }
          }
        }
        if !running.isEmpty || !runningArrays.isEmpty {
          CollapsibleSection(
            "Running", detail: "\(running.count + runningArrays.count)", key: "jobs.running"
          ) {
            CappedRows(items: entries(runningArrays, running)) { row($0) }
          }
        }
        if !queued.isEmpty || !queuedArrays.isEmpty {
          CollapsibleSection(
            "Queued", detail: "\(queued.count + queuedArrays.count)", key: "jobs.queued"
          ) {
            CappedRows(items: entries(queuedArrays, queued), limit: 5) { row($0) }
          }
        }
        CollapsibleSection("Recent", key: "jobs.recent") {
          ForEach(recent.prefix(recentLimit)) { jobLink($0) }
          NavigationLink(value: Route.history) {
            Label("All history", systemImage: "clock.arrow.circlepath")
          }
        } footer: {
          Text(
            "Last 7 days · up to 1,000 jobs per host · updated \(Format.age(store.receivedAt).lowercased())"
          )
        }
      }
    }
    .overlay {
      if jobs.isEmpty && arrays.isEmpty {
        if query.isEmpty {
          ContentUnavailableView(
            "No jobs", systemImage: "list.bullet.rectangle",
            description: Text("Jobs you submit on a connected host appear here."))
        } else {
          ContentUnavailableView.search(text: query)
        }
      }
    }
    .animation(.default, value: filter)
    .navigationTitle("Jobs")
    .rootToolbar()
    .toolbar {
      if store.hosts.count > 1 {
        ToolbarItem(placement: .topBarTrailing) {
          Menu {
            Picker("Host", selection: $host) {
              Text("All hosts").tag(String?.none)
              ForEach(store.hosts) { Text($0.hostname).tag(Optional($0.hostname)) }
            }
          } label: {
            Label(
              host ?? "All hosts",
              systemImage: host == nil
                ? "line.3.horizontal.decrease" : "line.3.horizontal.decrease.circle.fill")
          }
        }
      }
    }
    .searchable(text: $query, prompt: "Name, ID, host or partition")
    .searchToolbarBehavior(.minimize)
    .refreshable { await store.refresh(force: true) }
  }

  private func chips(jobs: [Job], arrays: [ArrayGroup]) -> some View {
    ScrollView(.horizontal) {
      HStack(spacing: 8) {
        chip(
          "Running", .running,
          count: jobs.filter { $0.state == .running }.count
            + arrays.filter { $0.running_count > 0 }.count, color: Theme.accent)
        chip(
          "Queued", .queued,
          count: jobs.filter { $0.state == .pending }.count
            + arrays.filter { $0.running_count == 0 && $0.pending_count > 0 }.count,
          color: Theme.amber)
        chip("Failed", .failed, count: jobs.filter(\.state.isFailure).count, color: Theme.red)
      }.padding(.horizontal, 20)
    }.scrollIndicators(.hidden)
  }
  private func chip(_ title: String, _ value: JobFilter, count: Int, color: Color) -> some View {
    FilterChip(title: title, count: count, color: color, selected: filter == value) {
      filter = filter == value ? nil : value
    }
  }
  private func matches(_ job: Job, _ filter: JobFilter) -> Bool {
    switch filter {
    case .running: job.state == .running
    case .queued: job.state == .pending
    case .failed: job.state.isFailure
    }
  }
  private func entries(_ arrays: [ArrayGroup], _ jobs: [Job]) -> [JobListEntry] {
    arrays.map(JobListEntry.array) + jobs.map(JobListEntry.job)
  }
  @ViewBuilder private func row(_ entry: JobListEntry) -> some View {
    switch entry {
    case .array(let group): arrayLink(group)
    case .job(let job): jobLink(job)
    }
  }
  private func arrayLink(_ group: ArrayGroup) -> some View {
    NavigationLink(value: Route.array(group.id)) { ArrayRow(group: group) }
  }
  private func jobLink(_ job: Job) -> some View {
    NavigationLink(value: Route.job(job.id)) {
      JobRow(job: job, pinned: store.pins.contains(job.id), showHost: host == nil)
    }
    .accessibilityIdentifier("job-\(job.number)")
    .jobActions(job)
  }
}

/// Jobs and arrays share a section, so rows are drawn from one list.
enum JobListEntry: Identifiable {
  case array(ArrayGroup)
  case job(Job)
  var id: String {
    switch self {
    case .array(let group): "array:\(group.id.id)"
    case .job(let job): job.id.id
    }
  }
}

extension View {
  /// Swipe and context actions shared by every job list.
  func jobActions(_ job: Job) -> some View { modifier(JobActions(job: job)) }
}
private struct JobActions: ViewModifier {
  var job: Job
  @Environment(AppStore.self) private var store
  @State private var confirmCancel = false
  @State private var error: String?
  func body(content: Content) -> some View {
    let pinned = store.pins.contains(job.id)
    content
      .swipeActions(edge: .leading, allowsFullSwipe: true) {
        Button("Output", systemImage: "terminal") { store.push(.output(job.id)) }
          .tint(Theme.accent)
      }
      .swipeActions(edge: .trailing, allowsFullSwipe: true) {
        Button(pinned ? "Unpin" : "Pin", systemImage: pinned ? "pin.slash" : "pin") {
          store.togglePin(job.id)
        }.tint(Theme.amber)
        if job.state.active {
          Button("Cancel", systemImage: "stop.circle") { confirmCancel = true }.tint(Theme.red)
        }
      }
      .contextMenu {
        Button("Output", systemImage: "terminal") { store.push(.output(job.id)) }
        Button(pinned ? "Unpin" : "Pin", systemImage: pinned ? "pin.slash" : "pin") {
          store.togglePin(job.id)
        }
        Button("Relaunch…", systemImage: "arrow.clockwise") { relaunch() }
        Section {
          Button("Copy job ID", systemImage: "doc.on.doc") {
            UIPasteboard.general.string = job.number
          }
          if let workDir = job.value("work_dir") {
            Button("Copy working directory", systemImage: "folder") {
              UIPasteboard.general.string = workDir
            }
          }
        }
        if job.state.active {
          Button("Cancel job…", systemImage: "stop.circle", role: .destructive) {
            confirmCancel = true
          }
        }
      } preview: {
        JobPreview(job: job).environment(store)
      }
      .confirmationDialog(
        "Cancel #\(job.number) on \(job.host)?", isPresented: $confirmCancel,
        titleVisibility: .visible
      ) {
        Button("Cancel job", role: .destructive) {
          Task {
            do { try await store.cancel(job.id) } catch { self.error = error.localizedDescription }
          }
        }
        Button("Keep running", role: .cancel) {}
      } message: {
        Text("The scheduler will stop \(job.name). Unsaved work is lost.")
      }
      .alert(
        "Couldn’t complete the action",
        isPresented: Binding(get: { error != nil }, set: { if !$0 { error = nil } })
      ) {
        Button("OK") {}
      } message: {
        Text(error ?? "")
      }
  }
  private func relaunch() {
    Task {
      do { store.openDraft(try await store.relaunchDraft(for: job)) } catch {
        self.error = error.localizedDescription
      }
    }
  }
}

/// The card shown while pressing a job: enough to decide without opening it.
struct JobPreview: View {
  var job: Job
  var body: some View {
    VStack(alignment: .leading, spacing: 12) {
      HStack {
        StatePill(state: job.state)
        Spacer()
        Text("\(job.host) · #\(job.number)").font(.caption.monospaced()).foregroundStyle(.secondary)
      }
      Text(job.name).font(.title3.weight(.semibold)).lineLimit(2)
      if job.state == .pending {
        Text(job.value("reason") ?? "Waiting for resources").font(.subheadline)
        if let position = job.queuePosition {
          Text(
            "\(position.ahead) ahead · \(position.rank) of \(position.size) in \(position.partition)"
          )
          .font(.caption).foregroundStyle(.secondary)
        }
      } else {
        HStack(alignment: .firstTextBaseline) {
          Text(Format.duration(job.runtime)).font(.title2.weight(.semibold).monospacedDigit())
          if !job.limit.isEmpty {
            Text("of \(Format.duration(job.limit))").foregroundStyle(.secondary)
          }
          Spacer()
          if !job.state.active, let code = job.exitCode {
            Text("Exit \(code)").font(.subheadline.monospacedDigit())
              .foregroundStyle(job.succeeded ? Theme.green : Theme.red)
          }
        }
        if let fraction = job.timeFraction, job.state.active {
          ProgressView(value: fraction).tint(Theme.accent)
        }
      }
      let resources = [
        job.value("cpus").map { "\($0) CPU" }, job.value("memory"), job.value("node_list"),
      ].compactMap { $0 }
      if !resources.isEmpty {
        Text(resources.joined(separator: " · ")).font(.caption).foregroundStyle(.secondary)
          .lineLimit(1)
      }
    }
    .padding(20)
    .frame(width: 320, alignment: .leading)
  }
}

struct JobHistoryView: View {
  @Environment(AppStore.self) private var store
  @State private var query = ""
  var jobs: [Job] {
    store.listedJobs.filter {
      !$0.state.active
        && (query.isEmpty
          || "\($0.name) \($0.number) \($0.host) \($0.partition)"
            .localizedCaseInsensitiveContains(query))
    }.sorted { $0.number.localizedStandardCompare($1.number) == .orderedDescending }
  }
  var body: some View {
    List {
      Section {
        ForEach(jobs) { job in
          NavigationLink(value: Route.job(job.id)) {
            JobRow(job: job, pinned: store.pins.contains(job.id))
          }.jobActions(job)
        }
      } footer: {
        Text("Finished jobs from the last 7 days.")
      }
    }
    .overlay {
      if jobs.isEmpty {
        ContentUnavailableView(
          query.isEmpty ? "No finished jobs" : "No matches", systemImage: "clock.arrow.circlepath")
      }
    }
    .navigationTitle("History")
    .searchable(text: $query)
  }
}

struct JobDetailView: View {
  let id: JobID
  @Environment(AppStore.self) private var store
  @Environment(\.scenePhase) private var scenePhase
  @State private var error: String?
  @State private var cancelling = false
  @State private var confirmCancel = false
  @State private var document: DocumentItem?
  @State private var liveActivities = JobLiveActivities.shared
  @State private var changingFollow = false
  @State private var loading = false
  @State private var preparingRelaunch = false
  @State private var addingWatcher = false
  var job: Job? { store.job(id) }
  var watchers: [Watcher] { store.watchers.filter { $0.jobID == id } }

  var body: some View {
    Group {
      if let job {
        content(job)
      } else if loading {
        ProgressView()
      } else {
        ContentUnavailableView(
          "Job unavailable", systemImage: "questionmark.folder",
          description: Text(error ?? "Pull to refresh or check the connection."))
      }
    }
    .navigationTitle(job?.name ?? "#\(id.number)")
    .navigationSubtitle("\(id.host) · #\(id.number)")
    .toolbar { if let job { ToolbarItem(placement: .topBarTrailing) { actions(job) } } }
    .task {
      liveActivities.refresh()
      await load()
    }
    .refreshable { await load() }
    .onChange(of: scenePhase) { _, phase in if phase == .active { liveActivities.refresh() } }
    .confirmationDialog(
      "Cancel #\(id.number) on \(id.host)?", isPresented: $confirmCancel, titleVisibility: .visible
    ) {
      Button("Cancel job", role: .destructive) {
        cancelling = true
        Task {
          do { try await store.cancel(id) } catch { self.error = error.localizedDescription }
          cancelling = false
        }
      }
      Button("Keep running", role: .cancel) {}
    } message: {
      Text("The scheduler will stop this job. Unsaved work is lost.")
    }
    .sheet(item: $document) { item in NavigationStack { DocumentView(item: item) } }
    .sheet(isPresented: $addingWatcher) { NavigationStack { WatcherEditor(jobID: id) } }
  }

  @ViewBuilder private func content(_ job: Job) -> some View {
    List {
      Section { header(job) }
      if let error {
        Label(error, systemImage: "exclamationmark.triangle").foregroundStyle(Theme.amber)
          .font(.subheadline)
      } else if store.error != nil || job.stale {
        Label("Saved state — refresh before acting on this job.", systemImage: "wifi.slash")
          .foregroundStyle(Theme.amber).font(.subheadline)
      }
      Section("Output") {
        NavigationLink(value: Route.output(id)) { OutputTail(id: id, active: job.state.active) }
          .accessibilityIdentifier("watchOutput")
      }
      CollapsibleSection("Watchers", detail: "\(watchers.count)", key: "job.watchers") {
        ForEach(watchers) { watcher in
          NavigationLink(value: Route.watcher(watcher.id)) { WatcherRow(watcher: watcher) }
        }
        Button("Add watcher", systemImage: "plus") { addingWatcher = true }
      }
      let timeline = job.timeline()
      if !timeline.isEmpty {
        CollapsibleSection("Timeline", key: "job.timeline") { facts(timeline) }
      }
      if job.state == .pending, !job.queue.isEmpty {
        CollapsibleSection("Queue", key: "job.queue") { facts(job.queue) }
      }
      if !job.resources.isEmpty {
        CollapsibleSection("Resources", key: "job.resources") { facts(job.resources) }
      }
      if !job.usage.isEmpty {
        CollapsibleSection("Usage", key: "job.usage", collapsedByDefault: job.state.active) {
          facts(job.usage)
        }
      }
      Section {
        Button("Submission script", systemImage: "doc.text") { fetchDocument("script") }
        Button("Launch manifest", systemImage: "list.bullet.rectangle") {
          fetchDocument("manifest")
        }
      }
      CollapsibleSection("Details", key: "job.details", collapsedByDefault: true) {
        if !job.partition.isEmpty {
          NavigationLink(value: Route.partition(job.host, job.partition)) {
            LabeledContent("Partition", value: job.partition)
          }
        }
        facts(job.scheduling)
      }
    }
    .listSectionSpacing(.compact)
  }

  private func facts(_ facts: [JobFact]) -> some View {
    ForEach(facts) { FactRow(fact: $0) }
  }

  private func header(_ job: Job) -> some View {
    VStack(alignment: .leading, spacing: 12) {
      HStack {
        StatePill(state: job.state)
        if following { Label("On Lock Screen", systemImage: "waveform.path").font(.caption) }
        Spacer()
        if cancelling { ProgressView() }
      }.foregroundStyle(.secondary)
      if job.state == .pending {
        Text(job.value("reason") ?? "Waiting for resources").font(.title3.weight(.semibold))
        if let position = job.queuePosition {
          Text(
            position.ahead == 0
              ? "Next in \(position.partition) queue"
              : "\(position.ahead) \(position.ahead == 1 ? "job" : "jobs") ahead in \(position.partition) · \(position.rank) of \(position.size)"
          ).font(.subheadline).foregroundStyle(.secondary)
        } else if let submitted = job.submitted {
          Text("Queued \(Format.age(submitted).lowercased())").font(.subheadline)
            .foregroundStyle(.secondary)
        }
      } else {
        HStack(alignment: .firstTextBaseline) {
          Text(Format.duration(job.runtime)).font(.title.weight(.semibold).monospacedDigit())
          if !job.limit.isEmpty {
            Text("of \(Format.duration(job.limit))").foregroundStyle(.secondary)
          }
          Spacer()
          if !job.state.active, let code = job.exitCode {
            Text("Exit \(code)").font(.subheadline.monospacedDigit().weight(.medium))
              .foregroundStyle(job.succeeded ? Theme.green : Theme.red)
          }
        }
        if let fraction = job.timeFraction, job.state.active {
          ProgressView(value: fraction).tint(fraction > 0.9 ? Theme.amber : Theme.accent)
        }
      }
    }.padding(.vertical, 4)
  }

  private var following: Bool {
    guard let connection = store.connection else { return false }
    return liveActivities.activityID(host: id.host, number: id.number, connectionID: connection.id)
      != nil
  }

  private func actions(_ job: Job) -> some View {
    Menu {
      let pinned = store.pins.contains(id)
      Button(pinned ? "Unpin" : "Pin", systemImage: pinned ? "pin.slash" : "pin") {
        store.togglePin(id)
      }
      if job.state.active || following {
        Button(
          following ? "Stop following" : "Follow on Lock Screen",
          systemImage: following ? "xmark.circle" : "waveform.path"
        ) { toggleFollow(job) }
        .disabled(changingFollow)
        .accessibilityIdentifier(following ? "stopFollowingJob" : "followJob")
      }
      Button("Relaunch…", systemImage: "arrow.clockwise") { prepareRelaunch(job) }
        .disabled(preparingRelaunch)
      Button("Copy job ID", systemImage: "doc.on.doc") { UIPasteboard.general.string = id.number }
      if job.state.active {
        Divider()
        Button("Cancel job…", systemImage: "stop.circle", role: .destructive) {
          confirmCancel = true
        }.disabled(cancelling)
      }
    } label: {
      Label("Job actions", systemImage: "ellipsis")
    }
  }

  private func toggleFollow(_ job: Job) {
    guard let connection = store.connection else { return }
    changingFollow = true
    Task {
      defer { changingFollow = false }
      if let activityID = liveActivities.activityID(
        host: id.host, number: id.number, connectionID: connection.id)
      {
        await liveActivities.stop(activityID: activityID)
      } else {
        do {
          try await LiveActivityService.shared.follow(job: job, connection: connection)
        } catch { self.error = error.localizedDescription }
      }
    }
  }
  private func load() async {
    guard let api = store.client else { return }
    loading = true
    defer { loading = false }
    do {
      var job = try await api.job(id)
      job.fields["hostname"] = .string(id.host)
      store.upsert(job)
      error = nil
    } catch { self.error = error.localizedDescription }
  }
  private func script() async throws -> String {
    let value =
      store.demo
      ? JSONValue.object(["script_content": .string(LaunchDraft.sample.script)])
      : try await store.client.orThrow().document(id, kind: "script")
    return value.object.text("script_content")
  }
  private func fetchDocument(_ kind: String) {
    Task {
      do {
        let text: String
        if kind == "script" {
          text = try await script()
        } else if store.demo {
          text = JSONValue.object(["job_id": .string(id.number)]).pretty
        } else {
          text = try await store.client.orThrow().document(id, kind: kind).pretty
        }
        document = DocumentItem(
          title: kind == "script" ? "Submission script" : "Launch manifest", text: text)
      } catch { self.error = error.localizedDescription }
    }
  }
  private func prepareRelaunch(_ job: Job) {
    preparingRelaunch = true
    Task {
      defer { preparingRelaunch = false }
      do { store.openDraft(try await store.relaunchDraft(for: job)) } catch {
        self.error = error.localizedDescription
      }
    }
  }
}

extension Optional where Wrapped == APIClient {
  func orThrow() throws -> APIClient {
    guard let self else { throw APIError(status: 0, message: "Not connected to a server.") }
    return self
  }
}

/// The last few lines of stdout, so a job's progress is visible without opening the viewer.
struct OutputTail: View {
  var id: JobID
  var active: Bool
  @Environment(AppStore.self) private var store
  @State private var lines: [String] = []
  @State private var state = "Loading…"
  var body: some View {
    VStack(alignment: .leading, spacing: 8) {
      if lines.isEmpty {
        Text(state).font(.subheadline).foregroundStyle(.secondary)
      } else {
        VStack(alignment: .leading, spacing: 2) {
          ForEach(Array(lines.enumerated()), id: \.offset) { _, line in
            Text(line.isEmpty ? " " : line).lineLimit(1).truncationMode(.tail)
          }
        }
        .font(.system(size: 11, design: .monospaced)).foregroundStyle(.primary.opacity(0.85))
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(10).background(Theme.code, in: RoundedRectangle(cornerRadius: 8))
      }
    }
    .padding(.vertical, 4)
    .task(id: active ? store.refreshRevision : 0) { await load() }
  }
  private func load() async {
    let text: String
    if store.demo {
      text = DemoData.output("stdout")
    } else if let api = store.client {
      do { text = try await api.output(id, source: "stdout").stdout ?? "" } catch {
        state = "Output unavailable"
        return
      }
    } else {
      return
    }
    let all = text.split(separator: "\n", omittingEmptySubsequences: false).map(String.init)
    lines = Array(all.reversed().drop(while: \.isEmpty).prefix(6).reversed())
    if lines.isEmpty { state = "No output yet" }
  }
}

struct DocumentItem: Identifiable {
  let id = UUID()
  var title: String
  var text: String
}
struct DocumentView: View {
  var item: DocumentItem
  @Environment(\.dismiss) private var dismiss
  var body: some View {
    ScrollView([.horizontal, .vertical]) {
      Text(item.text).font(.system(.footnote, design: .monospaced)).textSelection(.enabled)
        .padding(16)
    }
    .background(Theme.code).navigationTitle(item.title).navigationBarTitleDisplayMode(.inline)
    .toolbar {
      ToolbarItem(placement: .confirmationAction) { Button("Done") { dismiss() } }
      ToolbarItem(placement: .topBarLeading) { ShareLink(item: item.text) }
    }
  }
}

struct ArrayDetailView: View {
  var id: JobID
  @Environment(AppStore.self) private var store
  var body: some View {
    Group {
      if let group = store.arrays.first(where: { $0.id == id }) {
        List {
          Section {
            HStack(spacing: 8) {
              count(group.running_count, "running", Theme.accent)
              count(group.pending_count, "queued", Theme.amber)
              count(group.completed_count, "done", Theme.green)
              count(group.failed_count, "failed", Theme.red)
            }
            .listRowInsets(EdgeInsets()).listRowBackground(Color.clear)
          }
          ForEach(taskGroups(group.tasks), id: \.title) { title, tasks, collapsed in
            CollapsibleSection(
              title, detail: "\(tasks.count)", key: "array.\(title)", collapsedByDefault: collapsed
            ) {
              CappedRows(items: tasks, limit: 10) { task in
                NavigationLink(value: Route.job(JobID(host: id.host, number: task.number))) {
                  JobRow(job: task, showHost: false)
                }
              }
            }
          }
        }
        .navigationTitle(group.job_name)
      } else {
        ContentUnavailableView(
          "Array unavailable", systemImage: "square.grid.3x3",
          description: Text("Refresh jobs to load this array."))
      }
    }
    .navigationSubtitle("\(id.host) · #\(id.number)")
  }
  /// Tasks split by outcome; finished work starts collapsed.
  private func taskGroups(_ tasks: [Job]) -> [(title: String, tasks: [Job], collapsed: Bool)] {
    [
      ("Running", tasks.filter { $0.state == .running }, false),
      ("Queued", tasks.filter { $0.state == .pending }, false),
      ("Failed", tasks.filter(\.state.isFailure), false),
      ("Completed", tasks.filter { $0.state == .completed }, true),
      ("Other", tasks.filter { $0.state == .cancelled || $0.state == .unknown }, true),
    ].filter { !$0.1.isEmpty }
  }
  private func count(_ value: Int, _ label: String, _ color: Color) -> some View {
    VStack(spacing: 2) {
      Text("\(value)").font(.title2.weight(.semibold).monospacedDigit()).foregroundStyle(color)
      Text(label).font(.caption).foregroundStyle(.secondary)
    }
    .frame(maxWidth: .infinity).padding(.vertical, 10)
    .background(color.opacity(0.08), in: RoundedRectangle(cornerRadius: 12))
  }
}
