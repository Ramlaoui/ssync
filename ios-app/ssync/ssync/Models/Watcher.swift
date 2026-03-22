import Foundation

// MARK: - JSON Value

enum JSONValue: Codable, Hashable {
    case string(String)
    case number(Double)
    case bool(Bool)
    case object([String: JSONValue])
    case array([JSONValue])
    case null

    init(from decoder: Decoder) throws {
        let container = try decoder.singleValueContainer()
        if container.decodeNil() {
            self = .null
        } else if let value = try? container.decode(Bool.self) {
            self = .bool(value)
        } else if let value = try? container.decode(Double.self) {
            self = .number(value)
        } else if let value = try? container.decode(String.self) {
            self = .string(value)
        } else if let value = try? container.decode([String: JSONValue].self) {
            self = .object(value)
        } else if let value = try? container.decode([JSONValue].self) {
            self = .array(value)
        } else {
            throw DecodingError.dataCorruptedError(
                in: container,
                debugDescription: "Unsupported JSON value"
            )
        }
    }

    func encode(to encoder: Encoder) throws {
        var container = encoder.singleValueContainer()
        switch self {
        case .string(let value):
            try container.encode(value)
        case .number(let value):
            try container.encode(value)
        case .bool(let value):
            try container.encode(value)
        case .object(let value):
            try container.encode(value)
        case .array(let value):
            try container.encode(value)
        case .null:
            try container.encodeNil()
        }
    }

    var displayValue: String {
        switch self {
        case .string(let value):
            return value
        case .number(let value):
            return String(value)
        case .bool(let value):
            return value ? "true" : "false"
        case .object(let value):
            return JSONValue.prettyPrinted(value) ?? "{...}"
        case .array(let value):
            return JSONValue.prettyPrinted(value) ?? "[...]"
        case .null:
            return "null"
        }
    }

    private static func prettyPrinted<T: Encodable>(_ value: T) -> String? {
        guard let data = try? JSONEncoder().encode(value) else { return nil }
        return String(data: data, encoding: .utf8)
    }

    static func decodeObject(from jsonString: String) -> [String: JSONValue]? {
        guard let data = jsonString.data(using: .utf8) else { return nil }
        if let object = try? JSONDecoder().decode([String: JSONValue].self, from: data) {
            return object
        }
        guard let raw = try? JSONSerialization.jsonObject(with: data, options: []) else {
            return nil
        }
        return JSONValue.fromAny(raw)?.objectValue
    }

    private static func fromAny(_ value: Any) -> JSONValue? {
        switch value {
        case let string as String:
            return .string(string)
        case let number as NSNumber:
            if CFGetTypeID(number) == CFBooleanGetTypeID() {
                return .bool(number.boolValue)
            }
            return .number(number.doubleValue)
        case let array as [Any]:
            return .array(array.compactMap { fromAny($0) })
        case let dict as [String: Any]:
            var object: [String: JSONValue] = [:]
            for (key, value) in dict {
                if let converted = fromAny(value) {
                    object[key] = converted
                }
            }
            return .object(object)
        case _ as NSNull:
            return .null
        default:
            return nil
        }
    }

    private var objectValue: [String: JSONValue]? {
        if case .object(let value) = self {
            return value
        }
        return nil
    }
}

// MARK: - Watcher Models

enum WatcherState: String, Codable, CaseIterable {
    case pending
    case active
    case paused
    case `static`
    case completed
    case failed
    case disabled
    case triggered
    case unknown

    var displayName: String {
        switch self {
        case .pending: return "Pending"
        case .active: return "Active"
        case .paused: return "Paused"
        case .static: return "Static"
        case .completed: return "Completed"
        case .failed: return "Failed"
        case .disabled: return "Disabled"
        case .triggered: return "Triggered"
        case .unknown: return "Unknown"
        }
    }

    static func from(_ raw: String) -> WatcherState {
        WatcherState(rawValue: raw.lowercased()) ?? .unknown
    }
}

enum WatcherActionType: String, CaseIterable, Identifiable {
    case cancelJob = "cancel_job"
    case resubmit = "resubmit"
    case notifyEmail = "notify_email"
    case notifySlack = "notify_slack"
    case runCommand = "run_command"
    case storeMetric = "store_metric"
    case pauseWatcher = "pause_watcher"
    case logEvent = "log_event"

    var id: String { rawValue }

    var displayName: String {
        switch self {
        case .cancelJob: return "Cancel Job"
        case .resubmit: return "Resubmit"
        case .notifyEmail: return "Notify Email"
        case .notifySlack: return "Notify Slack"
        case .runCommand: return "Run Command"
        case .storeMetric: return "Store Metric"
        case .pauseWatcher: return "Pause Watcher"
        case .logEvent: return "Log Event"
        }
    }
}

