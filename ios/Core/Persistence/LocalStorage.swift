import Foundation
import Security
import SwiftData

enum CredentialStore {
  static func read(_ id: UUID) -> String {
    let query: [String: Any] = [
      kSecClass as String: kSecClassGenericPassword,
      kSecAttrService as String: "com.ssync.mobile.connection",
      kSecAttrAccount as String: id.uuidString,
      kSecReturnData as String: true,
      kSecMatchLimit as String: kSecMatchLimitOne,
    ]
    var item: CFTypeRef?
    guard SecItemCopyMatching(query as CFDictionary, &item) == errSecSuccess,
      let data = item as? Data
    else { return "" }
    return String(decoding: data, as: UTF8.self)
  }
  static func save(_ value: String, for id: UUID) throws {
    let query: [String: Any] = [
      kSecClass as String: kSecClassGenericPassword,
      kSecAttrService as String: "com.ssync.mobile.connection",
      kSecAttrAccount as String: id.uuidString,
    ]
    if value.isEmpty {
      SecItemDelete(query as CFDictionary)
      return
    }
    let data = Data(value.utf8)
    let status = SecItemUpdate(
      query as CFDictionary, [kSecValueData as String: data] as CFDictionary)
    if status == errSecItemNotFound {
      var item = query
      item[kSecValueData as String] = data
      item[kSecAttrAccessible as String] = kSecAttrAccessibleWhenUnlockedThisDeviceOnly
      let added = SecItemAdd(item as CFDictionary, nil)
      guard added == errSecSuccess else {
        throw APIError(
          status: Int(added), message: "The ssync API Key could not be saved securely.")
      }
    } else if status != errSecSuccess {
      throw APIError(
        status: Int(status), message: "The ssync API Key could not be updated securely.")
    }
  }
}

@Model final class SavedDraft {
  @Attribute(.unique) var id: UUID
  var connectionID: UUID
  var name: String
  var updatedAt: Date
  var isTemplate: Bool
  var payload: Data

  init(id: UUID, connectionID: UUID, name: String, isTemplate: Bool, payload: Data) {
    self.id = id
    self.connectionID = connectionID
    self.name = name
    self.updatedAt = .now
    self.isTemplate = isTemplate
    self.payload = payload
  }
}

struct SavedSession: Codable {
  var version = 1
  var connection: Connection
  var hosts: [Host]
  var jobs: [Job]
  var partitions: [PartitionSnapshot]
  var watchers: [Watcher]
  var arrays: [ArrayGroup]
  var receivedAt: Date?
  var pins: Set<JobID>
  var acknowledgements: Set<JobID>
}

@MainActor final class LocalStorage {
  let container: ModelContainer
  let root: URL

  init(inMemory: Bool = false) throws {
    container = try ModelContainer(
      for: SavedDraft.self, configurations: ModelConfiguration(isStoredInMemoryOnly: inMemory))
    root = FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask)[0]
      .appending(path: "ssync", directoryHint: .isDirectory)
    if !inMemory {
      try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
    }
  }
  func snapshot(_ id: UUID) -> SavedSession? {
    guard let data = try? Data(contentsOf: root.appending(path: "\(id).json")) else { return nil }
    return try? JSONDecoder().decode(SavedSession.self, from: data)
  }
  func save(_ session: SavedSession) throws {
    let data = try JSONEncoder().encode(session)
    try data.write(
      to: root.appending(path: "\(session.connection.id).json"),
      options: [.atomic, .completeFileProtectionUntilFirstUserAuthentication])
  }
  func removeSnapshot(_ id: UUID) {
    try? FileManager.default.removeItem(at: root.appending(path: "\(id).json"))
  }
  func drafts(connectionID: UUID) -> [SavedDraft] {
    let descriptor = FetchDescriptor<SavedDraft>(
      predicate: #Predicate { $0.connectionID == connectionID },
      sortBy: [SortDescriptor(\.updatedAt, order: .reverse)])
    return (try? container.mainContext.fetch(descriptor)) ?? []
  }
  func saveDraft(_ draft: LaunchDraft, connectionID: UUID, template: Bool = false) throws {
    let payload = try JSONEncoder().encode(draft)
    if let saved = drafts(connectionID: connectionID).first(where: { $0.id == draft.id }) {
      saved.name = draft.name
      saved.payload = payload
      saved.updatedAt = .now
      saved.isTemplate = template
    } else {
      container.mainContext.insert(
        SavedDraft(
          id: draft.id, connectionID: connectionID, name: draft.name, isTemplate: template,
          payload: payload))
    }
    try container.mainContext.save()
  }
  func deleteDraft(_ id: UUID, connectionID: UUID) throws {
    if let saved = drafts(connectionID: connectionID).first(where: { $0.id == id }) {
      container.mainContext.delete(saved)
      try container.mainContext.save()
    }
  }
}
