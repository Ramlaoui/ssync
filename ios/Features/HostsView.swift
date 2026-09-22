import SwiftUI

struct HostsView: View {
  @Environment(AppStore.self) private var store
  var body: some View {
    Screen {
      ConnectionStatus()
      ForEach(store.hosts) { host in
        NavigationLink(value: Route.host(host.hostname)) { HostCard(host: host.hostname) }
          .buttonStyle(.plain)
          .accessibilityIdentifier("host-\(host.hostname)")
      }
      if store.hosts.isEmpty {
        EmptyState(
          title: "No hosts yet", detail: "Configure a host on your ssync server, then refresh.",
          symbol: "server.rack")
      }
      Notice(
        title: "Allocation, not utilization",
        detail:
          "These are scheduler resource counts. Partitions can share nodes, so their capacities are not added together.",
        symbol: "chart.bar.xaxis")
    }.navigationTitle("Hosts").navigationBarTitleDisplayMode(.inline).rootToolbar()
      .refreshable { await store.refresh(force: true) }
  }
}
struct HostCard: View {
  var host: String
  @Environment(AppStore.self) private var store
  var snapshot: PartitionSnapshot? { store.partitions.first { $0.hostname == host } }
  var jobs: [Job] { store.jobs.filter { $0.host == host } }
  var body: some View {
    Paper {
      VStack(alignment: .leading, spacing: 18) {
        HStack {
          Image(systemName: "server.rack").foregroundStyle(Theme.accent)
          Text(host).font(.title2.weight(.semibold))
          Spacer()
          Image(systemName: "chevron.right").font(.caption).foregroundStyle(Theme.secondary)
        }
        HStack(spacing: 18) {
          Label("\(jobs.filter { $0.state == .running }.count) running", systemImage: "play.circle")
            .foregroundStyle(Theme.green)
          Label("\(jobs.filter { $0.state == .pending }.count) queued", systemImage: "clock")
            .foregroundStyle(Theme.amber)
        }.font(.caption.weight(.medium))
        if let snapshot {
          if snapshot.stale == true || snapshot.error != nil {
            Notice(title: "Capacity may be out of date", detail: snapshot.error, warning: true)
          }
          ForEach(snapshot.partitions.prefix(3)) { partition in
            PartitionSummary(partition: partition)
          }
          Text("Capacity · \(Format.age(snapshot.observedAt))").font(.caption2).foregroundStyle(
            Theme.secondary)
        } else {
          Text("Capacity unavailable").font(.caption).foregroundStyle(Theme.secondary)
        }
      }
    }
  }
}
struct PartitionSummary: View {
  var partition: Partition
  var body: some View {
    VStack(alignment: .leading, spacing: 8) {
      HStack {
        Text(partition.partition).font(.subheadline.weight(.semibold))
        Spacer()
        Text(
          partition.hasGPUs
            ? "\(partition.gpus_idle.map(String.init) ?? "—") GPU idle"
            : "\(partition.cpus_idle) CPU idle"
        ).font(.caption).foregroundStyle(Theme.secondary)
      }
      CapacityBar(
        allocated: partition.cpus_alloc, idle: partition.cpus_idle, other: partition.cpus_other,
        total: partition.cpus_total)
      HStack {
        Text("\(partition.cpus_alloc)/\(partition.cpus_total) CPUs allocated")
        Spacer()
        Text(partition.availability ?? "Unknown")
      }.font(.caption2).foregroundStyle(Theme.secondary)
    }
  }
}
struct HostDetailView: View {
  var host: String
  @Environment(AppStore.self) private var store
  var snapshot: PartitionSnapshot? { store.partitions.first { $0.hostname == host } }
  var jobs: [Job] { store.sortedJobs.filter { $0.host == host && $0.state.active } }
  var body: some View {
    Screen {
      Eyebrow(title: "Cluster overview")
      Text(host).font(.system(.largeTitle, design: .rounded).weight(.bold))
      if let error = store.hostErrors[host] {
        Notice(title: "Host unavailable", detail: error, warning: true)
      }
      if let snapshot {
        Notice(
          title: "Capacity sampled \(Format.age(snapshot.observedAt).lowercased())",
          detail: snapshot.error
            ?? "\(snapshot.partitions.count) partitions · Counts may overlap between partitions.",
          symbol: snapshot.stale == true ? "clock.badge.exclamationmark" : "chart.bar",
          warning: snapshot.stale == true || snapshot.error != nil)
        SectionHeading(title: "Partitions")
        ForEach(snapshot.partitions) { partition in
          NavigationLink(value: Route.partition(host, partition.partition)) {
            Paper { PartitionSummary(partition: partition) }
          }.buttonStyle(.plain)
        }
      } else {
        Notice(
          title: "No capacity snapshot", detail: "Pull to refresh when the host is reachable.",
          warning: true)
      }
      SectionHeading(title: "Active jobs", detail: "\(jobs.count) loaded")
      Text(
        "Job data · \(Format.age(store.receivedAt)). Counts include jobs visible to this server, within the loaded scope."
      )
      .font(.caption).foregroundStyle(Theme.secondary)
      ForEach(jobs) { job in
        NavigationLink(value: Route.job(job.id)) { JobRow(job: job) }.buttonStyle(.plain)
      }
      if jobs.isEmpty {
        EmptyState(
          title: "No active jobs",
          detail: "There are no running or pending jobs in the loaded scope.")
      }
    }.navigationTitle(host).navigationBarTitleDisplayMode(.inline).refreshable {
      await store.refresh(force: true)
    }
  }
}
struct PartitionDetailView: View {
  var host: String
  var name: String
  @Environment(AppStore.self) private var store
  @State private var scope = "Active"
  var snapshot: PartitionSnapshot? { store.partitions.first { $0.hostname == host } }
  var partition: Partition? {
    snapshot?.partitions.first {
      $0.partition.trimmingCharacters(in: CharacterSet(charactersIn: "*"))
        == name.trimmingCharacters(in: CharacterSet(charactersIn: "*"))
    }
  }
  var jobs: [Job] {
    store.sortedJobs.filter {
      $0.host == host
        && $0.partition.split(separator: ",").contains(
          Substring(name.trimmingCharacters(in: CharacterSet(charactersIn: "*"))))
        && (scope != "Active" || $0.state.active)
        && (scope != "Queued" || $0.state == .pending)
        && (scope != "Running" || $0.state == .running)
    }
  }
  var body: some View {
    Screen {
      Eyebrow(title: host)
      Text(name).font(.system(.largeTitle, design: .rounded).weight(.bold))
      if let partition {
        HStack {
          Label(partition.availability ?? "Unknown", systemImage: "circle.fill").font(.caption)
            .foregroundStyle(Theme.green)
          Spacer()
          Text("\(partition.nodes_total) nodes").font(.subheadline)
        }
        Notice(
          title: "Capacity · \(Format.age(snapshot?.observedAt))",
          detail: snapshot?.error
            ?? "Scheduler allocation snapshot. Idle resources may still be constrained by policy or reservations.",
          warning: snapshot?.stale == true)
        Paper {
          VStack(alignment: .leading, spacing: 16) {
            Eyebrow(title: "CPUs")
            HStack(alignment: .firstTextBaseline) {
              Text("\(partition.cpus_alloc)").font(
                .system(size: 44, weight: .medium, design: .rounded))
              Text("/ \(partition.cpus_total) allocated").foregroundStyle(Theme.secondary)
            }
            CapacityBar(
              allocated: partition.cpus_alloc, idle: partition.cpus_idle,
              other: partition.cpus_other, total: partition.cpus_total)
            HStack {
              Label("\(partition.cpus_idle) idle", systemImage: "circle.fill").foregroundStyle(
                Theme.green)
              Spacer()
              Label("\(partition.cpus_other) other", systemImage: "circle.fill").foregroundStyle(
                Theme.amber)
            }.font(.caption)
          }
        }
        if partition.hasGPUs {
          Paper {
            VStack(alignment: .leading, spacing: 15) {
              Eyebrow(title: "GPUs")
              Text(
                "\(partition.gpus_used.map(String.init) ?? "—") / \(partition.gpus_total ?? 0) allocated"
              ).font(.title2.weight(.semibold))
              if let used = partition.gpus_used, let idle = partition.gpus_idle {
                CapacityBar(allocated: used, idle: idle, total: partition.gpus_total ?? 0)
              }
              ForEach((partition.gpu_types ?? [:]).keys.sorted(), id: \.self) { type in
                if let counts = partition.gpu_types?[type] {
                  DetailRow(
                    name: type,
                    value: "\(counts.used) allocated · \(max(0, counts.total - counts.used)) idle")
                }
              }
            }
          }
        }
        Paper {
          VStack(alignment: .leading, spacing: 10) {
            Eyebrow(title: "Node states")
            Text(partition.states.joined(separator: " · ")).font(.subheadline)
            Text("Aggregate states; individual node health is not reported by this API.").font(
              .caption
            ).foregroundStyle(Theme.secondary)
          }
        }
      } else {
        Notice(
          title: "Capacity unavailable",
          detail: "The partition may have changed or the host could be offline.", warning: true)
      }
      SectionHeading(title: "Jobs in this partition")
      Picker("Job state", selection: $scope) {
        ForEach(["Active", "Running", "Queued", "All"], id: \.self) { Text($0) }
      }.pickerStyle(.segmented)
      ForEach(jobs) { job in
        NavigationLink(value: Route.job(job.id)) { JobRow(job: job) }.buttonStyle(.plain)
      }
      if jobs.isEmpty {
        EmptyState(
          title: "No matching jobs",
          detail: "Try a different filter. Jobs are scoped to the last 7 days.")
      }
      Button("Prepare launch here", systemImage: "arrow.up.right") {
        var draft = LaunchDraft()
        draft.host = host
        draft.partition = name.trimmingCharacters(in: CharacterSet(charactersIn: "*"))
        store.openDraft(draft)
      }.buttonStyle(PrimaryButtonStyle())
    }.navigationTitle("Partition").navigationBarTitleDisplayMode(.inline).refreshable {
      await store.refresh(force: true)
    }
  }
}
