import Foundation

struct Host: Codable, Identifiable, Hashable {
    let id: String
    let name: String
    let hostname: String
    let username: String?
    let port: Int
    let workDir: String
    let isDefault: Bool
    let isAvailable: Bool
    let lastError: String?
    
    enum CodingKeys: String, CodingKey {
        case id
        case name
        case hostname
        case username
        case port
        case workDir = "work_dir"
        case isDefault = "is_default"
        case isAvailable = "is_available"
        case lastError = "last_error"
    }
    
    var displayName: String {
        name.isEmpty ? hostname : name
    }
    
    var connectionString: String {
        if let username = username {
            return "\(username)@\(hostname):\(port)"
        }
        return "\(hostname):\(port)"
    }
}