struct WatcherAction: Decodable, Hashable {
    let type: String
    let params: [String: JSONValue]?
    let config: [String: JSONValue]?
    let condition: String?

    enum CodingKeys: String, CodingKey {
        case type
        case params
        case config
        case condition
    }

    init(type: String, params: [String: JSONValue]? = nil, config: [String: JSONValue]? = nil, condition: String? = nil) {
        self.type = type
        self.params = params
        self.config = config
        self.condition = condition
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        type = try container.decode(String.self, forKey: .type)
        condition = try container.decodeIfPresent(String.self, forKey: .condition)
        if let params = try container.decodeIfPresent([String: JSONValue].self, forKey: .params) {
            self.params = params
            self.config = nil
        } else if let config = try container.decodeIfPresent([String: JSONValue].self, forKey: .config) {
            self.params = nil
            self.config = config
        } else {
            self.params = nil
            self.config = nil
        }
    }

    var effectiveParams: [String: JSONValue]? {
        params ?? config
    }
}

struct Watcher: Decodable, Identifiable, Hashable {
    let id: Int
    let jobId: String
    let hostname: String
    let name: String
    let pattern: String
    let intervalSeconds: Int?
    let captures: [String]
    let condition: String?
    let actions: [WatcherAction]
    let state: String
    let triggerCount: Int?
    let lastCheck: Date?
    let lastPosition: Int?
    let createdAt: Date?
    let timerModeEnabled: Bool?
    let timerIntervalSeconds: Int?
    let timerModeActive: Bool?
    let variables: [String: String]?
    let isArrayTemplate: Bool?
    let arraySpec: String?
    let parentWatcherId: Int?
    let discoveredTaskCount: Int?
    let expectedTaskCount: Int?

    enum CodingKeys: String, CodingKey {
        case id
        case jobId = "job_id"
        case hostname
        case name
        case pattern
        case intervalSeconds = "interval_seconds"
        case captures
        case condition
        case actions
        case state
        case triggerCount = "trigger_count"
        case lastCheck = "last_check"
        case lastPosition = "last_position"
        case createdAt = "created_at"
        case timerModeEnabled = "timer_mode_enabled"
        case timerIntervalSeconds = "timer_interval_seconds"
        case timerModeActive = "timer_mode_active"
        case variables
        case isArrayTemplate = "is_array_template"
        case arraySpec = "array_spec"
        case parentWatcherId = "parent_watcher_id"
        case discoveredTaskCount = "discovered_task_count"
        case expectedTaskCount = "expected_task_count"
    }

    init(
        id: Int,
        jobId: String,
        hostname: String,
        name: String,
        pattern: String,
        intervalSeconds: Int?,
        captures: [String],
        condition: String?,
        actions: [WatcherAction],
        state: String,
        triggerCount: Int?,
        lastCheck: Date?,
        lastPosition: Int?,
        createdAt: Date?,
        timerModeEnabled: Bool?,
        timerIntervalSeconds: Int?,
        timerModeActive: Bool?,
        variables: [String: String]?,
        isArrayTemplate: Bool?,
        arraySpec: String?,
        parentWatcherId: Int?,
        discoveredTaskCount: Int?,
        expectedTaskCount: Int?
    ) {
        self.id = id
        self.jobId = jobId
        self.hostname = hostname
        self.name = name
        self.pattern = pattern
        self.intervalSeconds = intervalSeconds
        self.captures = captures
        self.condition = condition
        self.actions = actions
        self.state = state
        self.triggerCount = triggerCount
        self.lastCheck = lastCheck
        self.lastPosition = lastPosition
        self.createdAt = createdAt
        self.timerModeEnabled = timerModeEnabled
        self.timerIntervalSeconds = timerIntervalSeconds
        self.timerModeActive = timerModeActive
        self.variables = variables
        self.isArrayTemplate = isArrayTemplate
        self.arraySpec = arraySpec
        self.parentWatcherId = parentWatcherId
        self.discoveredTaskCount = discoveredTaskCount
        self.expectedTaskCount = expectedTaskCount
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        id = try container.decode(Int.self, forKey: .id)
        jobId = try container.decode(String.self, forKey: .jobId)
        hostname = try container.decodeIfPresent(String.self, forKey: .hostname) ?? ""
        name = try container.decodeIfPresent(String.self, forKey: .name) ?? "Watcher \(id)"
        pattern = try container.decodeIfPresent(String.self, forKey: .pattern) ?? ""
        intervalSeconds = try container.decodeIfPresent(Int.self, forKey: .intervalSeconds)
        captures = try container.decodeIfPresent([String].self, forKey: .captures) ?? []
        condition = try container.decodeIfPresent(String.self, forKey: .condition)
        actions = try container.decodeIfPresent([WatcherAction].self, forKey: .actions) ?? []
        state = try container.decodeIfPresent(String.self, forKey: .state) ?? "unknown"
        triggerCount = try container.decodeIfPresent(Int.self, forKey: .triggerCount)
        lastCheck = Watcher.parseDate(from: container, key: .lastCheck)
        lastPosition = try container.decodeIfPresent(Int.self, forKey: .lastPosition)
        createdAt = Watcher.parseDate(from: container, key: .createdAt)
        timerModeEnabled = try container.decodeIfPresent(Bool.self, forKey: .timerModeEnabled)
        timerIntervalSeconds = try container.decodeIfPresent(Int.self, forKey: .timerIntervalSeconds)
        timerModeActive = try container.decodeIfPresent(Bool.self, forKey: .timerModeActive)
        variables = try container.decodeIfPresent([String: String].self, forKey: .variables)
        isArrayTemplate = try container.decodeIfPresent(Bool.self, forKey: .isArrayTemplate)
        arraySpec = try container.decodeIfPresent(String.self, forKey: .arraySpec)
        parentWatcherId = try container.decodeIfPresent(Int.self, forKey: .parentWatcherId)
        discoveredTaskCount = try container.decodeIfPresent(Int.self, forKey: .discoveredTaskCount)
        expectedTaskCount = try container.decodeIfPresent(Int.self, forKey: .expectedTaskCount)
    }

