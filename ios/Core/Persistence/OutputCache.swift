import CryptoKit
import Foundation

struct SavedOutput: Codable {
  var text: String
  var truncated: Bool
  var receivedAt: Date
}

extension LocalStorage {
  func outputURL(connectionID: UUID, job: JobID, source: String) -> URL {
    let identity = "\(connectionID)|\(job.host)|\(job.number)|\(source)"
    let key = SHA256.hash(data: Data(identity.utf8)).map { String(format: "%02x", $0) }.joined()
    return root.appending(path: "output-\(connectionID)-\(key).json")
  }
  func removeOutputs(connectionID: UUID) {
    guard
      let files = try? FileManager.default.contentsOfDirectory(
        at: root, includingPropertiesForKeys: nil)
    else { return }
    for file in files where file.lastPathComponent.hasPrefix("output-\(connectionID)-") {
      try? FileManager.default.removeItem(at: file)
    }
  }
}
