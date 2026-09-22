import SwiftUI

struct RelayMark: View {
  var size: CGFloat = 32
  var color: Color = Color("Accent")
  var body: some View {
    Canvas { context, dimensions in
      let scale = dimensions.width / 100
      var upper = Path()
      upper.move(to: CGPoint(x: 76 * scale, y: 22 * scale))
      upper.addLine(to: CGPoint(x: 43 * scale, y: 22 * scale))
      upper.addCurve(
        to: CGPoint(x: 22 * scale, y: 42 * scale), control1: CGPoint(x: 30 * scale, y: 22 * scale),
        control2: CGPoint(x: 22 * scale, y: 30 * scale))
      upper.addLine(to: CGPoint(x: 55 * scale, y: 42 * scale))
      var lower = Path()
      lower.move(to: CGPoint(x: 24 * scale, y: 78 * scale))
      lower.addLine(to: CGPoint(x: 57 * scale, y: 78 * scale))
      lower.addCurve(
        to: CGPoint(x: 78 * scale, y: 58 * scale), control1: CGPoint(x: 70 * scale, y: 78 * scale),
        control2: CGPoint(x: 78 * scale, y: 70 * scale))
      lower.addLine(to: CGPoint(x: 45 * scale, y: 58 * scale))
      context.stroke(
        upper, with: .color(color),
        style: StrokeStyle(lineWidth: 10 * scale, lineCap: .round, lineJoin: .round))
      context.stroke(
        lower, with: .color(color),
        style: StrokeStyle(lineWidth: 10 * scale, lineCap: .round, lineJoin: .round))
    }
    .frame(width: size, height: size)
    .accessibilityHidden(true)
  }
}
