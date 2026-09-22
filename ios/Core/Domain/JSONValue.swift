import Foundation

/// Preserves server fields that are not yet understood by the client, including manifests.
enum JSONValue: Codable, Hashable, Sendable {
  case string(String)
  case number(Double)
  case bool(Bool)
  case object([String: JSONValue])
  case array([JSONValue])
  case null

  init(from decoder: any Decoder) throws {
    let c = try decoder.singleValueContainer()
    if c.decodeNil() {
      self = .null
    } else if let v = try? c.decode(Bool.self) {
      self = .bool(v)
    } else if let v = try? c.decode(Double.self) {
      self = .number(v)
    } else if let v = try? c.decode(String.self) {
      self = .string(v)
    } else if let v = try? c.decode([JSONValue].self) {
      self = .array(v)
    } else {
      self = .object(try c.decode([String: JSONValue].self))
    }
  }

  func encode(to encoder: any Encoder) throws {
    var c = encoder.singleValueContainer()
    switch self {
    case .string(let v): try c.encode(v)
    case .number(let v): try c.encode(v)
    case .bool(let v): try c.encode(v)
    case .object(let v): try c.encode(v)
    case .array(let v): try c.encode(v)
    case .null: try c.encodeNil()
    }
  }

  var string: String? {
    switch self {
    case .string(let v): v
    case .number(let v): v.rounded() == v ? String(format: "%.0f", v) : String(v)
    case .bool(let v): v ? "true" : "false"
    default: nil
    }
  }
  var object: [String: JSONValue] { if case .object(let value) = self { value } else { [:] } }
  var array: [JSONValue] { if case .array(let value) = self { value } else { [] } }
  var bool: Bool { if case .bool(let value) = self { value } else { false } }
  var int: Int? { string.flatMap(Int.init) }
  var pretty: String {
    let encoder = JSONEncoder()
    encoder.outputFormatting = [.prettyPrinted, .sortedKeys, .withoutEscapingSlashes]
    return (try? String(decoding: encoder.encode(self), as: UTF8.self)) ?? ""
  }
}

extension Dictionary where Key == String, Value == JSONValue {
  func text(_ key: String, fallback: String = "") -> String { self[key]?.string ?? fallback }
  func integer(_ key: String, fallback: Int = 0) -> Int { self[key]?.int ?? fallback }
  func flag(_ key: String) -> Bool { self[key]?.bool ?? false }
}
