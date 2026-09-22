import ActivityKit
import AppIntents
import SwiftUI
import WidgetKit

@main struct SsyncWidgetBundle: WidgetBundle {
  var body: some Widget {
    JobsSummaryWidget()
    PinnedJobWidget()
    PartitionWidget()
    JobLiveActivity()
  }
}

struct SnapshotEntry: TimelineEntry {
  var date: Date
  var snapshot: SystemSnapshot
  var selection: String? = nil
}
struct SnapshotProvider: TimelineProvider {
  func placeholder(in context: Context) -> SnapshotEntry {
    SnapshotEntry(date: .now, snapshot: .empty)
  }
  func getSnapshot(in context: Context, completion: @escaping (SnapshotEntry) -> Void) {
    completion(SnapshotEntry(date: .now, snapshot: .read()))
  }
  func getTimeline(in context: Context, completion: @escaping (Timeline<SnapshotEntry>) -> Void) {
    completion(
      Timeline(
        entries: [SnapshotEntry(date: .now, snapshot: .read())],
        policy: .after(.now.addingTimeInterval(900))))
  }
}

struct JobsSummaryWidget: Widget {
  let kind = "ssync.jobs"
  var body: some WidgetConfiguration {
    StaticConfiguration(kind: kind, provider: SnapshotProvider()) { entry in
      VStack(alignment: .leading, spacing: 14) {
        WidgetHeader(title: "ssync", updated: entry.snapshot.updatedAt)
        HStack(spacing: 20) {
          count(entry.snapshot.running, "Running", Color("Running"))
          count(entry.snapshot.pending, "Queued", Color("Warning"))
          count(entry.snapshot.attention, "Attention", Color("Danger"))
        }
        Text(entry.snapshot.name).font(.caption2).foregroundStyle(Color("InkSecondary")).lineLimit(
          1)
      }.containerBackground(Color("Canvas"), for: .widget)
        .widgetURL(URL(string: "ssync://jobs"))
    }.configurationDisplayName("Your jobs").description(
      "Running, queued and attention counts from your latest ssync snapshot."
    )
    .supportedFamilies([.systemMedium])
  }
  private func count(_ count: Int, _ title: String, _ color: Color) -> some View {
    VStack(alignment: .leading, spacing: 3) {
      Text("\(count)").font(.system(size: 34, weight: .medium, design: .rounded)).foregroundStyle(
        Color("Ink"))
      Label(title, systemImage: "circle.fill").font(.caption2).foregroundStyle(color)
    }.frame(maxWidth: .infinity, alignment: .leading)
  }
}

