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
    let scratchDir: String?
    let slurmDefaults: HostSlurmDefaults?
    
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
        case scratchDir = "scratch_dir"
        case slurmDefaults = "slurm_defaults"
    }

    init(
        id: String,
        name: String,
        hostname: String,
        username: String? = nil,
        port: Int = 22,
        workDir: String,
        isDefault: Bool = false,
        isAvailable: Bool = true,
        lastError: String? = nil,
        scratchDir: String? = nil,
        slurmDefaults: HostSlurmDefaults? = nil
    ) {
        self.id = id
        self.name = name
        self.hostname = hostname
        self.username = username
        self.port = port
        self.workDir = workDir
        self.isDefault = isDefault
        self.isAvailable = isAvailable
        self.lastError = lastError
        self.scratchDir = scratchDir
        self.slurmDefaults = slurmDefaults
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)

        hostname = try container.decode(String.self, forKey: .hostname)
        id = try container.decodeIfPresent(String.self, forKey: .id) ?? hostname

        let decodedName = try container.decodeIfPresent(String.self, forKey: .name)
        name = decodedName ?? hostname.components(separatedBy: ".").first ?? hostname

        username = try container.decodeIfPresent(String.self, forKey: .username)
        port = try container.decodeIfPresent(Int.self, forKey: .port) ?? 22
        workDir = try container.decodeIfPresent(String.self, forKey: .workDir) ?? "[CONFIGURED]"
        isDefault = try container.decodeIfPresent(Bool.self, forKey: .isDefault) ?? false
        isAvailable = try container.decodeIfPresent(Bool.self, forKey: .isAvailable) ?? true
        lastError = try container.decodeIfPresent(String.self, forKey: .lastError)
        scratchDir = try container.decodeIfPresent(String.self, forKey: .scratchDir)
        slurmDefaults = try container.decodeIfPresent(HostSlurmDefaults.self, forKey: .slurmDefaults)
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

struct HostSlurmDefaults: Codable, Hashable {
    let partition: String?
    let account: String?
    let cpus: Int?
    let mem: Int?
    let time: String?
    let nodes: Int?
    let ntasksPerNode: Int?
    let gpusPerNode: Int?
    let gres: String?

    enum CodingKeys: String, CodingKey {
        case partition
        case account
        case cpus
        case mem
        case time
        case nodes
        case ntasksPerNode = "ntasks_per_node"
        case gpusPerNode = "gpus_per_node"
        case gres
    }
}
