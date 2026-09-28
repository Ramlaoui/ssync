import SwiftUI

enum Theme {
  static let canvas = Color("Canvas")
  static let surface = Color("Surface")
  static let ink = Color("Ink")
  static let secondary = Color("InkSecondary")
  static let accent = Color("Accent")
  static let onAccent = Color("OnAccent")
  static let line = Color("Separator")
  static let green = Color.green
  static let amber = Color("Warning")
  static let red = Color("Danger")
  static let soft = Color("AccentSoft")
  static let code = Color("CodeCanvas")
}
extension JobState {
  var color: Color {
    switch self {
    case .running: Theme.accent
    case .completed: Theme.green
    case .pending: Theme.amber
    case .failed, .timedOut: Theme.red
    case .cancelled, .unknown: Color.secondary
    }
  }
}
struct StatePill: View {
  var state: JobState
  var body: some View {
    Label(state.label, systemImage: state.symbol)
      .font(.caption.weight(.semibold)).foregroundStyle(state.color)
      .padding(.horizontal, 8).padding(.vertical, 4)
      .background(state.color.opacity(0.12), in: Capsule())
  }
}
/// A compact, list-native job row: state glyph, name, one line of identity, trailing time.
struct JobRow: View {
  var job: Job
  var pinned = false
  var showHost = true
  var body: some View {
    HStack(spacing: 12) {
      Image(systemName: job.state.symbol).font(.body).foregroundStyle(job.state.color)
        .frame(width: 22)
      VStack(alignment: .leading, spacing: 3) {
        HStack(spacing: 5) {
          Text(job.name).font(.body.weight(.medium)).lineLimit(1)
          if pinned {
            Image(systemName: "pin.fill").font(.caption2).foregroundStyle(.secondary)
              .accessibilityLabel("Pinned")
          }
        }
        Text(identity).font(.caption).foregroundStyle(.secondary).lineLimit(1)
      }
      Spacer(minLength: 8)
      Text(trailing).font(.subheadline.monospacedDigit()).foregroundStyle(.secondary)
        .lineLimit(1)
    }
    .padding(.vertical, 2)
    .accessibilityElement(children: .combine)
    .accessibilityValue(job.state.label)
  }
  private var identity: String {
    [showHost ? job.host : nil, "#\(job.number)", job.partition.isEmpty ? nil : job.partition]
      .compactMap { $0 }.joined(separator: " · ")
  }
  private var trailing: String {
    switch job.state {
    case .pending: job.fields.text("reason", fallback: "Queued")
    case .running: Format.duration(job.runtime)
    default: job.state.label
    }
  }
}
struct ArrayRow: View {
  var group: ArrayGroup
  var body: some View {
    HStack(spacing: 12) {
      Image(systemName: "square.grid.3x3.fill").foregroundStyle(
        group.running_count > 0 ? Theme.accent : group.failed_count > 0 ? Theme.red : Theme.amber
      ).frame(width: 22)
      VStack(alignment: .leading, spacing: 3) {
        Text(group.job_name).font(.body.weight(.medium)).lineLimit(1)
        Text("\(group.hostname) · #\(group.array_job_id) · \(group.total_tasks) tasks")
          .font(.caption).foregroundStyle(.secondary).lineLimit(1)
      }
      Spacer(minLength: 8)
      Text(summary).font(.subheadline.monospacedDigit()).foregroundStyle(.secondary)
    }
    .padding(.vertical, 2)
    .accessibilityElement(children: .combine)
  }
  private var summary: String {
    if group.running_count > 0 { return "\(group.running_count) running" }
    if group.pending_count > 0 { return "\(group.pending_count) queued" }
    return "\(group.completed_count)/\(group.total_tasks) done"
  }
}
struct DetailRow: View {
  var name: String
  var value: String
  var monospaced = false
  var body: some View {
    LabeledContent(name) {
      Text(value)
        .font(monospaced ? .system(.subheadline, design: .monospaced) : .subheadline)
        .multilineTextAlignment(.trailing).textSelection(.enabled)
    }
  }
}
struct CapacityBar: View {
  var allocated: Int
  var idle: Int
  var other: Int = 0
  var total: Int
  var body: some View {
    GeometryReader { geometry in
      let denominator = CGFloat(max(total, allocated + idle + other, 1))
      HStack(spacing: 1.5) {
        segment(allocated, Theme.accent, geometry.size.width, denominator)
        segment(idle, Theme.green.opacity(0.45), geometry.size.width, denominator)
        segment(other, Theme.amber.opacity(0.7), geometry.size.width, denominator)
      }
    }.frame(height: 6).background(Color.secondary.opacity(0.15)).clipShape(Capsule())
      .accessibilityElement()
      .accessibilityLabel("\(allocated) allocated, \(idle) idle, \(other) other, \(total) total")
  }
  @ViewBuilder private func segment(
    _ count: Int, _ color: Color, _ width: CGFloat, _ denominator: CGFloat
  ) -> some View {
    if count > 0 {
      Rectangle().fill(color).frame(width: max(0, width * CGFloat(count) / denominator - 1.5))
    }
  }
}
/// A filter chip used for the quick state filters above lists.
struct FilterChip: View {
  var title: String
  var count: Int
  var color: Color
  var selected: Bool
  var action: () -> Void
  var body: some View {
    Button(action: action) {
      HStack(spacing: 6) {
        Text("\(count)").font(.subheadline.weight(.bold).monospacedDigit())
          .contentTransition(.numericText())
        Text(title).font(.subheadline)
      }
      .foregroundStyle(selected ? Color.white : color)
      .padding(.horizontal, 12).padding(.vertical, 7)
      .background(selected ? color : color.opacity(0.12), in: Capsule())
    }
    .buttonStyle(.plain)
    .accessibilityAddTraits(selected ? .isSelected : [])
  }
}
