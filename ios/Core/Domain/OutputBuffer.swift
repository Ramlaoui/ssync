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
