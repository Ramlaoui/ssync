import Foundation

struct OutputBuffer {
  static let limit = 524_288
  private(set) var text = ""
  private(set) var trimmed = false
  mutating func replace(_ value: String, truncated: Bool = false) {
    trimmed = truncated
    text = value
    bound()
  }
  mutating func append(_ value: String) {
    text += value
    bound()
  }
  private mutating func bound() {
    if text.utf8.count > Self.limit {
      text = String(decoding: text.utf8.suffix(Self.limit), as: UTF8.self)
      if let newline = text.firstIndex(of: "\n") {
        text = String(text[text.index(after: newline)...])
      }
      trimmed = true
    }
  }
  func matchingLines(_ query: String) -> [Int] {
    guard !query.isEmpty else { return [] }
    return text.components(separatedBy: "\n").enumerated().compactMap {
      $0.element.localizedCaseInsensitiveContains(query) ? $0.offset : nil
    }
  }
}

struct OutputBookmark: Codable, Identifiable {
  var id = UUID()
  var source: String
  var excerpt: String
  var createdAt = Date.now
}

/// Splits a byte stream into lines, keeping the empty lines that end SSE events.
/// `URLSession.AsyncBytes.lines` drops empty lines, so events would never dispatch.
struct SSELineSplitter {
  private var pending: [UInt8] = []
  private var sawCarriageReturn = false
  mutating func feed(_ byte: UInt8) -> String? {
    if byte == 0x0A, sawCarriageReturn {
      sawCarriageReturn = false
      return nil
    }
    sawCarriageReturn = byte == 0x0D
    guard byte == 0x0A || byte == 0x0D else {
      pending.append(byte)
      return nil
    }
    defer { pending.removeAll(keepingCapacity: true) }
    return String(decoding: pending, as: UTF8.self)
  }
}

struct SSEParser {
  private var data: [String] = []
  mutating func consume(_ line: String) -> String? {
    if line.isEmpty {
      defer { data.removeAll(keepingCapacity: true) }
      return data.isEmpty ? nil : data.joined(separator: "\n")
    }
    if line.hasPrefix("data:") {
      var value = String(line.dropFirst(5))
      if value.first == " " { value.removeFirst() }
      data.append(value)
    }
    return nil
  }
}
