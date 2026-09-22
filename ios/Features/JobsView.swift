import SwiftUI

struct JobsView: View {
  @Environment(AppStore.self) private var store
  @State private var query = ""
  @State private var filter = "Active"
  @Environment(\.accessibilityReduceMotion) private var reduceMotion
  private let filters = ["Active", "All", "Pinned", "History"]
  private var visible: [Job] {
    store.sortedJobs.filter { job in
      (filter != "Active" || job.state.active)
        && (filter != "Pinned" || store.pins.contains(job.id))
        && (filter != "History" || !job.state.active)
        && (query.isEmpty
          || "\(job.name) \(job.number) \(job.host) \(job.partition) \(job.user)"
            .localizedCaseInsensitiveContains(query))
    }
  }
  var body: some View {
    Screen {
      ConnectionStatus()
      HStack(spacing: 0) {
        summary(
          "Running", count: store.jobs.filter { $0.state == .running }.count,
          color: Color(red: 0.50, green: 0.87, blue: 0.72))
        Rectangle().fill(.white.opacity(0.15)).frame(width: 1, height: 40)
        summary(
          "Queued", count: store.jobs.filter { $0.state == .pending }.count,
          color: Color(red: 0.98, green: 0.76, blue: 0.40))
        Rectangle().fill(.white.opacity(0.15)).frame(width: 1, height: 40)
        summary(
          "Attention", count: store.attentionJobs.count,
          color: Color(red: 1, green: 0.57, blue: 0.53))
      }.padding(.vertical, 23).background(Theme.panel, in: RoundedRectangle(cornerRadius: 22))
        .animation(reduceMotion ? nil : .snappy(duration: 0.3), value: store.jobs.map(\.rawState))
      if let attention = store.attentionJobs.first {
        NavigationLink(value: Route.job(attention.id)) {
          Notice(
            title: attention.name,
            detail: "\(attention.host) · \(attention.state.label)",
            symbol: "exclamationmark.bubble", warning: true)
        }.buttonStyle(.plain)
      }
      Picker("Job filter", selection: $filter) { ForEach(filters, id: \.self) { Text($0) } }
        .pickerStyle(.segmented)
      if !store.arrays.isEmpty && query.isEmpty && filter != "History" {
        SectionHeading(title: "Job arrays", detail: "\(store.arrays.count)")
        ForEach(store.arrays) { group in
          NavigationLink(value: Route.array(group.id)) {
            Paper {
              HStack {
                Image("job-array").foregroundStyle(Theme.accent)
                VStack(alignment: .leading, spacing: 5) {
                  Text(group.job_name).font(.headline)
                  Text(
                    "\(group.hostname) · \(group.total_tasks) tasks · \(group.running_count) running"
                  ).font(.caption).foregroundStyle(Theme.secondary)
                }
                Spacer()
                Image(systemName: "chevron.right").font(.caption)
              }
            }
          }.buttonStyle(.plain)
        }
      }
      if visible.isEmpty {
        EmptyState(
          title: query.isEmpty ? "No jobs" : "No matching jobs",
          detail: query.isEmpty
            ? "Jobs appear here when they are submitted to a connected host."
            : "Try a job name, ID, user or partition.", symbol: "square.stack.3d.up")
      }
      ForEach(Array(Set(visible.map(\.host))).sorted(), id: \.self) { host in
        SectionHeading(title: host, detail: "\(visible.filter { $0.host == host }.count) jobs")
        if let error = store.hostErrors[host] {
          Notice(title: "Host unavailable", detail: error, warning: true)
        }
        LazyVStack(spacing: 10) {
          ForEach(visible.filter { $0.host == host }) { job in
            NavigationLink(value: Route.job(job.id)) {
              JobRow(job: job, pinned: store.pins.contains(job.id))
            }
            .buttonStyle(.plain).accessibilityIdentifier("job-\(job.number)")
            .contextMenu {
              Button(store.pins.contains(job.id) ? "Unpin" : "Pin", systemImage: "pin") {
                store.togglePin(job.id)
              }
              if job.state.needsAttention {
                Button("Mark reviewed", systemImage: "checkmark") { store.acknowledge(job.id) }
              }
            }
          }
        }
      }
      Text("Last 7 days · up to 1,000 jobs per host")
        .font(.caption2).foregroundStyle(Theme.secondary)
    }.navigationTitle("Jobs").navigationBarTitleDisplayMode(.inline).rootToolbar()
      .searchable(text: $query, prompt: "Name, job ID, host or partition")
      .refreshable { await store.refresh(force: true) }
  }
  private func summary(_ title: String, count: Int, color: Color) -> some View {
    VStack(alignment: .leading, spacing: 6) {
      Text("\(count)").font(.system(size: 38, weight: .medium, design: .rounded)).contentTransition(
        .numericText())
      HStack(spacing: 5) {
        Circle().fill(color).frame(width: 5, height: 5)
        Text(title).font(.caption)
      }
    }.foregroundStyle(.white).frame(maxWidth: .infinity)
  }
}

