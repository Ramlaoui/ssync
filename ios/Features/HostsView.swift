import SwiftUI

struct ClusterView: View {
  @Environment(AppStore.self) private var store
  @State private var explaining = false
  var body: some View {
    List {
      if store.error != nil && !store.demo { ConnectionBanner() }
      ForEach(store.hosts) { host in
        let snapshot = store.partitions.first { $0.hostname == host.hostname }
        Section {
          NavigationLink(value: Route.host(host.hostname)) { HostRow(host: host.hostname) }
            .accessibilityIdentifier("host-\(host.hostname)")
          ForEach(snapshot?.partitions ?? []) { partition in
            NavigationLink(value: Route.partition(host.hostname, partition.partition)) {
              PartitionRow(partition: partition)
            }
          }
        } footer: {
          if let snapshot {
            Text(
              snapshot.error.map { "Capacity may be out of date: \($0)" }
                ?? "Capacity sampled \(Format.age(snapshot.observedAt).lowercased())")
          } else {
            Text("Capacity unavailable")
          }
        }
      }
    }
    .overlay {
      if store.hosts.isEmpty {
        ContentUnavailableView(
          "No hosts", systemImage: "server.rack",
          description: Text("Configure a host on your ssync server, then refresh."))
      }
    }
    .navigationTitle("Cluster")
    .rootToolbar()
    .toolbar {
      ToolbarItem(placement: .topBarTrailing) {
        Button("About capacity", systemImage: "info.circle") { explaining = true }
      }
    }
    .alert("Allocation, not utilization", isPresented: $explaining) {
      Button("OK") {}
    } message: {
      Text(
        "Bars show what the scheduler has allocated. Partitions can share nodes, so their capacities don't add up, and idle resources may still be limited by policy or reservations."
      )
    }
    .refreshable { await store.refresh(force: true) }
  }
}

struct HostRow: View {
  var host: String
  @Environment(AppStore.self) private var store
  var body: some View {
    let jobs = store.jobs.filter { $0.host == host }
    let running = jobs.filter { $0.state == .running }.count
    let queued = jobs.filter { $0.state == .pending }.count
    HStack(spacing: 12) {
      Image(systemName: store.hostErrors[host] == nil ? "server.rack" : "exclamationmark.triangle")
        .foregroundStyle(store.hostErrors[host] == nil ? Theme.accent : Theme.amber)
        .frame(width: 22)
      VStack(alignment: .leading, spacing: 2) {
        Text(host).font(.headline)
        Text(store.hostErrors[host] ?? "\(running) running · \(queued) queued")
          .font(.caption).foregroundStyle(.secondary).lineLimit(1)
      }
    }
    .accessibilityElement(children: .combine)
  }
}

struct PartitionRow: View {
  var partition: Partition
  var body: some View {
    VStack(alignment: .leading, spacing: 6) {
      HStack {
        Circle().fill(partition.availability?.lowercased() == "up" ? Theme.green : Theme.amber)
          .frame(width: 6, height: 6)
        Text(partition.partition).font(.subheadline.weight(.medium))
        Spacer()
        Text(usage).font(.caption.monospacedDigit()).foregroundStyle(.secondary)
      }
      if partition.hasGPUs, let used = partition.gpus_used, let idle = partition.gpus_idle {
        CapacityBar(allocated: used, idle: idle, total: partition.gpus_total ?? 0)
      } else {
        CapacityBar(
          allocated: partition.cpus_alloc, idle: partition.cpus_idle,
          other: partition.cpus_other, total: partition.cpus_total)
      }
    }
    .padding(.vertical, 2)
    .accessibilityElement(children: .combine)
  }
  private var usage: String {
    if partition.hasGPUs {
      return
        "\(partition.gpus_idle.map(String.init) ?? "—") of \(partition.gpus_total ?? 0) GPUs idle"
    }
    return "\(partition.cpus_idle) of \(partition.cpus_total) CPUs idle"
  }
}

struct HostDetailView: View {
  var host: String
  @Environment(AppStore.self) private var store
  var snapshot: PartitionSnapshot? { store.partitions.first { $0.hostname == host } }
  var jobs: [Job] { store.listedJobs.filter { $0.host == host && $0.state.active } }
  var body: some View {
    List {
      if let error = store.hostErrors[host] {
        Label(error, systemImage: "exclamationmark.triangle").foregroundStyle(Theme.amber)
          .font(.subheadline)
      }
      Section {
        ForEach(snapshot?.partitions ?? []) { partition in
          NavigationLink(value: Route.partition(host, partition.partition)) {
            PartitionRow(partition: partition)
          }
        }
      } header: {
        Text("Partitions")
      } footer: {
        if let snapshot {
          Text("Sampled \(Format.age(snapshot.observedAt).lowercased())")
        } else {
          Text("No capacity snapshot. Pull to refresh when the host is reachable.")
        }
      }
      Section("Your active jobs") {
        ForEach(jobs) { job in
          NavigationLink(value: Route.job(job.id)) {
            JobRow(job: job, pinned: store.pins.contains(job.id), showHost: false)
          }.jobActions(job)
        }
        if jobs.isEmpty {
          Text("Nothing running or queued").foregroundStyle(.secondary)
        }
      }
    }
    .navigationTitle(host)
    .toolbar {
      ToolbarItem(placement: .topBarTrailing) {
        Button("Launch on \(host)", systemImage: "plus") {
          var draft = LaunchDraft()
          draft.host = host
          store.openDraft(draft)
        }
      }
    }
    .refreshable { await store.refresh(force: true) }
  }
}