    var stateEnum: WatcherState {
        WatcherState.from(state)
    }

    var hasVariables: Bool {
        guard let variables else { return false }
        return !variables.isEmpty
    }

    var lastCheckDisplay: String? {
        guard let lastCheck else { return nil }
        return Watcher.displayFormatter.string(from: lastCheck)
    }

    var createdAtDisplay: String? {
        guard let createdAt else { return nil }
        return Watcher.displayFormatter.string(from: createdAt)
    }

    private static func parseDate(from container: KeyedDecodingContainer<CodingKeys>, key: CodingKeys) -> Date? {
        if let raw = try? container.decodeIfPresent(String.self, forKey: key) {
            return parseDate(raw)
        }
        return nil
    }

    static func parseDate(_ raw: String?) -> Date? {
        guard let raw else { return nil }
        let trimmed = raw.trimmingCharacters(in: .whitespacesAndNewlines)
        if trimmed.isEmpty || trimmed == "None" || trimmed == "N/A" {
            return nil
        }
        if let date = isoFormatterWithFractionalSeconds.date(from: trimmed) {
            return date
        }
        if let date = isoFormatter.date(from: trimmed) {
            return date
        }
        return nil
    }

    private static let isoFormatterWithFractionalSeconds: ISO8601DateFormatter = {
        let formatter = ISO8601DateFormatter()
        formatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        return formatter
    }()

    private static let isoFormatter: ISO8601DateFormatter = {
        let formatter = ISO8601DateFormatter()
        formatter.formatOptions = [.withInternetDateTime]
        return formatter
    }()

    static let displayFormatter: DateFormatter = {
        let formatter = DateFormatter()
        formatter.dateStyle = .medium
        formatter.timeStyle = .short
        return formatter
    }()
}

struct WatcherEvent: Decodable, Identifiable, Hashable {
    let id: Int
    let watcherId: Int
    let watcherName: String
    let jobId: String
    let hostname: String
    let timestamp: Date?
    let matchedText: String?
    let capturedVars: [String: JSONValue]
    let actionType: String
    let actionResult: String?
    let success: Bool

    enum CodingKeys: String, CodingKey {
        case id
        case watcherId = "watcher_id"
        case watcherName = "watcher_name"
        case jobId = "job_id"
        case hostname
        case timestamp
        case matchedText = "matched_text"
        case capturedVars = "captured_vars"
        case capturedVarsJson = "captured_vars_json"
        case actionType = "action_type"
        case actionResult = "action_result"
        case success
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        id = try container.decode(Int.self, forKey: .id)
        watcherId = try container.decodeIfPresent(Int.self, forKey: .watcherId) ?? 0
        watcherName = try container.decodeIfPresent(String.self, forKey: .watcherName) ?? "watcher_\(watcherId)"
        jobId = try container.decodeIfPresent(String.self, forKey: .jobId) ?? ""
        hostname = try container.decodeIfPresent(String.self, forKey: .hostname) ?? ""
        if let raw = try? container.decodeIfPresent(String.self, forKey: .timestamp) {
            timestamp = Watcher.parseDate(raw)
        } else {
            timestamp = nil
        }
        matchedText = try container.decodeIfPresent(String.self, forKey: .matchedText)
        if let vars = try container.decodeIfPresent([String: JSONValue].self, forKey: .capturedVars) {
            capturedVars = vars
        } else if let raw = try container.decodeIfPresent(String.self, forKey: .capturedVarsJson),
                  let vars = JSONValue.decodeObject(from: raw) {
            capturedVars = vars
        } else {
            capturedVars = [:]
        }
        actionType = try container.decodeIfPresent(String.self, forKey: .actionType) ?? ""
        actionResult = try container.decodeIfPresent(String.self, forKey: .actionResult)
        success = try container.decodeIfPresent(Bool.self, forKey: .success) ?? false
    }