struct JobDetailView: View {
  let id: JobID
  @Environment(AppStore.self) private var store
  @State private var error: String?
  @State private var cancelling = false
  @State private var confirmCancel = false
  @State private var document: DocumentItem?
  @State private var liveActivities = JobLiveActivities.shared
  @State private var changingFollow = false
  @Environment(\.scenePhase) private var scenePhase
  @State private var loading = false
  var job: Job? { store.job(id) }
  var body: some View {
    Screen {
      if let job {
        HStack {
          StatePill(state: job.state)
          Spacer()
          Text("\(job.host) / #\(job.number)").font(.system(.caption, design: .monospaced))
            .foregroundStyle(Theme.secondary)
        }
        Text(job.name).font(.system(.largeTitle, design: .rounded).weight(.bold)).tracking(-1)
          .textSelection(.enabled)
        if let error {
          Notice(title: "Couldn’t complete the request", detail: error, warning: true)
        }
        if store.error != nil || job.stale {
          Notice(
            title: "Saved job state", detail: "Refresh before acting on this job.",
            symbol: "wifi.slash", warning: true)
        }
        VStack(alignment: .leading, spacing: 16) {
          Eyebrow(
            title: job.state == .pending ? "Waiting for scheduling" : "Elapsed time",
            color: Theme.onAccent)
          Text(
            job.state == .pending
              ? job.fields.text("reason", fallback: "Pending") : Format.duration(job.runtime)
          )
          .font(.system(size: 42, weight: .medium, design: .rounded)).minimumScaleFactor(0.6)
          .foregroundStyle(Theme.onAccent)
          if let fraction = job.timeFraction, job.state != .pending {
            ProgressView(value: fraction).tint(Theme.onAccent)
            Text(
              "of \(Format.duration(job.limit)) wall-time limit"
            )
            .font(.caption)
          }
        }.foregroundStyle(Theme.onAccent).padding(24).frame(
          maxWidth: .infinity, alignment: .leading
        )
        .background(Theme.accent, in: RoundedRectangle(cornerRadius: 22))
        HStack(spacing: 12) {
          NavigationLink(value: Route.output(id)) {
            Label("Watch output", systemImage: "terminal").frame(maxWidth: .infinity)
          }
          .buttonStyle(PrimaryButtonStyle()).accessibilityIdentifier("watchOutput")
          Button {
            store.togglePin(id)
          } label: {
            Image(systemName: store.pins.contains(id) ? "pin.fill" : "pin").frame(
              width: 52, height: 52
            ).background(Theme.soft, in: RoundedRectangle(cornerRadius: 15))
          }.accessibilityLabel(store.pins.contains(id) ? "Unpin job" : "Pin job")
        }
        if let connection = store.connection {
          let activityID = liveActivities.activityID(
            host: id.host, number: id.number, connectionID: connection.id)
          if job.state.active || activityID != nil {
            Button {
              changingFollow = true
              Task {
                defer { changingFollow = false }
                if let activityID {
                  await liveActivities.stop(activityID: activityID)
                } else {
                  do {
                    try await LiveActivityService.shared.follow(job: job, connection: connection)
                  } catch { self.error = error.localizedDescription }
                }
              }
            } label: {
              HStack {
                Label(
                  activityID == nil ? "Follow on Lock Screen" : "Stop following",
                  systemImage: activityID == nil ? "waveform.path" : "xmark.circle")
                Spacer()
                if changingFollow { ProgressView() }
              }
              .font(.subheadline.weight(.semibold))
              .frame(minHeight: 44)
            }
            .disabled(changingFollow)
            .accessibilityIdentifier(activityID == nil ? "followJob" : "stopFollowingJob")
            .accessibilityHint(activityID == nil ? "Show a Live Activity" : "The job keeps running")
          }
        }
        SectionHeading(title: "Allocation")
        Paper {
          VStack(spacing: 14) {
            DetailRow(name: "Host", value: job.host)
            NavigationLink(value: Route.partition(job.host, job.partition)) {
              DetailRow(name: "Partition", value: job.partition)
            }
            Divider()
            DetailRow(name: "CPUs", value: job.fields.text("cpus"))
            DetailRow(name: "Memory requested", value: job.fields.text("memory"))
            DetailRow(name: "Nodes", value: job.fields.text("nodes"))
            DetailRow(name: "Allocated resources", value: job.fields.text("alloc_tres"))
            DetailRow(name: "User", value: job.user)
          }
        }
        SectionHeading(
          title: "Watchers", detail: "\(store.watchers.filter { $0.jobID == id }.count)")
        ForEach(store.watchers.filter { $0.jobID == id }) { watcher in
          NavigationLink(value: Route.watcher(watcher.id)) { WatcherCard(watcher: watcher) }
            .buttonStyle(.plain)
        }
        NavigationLink {
          WatcherEditor(jobID: id)
        } label: {
          Label("Add watcher", systemImage: "plus.circle")
        }
        SectionHeading(title: "Files & details")
        Paper {
          VStack(alignment: .leading, spacing: 18) {
            Button("View submission script", systemImage: "doc.text") { fetchDocument("script") }
            Button("View launch manifest", systemImage: "list.bullet.rectangle") {
              fetchDocument("manifest")
            }
            Divider()
            DetailRow(
              name: "Working directory", value: job.fields.text("work_dir"), monospaced: true)
            DetailRow(name: "Started", value: job.fields.text("start_time"))
            DetailRow(name: "Finished", value: job.fields.text("end_time"))
            DetailRow(name: "Raw scheduler state", value: job.rawState)
          }
        }
        Button("Prepare a relaunch", systemImage: "arrow.uturn.up") { prepareRelaunch(job) }
          .disabled(loading)
        if job.state.needsAttention {
          Button("Mark reviewed", systemImage: "checkmark.circle") { store.acknowledge(id) }
        }
        if job.state.active {
          Button(
            cancelling ? "Cancelling…" : "Cancel job", systemImage: "stop.circle",
            role: .destructive
          ) { confirmCancel = true }
          .disabled(cancelling).padding(.top, 8)
        }
      } else if loading {
        ProgressView("Loading job…").frame(maxWidth: .infinity).padding(50)
      } else {
        EmptyState(
          title: "Job unavailable", detail: error ?? "Pull to refresh or check the connection.",
          symbol: "questionmark.folder")
      }
    }.navigationTitle("Job").navigationBarTitleDisplayMode(.inline)
      .task {
        liveActivities.refresh()
        await load()
      }.refreshable { await load() }
      .onChange(of: scenePhase) { _, phase in
        if phase == .active { liveActivities.refresh() }
      }
      .confirmationDialog(
        "Cancel #\(id.number) on \(id.host)?", isPresented: $confirmCancel,
        titleVisibility: .visible
      ) {
        Button("Cancel job", role: .destructive) {
          cancelling = true
          Task {
            do { try await store.cancel(id) } catch { self.error = error.localizedDescription }
            cancelling = false
          }
        }
      } message: {
        Text("The scheduler will stop this job. Its work may not have been saved.")
      }
      .sheet(item: $document) { item in NavigationStack { DocumentView(item: item) } }
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
  private func fetchDocument(_ kind: String) {
    Task {
      do {
        let value =
          store.demo
          ? JSONValue.object(["script_content": .string(LaunchDraft.sample.script)])
          : try await store.client!.document(id, kind: kind)
        document = DocumentItem(
          title: kind.capitalized,
          text: kind == "script" ? value.object.text("script_content") : value.pretty)
      } catch { self.error = error.localizedDescription }
    }
  }
  private func prepareRelaunch(_ job: Job) {
    loading = true
    Task {
      defer { loading = false }
      do {
        let script =
          store.demo
          ? JSONValue.object(["script_content": .string(LaunchDraft.sample.script)])
          : try await store.client!.document(id, kind: "script")
        var draft = LaunchDraft()
        draft.host = id.host
        draft.name = job.name
        draft.partition = job.partition
        draft.script = script.object.text("script_content")
        guard !draft.script.isEmpty else {
          throw APIError(status: 0, message: "The submission script is unavailable.")
        }
        draft.provenance =
          "Prepared from \(id.host) / #\(id.number). Review resource and sync settings before launching."
        if let api = store.client, let manifest = try? await api.document(id, kind: "manifest") {
          draft.extraFields["launch_manifest"] = manifest
        }
        try store.saveDraft(draft)
        store.openDraft(draft)
      } catch { self.error = error.localizedDescription }
    }
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
      Text(item.text).font(.system(.caption, design: .monospaced)).textSelection(.enabled).padding(
        20)
    }
    .background(Theme.canvas).navigationTitle(item.title).navigationBarTitleDisplayMode(.inline)
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
    Screen {
      if let group = store.arrays.first(where: { $0.id == id }) {
        Text(group.job_name).font(.largeTitle.bold())
        Notice(
          title: "\(group.total_tasks) tasks",
          detail:
            "\(group.running_count) running · \(group.pending_count) pending · \(group.completed_count) completed · \(group.failed_count) failed"
        )
        ForEach(group.tasks) { task in
          NavigationLink(value: Route.job(JobID(host: id.host, number: task.number))) {
            JobRow(job: task)
          }.buttonStyle(.plain)
        }
      } else {
        EmptyState(
          title: "Array unavailable", detail: "Refresh jobs to load this array.",
          symbol: "square.grid.3x3")
      }
    }.navigationTitle("Job array").navigationBarTitleDisplayMode(.inline)
  }
}