struct PartitionDetailView: View {
  var host: String
  var name: String
  @Environment(AppStore.self) private var store
  @State private var scope = "Active"
  var snapshot: PartitionSnapshot? { store.partitions.first { $0.hostname == host } }
  var cleanName: String { name.trimmingCharacters(in: CharacterSet(charactersIn: "*")) }
  var partition: Partition? {
    snapshot?.partitions.first {
      $0.partition.trimmingCharacters(in: CharacterSet(charactersIn: "*")) == cleanName
    }
  }
  var jobs: [Job] {
    store.listedJobs.filter {
      $0.host == host
        && $0.partition.split(separator: ",").contains(Substring(cleanName))
        && (scope != "Active" || $0.state.active)
        && (scope != "Queued" || $0.state == .pending)
        && (scope != "Running" || $0.state == .running)
    }
  }
  var body: some View {
    List {
      if let partition {
        Section {
          metric(
            "CPUs", allocated: partition.cpus_alloc, idle: partition.cpus_idle,
            other: partition.cpus_other, total: partition.cpus_total)
          if partition.hasGPUs, let used = partition.gpus_used, let idle = partition.gpus_idle {
            metric("GPUs", allocated: used, idle: idle, other: 0, total: partition.gpus_total ?? 0)
            ForEach((partition.gpu_types ?? [:]).keys.sorted(), id: \.self) { type in
              if let counts = partition.gpu_types?[type] {
                DetailRow(
                  name: type, value: "\(max(0, counts.total - counts.used)) of \(counts.total) idle"
                )
              }
            }
          }
        } footer: {
          Text(
            "Scheduler allocation, sampled \(Format.age(snapshot?.observedAt).lowercased())."
          )
        }
        Section {
          DetailRow(name: "Availability", value: partition.availability ?? "Unknown")
          DetailRow(name: "Nodes", value: "\(partition.nodes_total)")
          DetailRow(name: "Node states", value: partition.states.joined(separator: ", "))
        }
      } else {
        Label(
          "Capacity unavailable. The partition may have changed or the host is offline.",
          systemImage: "exclamationmark.triangle"
        ).foregroundStyle(Theme.amber).font(.subheadline)
      }
      Section {
        Picker("Show", selection: $scope) {
          ForEach(["Active", "Running", "Queued", "All"], id: \.self) { Text($0) }
        }.pickerStyle(.segmented).listRowBackground(Color.clear).listRowInsets(EdgeInsets())
        ForEach(jobs) { job in
          NavigationLink(value: Route.job(job.id)) {
            JobRow(job: job, pinned: store.pins.contains(job.id), showHost: false)
          }.jobActions(job)
        }
        if jobs.isEmpty { Text("No matching jobs").foregroundStyle(.secondary) }
      } header: {
        Text("Your jobs")
      }
    }
    .navigationTitle(cleanName)
    .navigationSubtitle(host)
    .toolbar {
      ToolbarItem(placement: .topBarTrailing) {
        Button("Launch here", systemImage: "plus") {
          var draft = LaunchDraft()
          draft.host = host
          draft.partition = cleanName
          store.openDraft(draft)
        }
      }
    }
    .refreshable { await store.refresh(force: true) }
  }
  private func metric(_ title: String, allocated: Int, idle: Int, other: Int, total: Int)
    -> some View
  {
    VStack(alignment: .leading, spacing: 8) {
      HStack(alignment: .firstTextBaseline) {
        Text(title).font(.subheadline.weight(.semibold))
        Spacer()
        Text("\(idle)").font(.title2.weight(.semibold).monospacedDigit())
          .foregroundStyle(Theme.green)
        Text("idle of \(total)").font(.subheadline).foregroundStyle(.secondary)
      }
      CapacityBar(allocated: allocated, idle: idle, other: other, total: total)
      Text("\(allocated) allocated" + (other > 0 ? " · \(other) other" : ""))
        .font(.caption).foregroundStyle(.secondary)
    }.padding(.vertical, 4)
  }
}
