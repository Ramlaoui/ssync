import SwiftUI

enum Theme {
  static let canvas = Color("Canvas")
  static let surface = Color("Surface")
  static let ink = Color("Ink")
  static let secondary = Color("InkSecondary")
  static let accent = Color("Accent")
  static let onAccent = Color("OnAccent")
  static let line = Color("Separator")
  static let green = Color("Running")
  static let amber = Color("Warning")
  static let red = Color("Danger")
  static let soft = Color("AccentSoft")
  static let panel = Color(red: 0.09, green: 0.13, blue: 0.22)
}
extension JobState {
  var color: Color {
    switch self {
    case .running, .completed: Theme.green
    case .pending: Theme.amber
    case .failed, .timedOut: Theme.red
    case .cancelled, .unknown: Theme.secondary
    }
  }
}
struct StatePill: View {
  var state: JobState
  var body: some View {
    Label(state.label, systemImage: state.symbol)
      .font(.caption.weight(.semibold)).foregroundStyle(state.color)
      .padding(.horizontal, 9).padding(.vertical, 6)
      .background(state.color.opacity(0.11), in: Capsule())
  }
}
struct Eyebrow: View {
  var title: String
  var color: Color = Theme.secondary
  var body: some View {
    Text(title.uppercased()).font(.caption2.weight(.bold)).tracking(1.4).foregroundStyle(
      color)
  }
}
struct SectionHeading: View {
  var title: String
  var detail: String? = nil
  var body: some View {
    HStack(alignment: .firstTextBaseline) {
      Text(title).font(.headline)
      Spacer()
      if let detail { Text(detail).font(.caption).foregroundStyle(Theme.secondary) }
    }.padding(.top, 8)
  }
}
struct Paper<Content: View>: View {
  var padding: CGFloat = 18
  @ViewBuilder var content: Content
  var body: some View {
    content.padding(padding).frame(maxWidth: .infinity, alignment: .leading)
      .background(Theme.surface, in: RoundedRectangle(cornerRadius: 20))
      .overlay(RoundedRectangle(cornerRadius: 20).strokeBorder(Theme.line, lineWidth: 0.7))
  }
}
struct PrimaryButtonStyle: ButtonStyle {
  func makeBody(configuration: Configuration) -> some View {
    configuration.label.font(.headline).frame(maxWidth: .infinity).padding(.vertical, 16)
      .background(Theme.accent, in: RoundedRectangle(cornerRadius: 15))
      .foregroundStyle(Theme.onAccent)
      .opacity(configuration.isPressed ? 0.75 : 1)
  }
}
struct Notice: View {
  var title: String
  var detail: String? = nil
  var symbol = "info.circle"
  var warning = false
  var body: some View {
    HStack(alignment: .top, spacing: 12) {
      Image(systemName: symbol).foregroundStyle(warning ? Theme.amber : Theme.accent)
      VStack(alignment: .leading, spacing: 5) {
        Text(title).font(.subheadline.weight(.semibold))
        if let detail { Text(detail).font(.caption).foregroundStyle(Theme.secondary) }
      }
      Spacer(minLength: 0)
    }.padding(14).background(
      (warning ? Theme.amber : Theme.accent).opacity(0.08), in: RoundedRectangle(cornerRadius: 14))
  }
}
struct EmptyState: View {
  var title: String
  var detail: String
  var symbol = "tray"
  var body: some View {
    VStack(spacing: 14) {
      Image(systemName: symbol).font(.system(size: 38, weight: .light)).foregroundStyle(
        Theme.accent)
      Text(title).font(.title3.weight(.semibold))
      Text(detail).font(.subheadline).foregroundStyle(Theme.secondary).multilineTextAlignment(
        .center)
    }.frame(maxWidth: .infinity).padding(.vertical, 38).padding(.horizontal, 20)
  }
}
struct DetailRow: View {
  var name: String
  var value: String
  var monospaced = false
  var body: some View {
    LabeledContent {
      Text(value.isEmpty ? "Unavailable" : value)
        .font(monospaced ? .system(.subheadline, design: .monospaced) : .subheadline)
        .foregroundStyle(Theme.ink).multilineTextAlignment(.trailing).textSelection(.enabled)
    } label: {
      Text(name).font(.subheadline).foregroundStyle(Theme.secondary)
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
      HStack(spacing: 2) {
        if allocated > 0 {
          Rectangle().fill(Theme.accent).frame(
            width: max(0, geometry.size.width * CGFloat(allocated) / denominator - 1))
        }
        if idle > 0 {
          Rectangle().fill(Theme.green.opacity(0.35)).frame(
            width: max(0, geometry.size.width * CGFloat(idle) / denominator - 1))
        }
        if other > 0 {
          Rectangle().fill(Theme.amber.opacity(0.6)).frame(
            width: max(0, geometry.size.width * CGFloat(other) / denominator - 1))
        }
      }
    }.frame(height: 9).background(Theme.line).clipShape(Capsule())
      .accessibilityLabel("\(allocated) allocated, \(idle) idle, \(other) other, \(total) total")
  }
}
struct Screen<Content: View>: View {
  @ViewBuilder var content: Content
  var body: some View {
    ScrollView {
      VStack(alignment: .leading, spacing: 18) { content }
        .frame(maxWidth: 760).padding(20).frame(maxWidth: .infinity)
    }.background(Theme.canvas).foregroundStyle(Theme.ink)
  }
}
struct JobRow: View {
  var job: Job
  var pinned = false
  var body: some View {
    let shape = RoundedRectangle(cornerRadius: 12)
    HStack(spacing: 13) {
      Rectangle().fill(job.state.color).frame(width: 4)
      VStack(alignment: .leading, spacing: 7) {
        HStack {
          Text(job.name).font(.subheadline.weight(.semibold)).lineLimit(1)
          if pinned { Image(systemName: "pin.fill").font(.caption2).foregroundStyle(Theme.accent) }
          Spacer(minLength: 0)
          Image(systemName: "chevron.right").font(.caption2.weight(.semibold)).foregroundStyle(
            Theme.secondary)
        }
        HStack {
          Text("#\(job.number)").font(.system(.caption, design: .monospaced))
          Text(job.state.label).foregroundStyle(job.state.color)
          Spacer(minLength: 0)
          Text(job.fields.text("cpus") + " CPU").lineLimit(1)
        }.font(.caption).foregroundStyle(Theme.secondary)
        Text(job.subtitle).font(.caption).foregroundStyle(Theme.secondary).lineLimit(2)
      }.padding(.vertical, 15).padding(.trailing, 14)
    }
    .fixedSize(horizontal: false, vertical: true).frame(minHeight: 96)
    .background(Theme.surface)
    .clipShape(shape)
    .overlay(shape.strokeBorder(Theme.line, lineWidth: 0.6))
    .contentShape(shape)
    .accessibilityElement(children: .combine)
  }
}