struct WidgetJob: AppEntity {
  static let typeDisplayRepresentation = TypeDisplayRepresentation(name: "Job")
  static let defaultQuery = WidgetJobQuery()
  var id: String
  var name: String
  var displayRepresentation: DisplayRepresentation {
    DisplayRepresentation(title: "\(name)", subtitle: "\(id)")
  }
}
struct WidgetJobQuery: EntityQuery {
  func entities(for identifiers: [String]) async throws -> [WidgetJob] {
    SystemSnapshot.read().jobs.filter { identifiers.contains($0.id) }.map {
      WidgetJob(id: $0.id, name: $0.name)
    }
  }
  func suggestedEntities() async throws -> [WidgetJob] {
    SystemSnapshot.read().jobs.filter(\.pinned).map { WidgetJob(id: $0.id, name: $0.name) }
  }
}
struct PinnedConfiguration: WidgetConfigurationIntent {
  static let title: LocalizedStringResource = "Pinned job"
  static let description = IntentDescription("Choose a job pinned in ssync.")
  @Parameter(title: "Job") var job: WidgetJob?
}
struct PinnedProvider: AppIntentTimelineProvider {
  func placeholder(in context: Context) -> SnapshotEntry {
    SnapshotEntry(date: .now, snapshot: .empty)
  }
  func snapshot(for configuration: PinnedConfiguration, in context: Context) async -> SnapshotEntry
  {
    SnapshotEntry(date: .now, snapshot: .read(), selection: configuration.job?.id)
  }
  func timeline(for configuration: PinnedConfiguration, in context: Context) async -> Timeline<
    SnapshotEntry
  > {
    Timeline(
      entries: [await snapshot(for: configuration, in: context)],
      policy: .after(.now.addingTimeInterval(900)))
  }
}
struct PinnedJobWidget: Widget {
  var body: some WidgetConfiguration {
    AppIntentConfiguration(
      kind: "ssync.pinned", intent: PinnedConfiguration.self, provider: PinnedProvider()
    ) { entry in
      let job = entry.snapshot.jobs.first { job in
        entry.selection.map { $0 == job.id } ?? job.pinned
      }
      PinnedWidgetView(entry: entry, job: job).containerBackground(Color("Canvas"), for: .widget)
    }.configurationDisplayName("Pinned job").description(
      "Keep one job close, with a timestamp for its last update."
    )
    .supportedFamilies([.systemSmall, .systemMedium])
  }
}
struct PinnedWidgetView: View {
  var entry: SnapshotEntry
  var job: SystemJob?
  var body: some View {
    VStack(alignment: .leading, spacing: 10) {
      WidgetHeader(title: "Pinned", updated: nil)
      if let job {
        Text(job.name).font(.headline).lineLimit(2)
        Text("\(job.host) · #\(job.number)").font(.caption2).foregroundStyle(Color("InkSecondary"))
        Spacer(minLength: 0)
        Text(job.state).font(.subheadline.weight(.semibold)).foregroundStyle(Color("Accent"))
        Text("\(job.runtime) elapsed").font(.caption2)
        if let updated = entry.snapshot.updatedAt {
          Text(updated, style: .relative).font(.caption2).foregroundStyle(Color("InkSecondary"))
        }
      } else {
        Text("Pin a job in ssync").font(.subheadline)
        Spacer()
      }
    }.foregroundStyle(Color("Ink")).widgetURL(
      job?.url(connection: entry.snapshot.connectionID) ?? URL(string: "ssync://jobs"))
  }
}
struct WidgetPartition: AppEntity {
  static let typeDisplayRepresentation = TypeDisplayRepresentation(name: "Partition")
  static let defaultQuery = WidgetPartitionQuery()
  var id: String
  var name: String
  var displayRepresentation: DisplayRepresentation {
    DisplayRepresentation(title: "\(name)", subtitle: "\(id)")
  }
}
struct WidgetPartitionQuery: EntityQuery {
  func entities(for identifiers: [String]) async throws -> [WidgetPartition] {
    SystemSnapshot.read().partitions.filter { identifiers.contains($0.id) }.map {
      WidgetPartition(id: $0.id, name: $0.name)
    }
  }
  func suggestedEntities() async throws -> [WidgetPartition] {
    SystemSnapshot.read().partitions.map { WidgetPartition(id: $0.id, name: $0.name) }
  }
}
struct PartitionConfiguration: WidgetConfigurationIntent {
  static let title: LocalizedStringResource = "Partition capacity"
  @Parameter(title: "Partition") var partition: WidgetPartition?
}
struct PartitionProvider: AppIntentTimelineProvider {
  func placeholder(in context: Context) -> SnapshotEntry {
    SnapshotEntry(date: .now, snapshot: .empty)
  }
  func snapshot(for configuration: PartitionConfiguration, in context: Context) async
    -> SnapshotEntry
  {
    SnapshotEntry(date: .now, snapshot: .read(), selection: configuration.partition?.id)
  }
  func timeline(for configuration: PartitionConfiguration, in context: Context) async -> Timeline<
    SnapshotEntry
  > {
    Timeline(
      entries: [await snapshot(for: configuration, in: context)],
      policy: .after(.now.addingTimeInterval(900)))
  }
}
struct PartitionWidget: Widget {
  var body: some WidgetConfiguration {
    AppIntentConfiguration(
      kind: "ssync.partition", intent: PartitionConfiguration.self, provider: PartitionProvider()
    ) { entry in
      let partition =
        entry.snapshot.partitions.first { $0.id == entry.selection }
        ?? (entry.selection == nil ? entry.snapshot.partitions.first : nil)
      VStack(alignment: .leading, spacing: 12) {
        WidgetHeader(title: partition?.name ?? "Partition", updated: partition?.updatedAt)
        if let partition {
          HStack(alignment: .firstTextBaseline) {
            Text("\(partition.allocated)").font(
              .system(size: 36, weight: .medium, design: .rounded))
            Text("/ \(partition.total) CPUs allocated").font(.caption)
          }
          ProgressView(value: Double(partition.allocated), total: Double(max(partition.total, 1)))
            .tint(Color("Accent"))
          HStack {
            Text("\(partition.idle) idle · \(partition.other) other")
            Spacer()
            Text(partition.host)
          }.font(.caption2).foregroundStyle(Color("InkSecondary"))
        } else {
          Text("Open ssync to load capacity.").font(.subheadline)
        }
      }.foregroundStyle(Color("Ink")).containerBackground(Color("Canvas"), for: .widget)
        .widgetURL(hostURL(partition?.host, connection: entry.snapshot.connectionID))
    }.configurationDisplayName("Partition capacity").description(
      "Scheduler CPU allocation for one partition. Data is a saved snapshot."
    )
    .supportedFamilies([.systemMedium])
  }
  private func hostURL(_ host: String?, connection: UUID?) -> URL {
    var parts = URLComponents()
    parts.scheme = "ssync"
    parts.host = "host"
    parts.queryItems = [
      URLQueryItem(name: "name", value: host),
      URLQueryItem(name: "connection", value: connection?.uuidString),
    ]
    return parts.url!
  }
}
struct WidgetHeader: View {
  var title: String
  var updated: Date?
  var body: some View {
    HStack(spacing: 6) {
      RelayMark(size: 23)
      Text(title).font(.caption.weight(.semibold)).lineLimit(1)
      Spacer(minLength: 0)
      if let updated {
        Text(updated, style: .relative).font(.caption2).foregroundStyle(Color("InkSecondary"))
      }
    }
  }
}
struct JobLiveActivity: Widget {
  var body: some WidgetConfiguration {
    ActivityConfiguration(for: JobActivityAttributes.self) { context in
      VStack(alignment: .leading, spacing: 12) {
        HStack {
          RelayMark(size: 28)
          Text(context.attributes.name).font(.headline).lineLimit(1)
          Spacer()
          Text(context.state.state).font(.caption.weight(.semibold)).foregroundStyle(
            Color("Accent"))
        }
        HStack {
          Text("\(context.attributes.host) / #\(context.attributes.number)").font(.caption)
            .lineLimit(1).truncationMode(.middle)
          Spacer(minLength: 8)
          Text("\(context.state.runtime) elapsed").font(.caption.monospacedDigit())
            .lineLimit(1).layoutPriority(1)
        }
        HStack {
          ActivityUpdatedLabel(updatedAt: context.state.updatedAt, stale: context.isStale)
            .foregroundStyle(Color("InkSecondary"))
          Spacer(minLength: 12)
          StopFollowingButton(activityID: context.activityID, color: Color("Accent"))
        }
      }.foregroundStyle(Color("Ink")).padding(20)
        .activityBackgroundTint(Color("Surface")).activitySystemActionForegroundColor(
          Color("Ink")
        )
        .widgetURL(context.attributes.url)
    } dynamicIsland: { context in
      DynamicIsland {
        DynamicIslandExpandedRegion(.leading) { RelayMark(size: 26) }
        DynamicIslandExpandedRegion(.trailing) {
          Text(context.state.state).font(.caption.weight(.semibold))
            .foregroundStyle(Color("Accent")).lineLimit(1).minimumScaleFactor(0.8)
            .frame(minHeight: 26)
        }
        DynamicIslandExpandedRegion(.bottom) {
          VStack(alignment: .leading, spacing: 8) {
            Text(context.attributes.name).font(.headline).lineLimit(1).truncationMode(.middle)
            HStack(spacing: 12) {
              Text("\(context.attributes.host) / #\(context.attributes.number)")
                .lineLimit(1).truncationMode(.middle)
              Spacer(minLength: 0)
              Text("\(context.state.runtime) elapsed").monospacedDigit()
                .lineLimit(1).layoutPriority(1)
            }.font(.caption).foregroundStyle(.white.opacity(0.8))
            HStack(spacing: 12) {
              ActivityUpdatedLabel(updatedAt: context.state.updatedAt, stale: context.isStale)
                .foregroundStyle(.white.opacity(0.7))
              Spacer(minLength: 0)
              StopFollowingButton(activityID: context.activityID, color: .white)
            }
          }.foregroundStyle(.white)
        }
      } compactLeading: {
        RelayMark(size: 22)
      } compactTrailing: {
        Image(systemName: context.state.ended ? "checkmark" : "waveform.path").foregroundStyle(
          Color("Accent"))
      } minimal: {
        RelayMark(size: 22)
      }
      .contentMargins(.horizontal, 24, for: .expanded)
      .contentMargins(.top, 12, for: .expanded)
      .contentMargins(.bottom, 18, for: .expanded)
      .widgetURL(context.attributes.url)
    }
  }
}

private struct ActivityUpdatedLabel: View {
  var updatedAt: Date
  var stale: Bool
  var body: some View {
    VStack(alignment: .leading, spacing: 2) {
      Text(stale ? "Update overdue" : "Updated")
      Text(updatedAt, style: .time)
    }.font(.caption2).lineLimit(1)
  }
}

private struct StopFollowingButton: View {
  var activityID: String
  var color: Color
  var body: some View {
    Button(intent: StopFollowingJobIntent(activityID: activityID)) {
      Label("Stop following", systemImage: "xmark")
        .font(.caption.weight(.semibold)).lineLimit(1)
        .frame(minHeight: 32)
    }
    .buttonStyle(.bordered).buttonBorderShape(.capsule).tint(color)
    .accessibilityHint("The job keeps running")
    .accessibilityIdentifier("stopFollowingActivity")
  }
}
