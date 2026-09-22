import ActivityKit
import Foundation

struct SystemSnapshot: Codable, Sendable {
  var connectionID: UUID?
  var name: String
  var updatedAt: Date?
  var running: Int
  var pending: Int
  var attention: Int
  var jobs: [SystemJob]
  var partitions: [SystemPartition]
  static let empty = SystemSnapshot(
    name: "Open ssync to connect", running: 0, pending: 0, attention: 0, jobs: [], partitions: [])
  static let group = "group.com.ssync.mobile"
  static var fileURL: URL? {
    FileManager.default.containerURL(forSecurityApplicationGroupIdentifier: group)?.appending(
      path: "snapshot.json")
  }
  static func read() -> Self {
    guard let url = fileURL, let data = try? Data(contentsOf: url),
      let value = try? JSONDecoder().decode(Self.self, from: data)
    else { return .empty }
    return value
  }
  func write() throws {
    guard let url = Self.fileURL else { return }
    try JSONEncoder().encode(self).write(
      to: url, options: [.atomic, .completeFileProtectionUntilFirstUserAuthentication])
  }
}

struct SystemJob: Codable, Identifiable, Sendable {
  var host: String
  var number: String
  var name: String
  var state: String
  var runtime: String
  var pinned: Bool
  var id: String { "\(host)::\(number)" }
  func url(connection: UUID?) -> URL {
    var parts = URLComponents()
    parts.scheme = "ssync"
    parts.host = "job"
    parts.queryItems = [
      URLQueryItem(name: "host", value: host), URLQueryItem(name: "id", value: number),
      URLQueryItem(name: "connection", value: connection?.uuidString),
    ]
    return parts.url!
  }
}

struct SystemPartition: Codable, Identifiable, Sendable {
  var host: String
  var name: String
  var allocated: Int
  var idle: Int
  var other: Int
  var total: Int
  var updatedAt: Date?
  var id: String { "\(host)::\(name)" }
}

struct JobActivityAttributes: ActivityAttributes {
  struct ContentState: Codable, Hashable {
    var state: String
    var runtime: String
    var updatedAt: Date
    var ended: Bool
  }
  var host: String
  var number: String
  var name: String
  var connectionID: UUID
  var url: URL {
    SystemJob(host: host, number: number, name: name, state: "", runtime: "", pinned: true).url(
      connection: connectionID)
  }
}