    var timestampDisplay: String? {
        guard let timestamp else { return nil }
        return Watcher.displayFormatter.string(from: timestamp)
    }
}

struct WatcherStats: Codable, Hashable {
    let totalWatchers: Int
    let watchersByState: [String: Int]
    let totalEvents: Int
    let eventsByAction: [String: WatcherActionStats]
    let eventsLastHour: Int
    let topWatchers: [WatcherTopStats]

    enum CodingKeys: String, CodingKey {
        case totalWatchers = "total_watchers"
        case watchersByState = "watchers_by_state"
        case totalEvents = "total_events"
        case eventsByAction = "events_by_action"
        case eventsLastHour = "events_last_hour"
        case topWatchers = "top_watchers"
    }
}

struct WatcherActionStats: Codable, Hashable {
    let total: Int
    let success: Int
    let failed: Int
}

struct WatcherTopStats: Codable, Hashable, Identifiable {
    var id: String { "\(watcherId)-\(jobId)" }
    let watcherId: Int
    let jobId: String
    let name: String
    let eventCount: Int

    enum CodingKeys: String, CodingKey {
        case watcherId = "watcher_id"
        case jobId = "job_id"
        case name
        case eventCount = "event_count"
    }
}

struct WatchersResponse: Decodable {
    let jobId: String?
    let watchers: [Watcher]
    let count: Int?

    enum CodingKeys: String, CodingKey {
        case jobId = "job_id"
        case watchers
        case count
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        jobId = try container.decodeIfPresent(String.self, forKey: .jobId)
        watchers = try container.decodeIfPresent([Watcher].self, forKey: .watchers) ?? []
        count = try container.decodeIfPresent(Int.self, forKey: .count)
    }
}

struct WatcherEventsResponse: Decodable {
    let events: [WatcherEvent]
    let count: Int?
}

struct WatcherActionRequest: Encodable {
    let type: String
    let params: [String: JSONValue]?
    let condition: String?
}

struct WatcherDefinitionRequest: Encodable {
    let name: String
    let pattern: String
    let intervalSeconds: Int
    let captures: [String]
    let condition: String?
    let actions: [WatcherActionRequest]
    let maxTriggers: Int?
    let outputType: String?
    let timerModeEnabled: Bool?
    let timerIntervalSeconds: Int?

    enum CodingKeys: String, CodingKey {
        case name
        case pattern
        case intervalSeconds = "interval_seconds"
        case captures
        case condition
        case actions
        case maxTriggers = "max_triggers"
        case outputType = "output_type"
        case timerModeEnabled = "timer_mode_enabled"
        case timerIntervalSeconds = "timer_interval_seconds"
    }
}

struct WatcherCreateRequest: Encodable {
    let jobId: String
    let hostname: String
    let name: String
    let pattern: String
    let intervalSeconds: Int
    let captures: [String]
    let condition: String?
    let actions: [WatcherActionRequest]
    let outputType: String?
    let timerModeEnabled: Bool?
    let timerIntervalSeconds: Int?
    let maxTriggers: Int?

    enum CodingKeys: String, CodingKey {
        case jobId = "job_id"
        case hostname
        case name
        case pattern
        case intervalSeconds = "interval_seconds"
        case captures
        case condition
        case actions
        case outputType = "output_type"
        case timerModeEnabled = "timer_mode_enabled"
        case timerIntervalSeconds = "timer_interval_seconds"
        case maxTriggers = "max_triggers"
    }
}

struct WatcherAttachResponse: Decodable {
    let message: String?
    let watcherIds: [Int]?
    let jobId: String?
    let hostname: String?

    enum CodingKeys: String, CodingKey {
        case message
        case watcherIds = "watcher_ids"
        case jobId = "job_id"
        case hostname
    }
}

struct WatcherTriggerResponse: Decodable {
    let success: Bool?
    let message: String?
    let matches: Bool?
    let matchCount: Int?
    let timerMode: Bool?

    enum CodingKeys: String, CodingKey {
        case success
        case message
        case matches
        case matchCount = "match_count"
        case timerMode = "timer_mode"
    }
}

struct WatcherMessageResponse: Decodable {
    let message: String?
}
