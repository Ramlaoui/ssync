import Foundation

struct APIError: LocalizedError, Sendable {
  var status: Int
  var message: String
  var errorDescription: String? { message }
}

struct APIClient: Sendable {
  private static let ephemeralSession: URLSession = {
    let configuration = URLSessionConfiguration.ephemeral
    configuration.urlCache = nil
    configuration.httpCookieStorage = nil
    configuration.requestCachePolicy = .reloadIgnoringLocalCacheData
    return URLSession(configuration: configuration)
  }()
  let connection: Connection
  let apiKey: String
  var session: URLSession = ephemeralSession

  func request(
    _ path: String, method: String = "GET", query: [String: String] = [:], body: JSONValue? = nil
  ) throws -> URLRequest {
    guard var parts = URLComponents(string: connection.baseURL),
      ["https", "http"].contains(parts.scheme?.lowercased() ?? ""),
      parts.host != nil, parts.user == nil, parts.password == nil
    else {
      throw APIError(
        status: 0, message: "Enter a valid ssync API URL without embedded credentials.")
    }
    parts.path =
      parts.path.trimmingCharacters(in: CharacterSet(charactersIn: "/")).isEmpty
      ? "/" + path.trimmingCharacters(in: CharacterSet(charactersIn: "/"))
      : "/" + parts.path.trimmingCharacters(in: CharacterSet(charactersIn: "/")) + "/"
        + path.trimmingCharacters(in: CharacterSet(charactersIn: "/"))
    parts.queryItems =
      query.isEmpty
      ? nil : query.sorted { $0.key < $1.key }.map { URLQueryItem(name: $0.key, value: $0.value) }
    parts.fragment = nil
    guard let url = parts.url else {
      throw APIError(status: 0, message: "The ssync API URL could not be read.")
    }
    var request = URLRequest(url: url, timeoutInterval: 30)
    request.httpMethod = method
    request.setValue("application/json", forHTTPHeaderField: "Accept")
    if !apiKey.isEmpty { request.setValue(apiKey, forHTTPHeaderField: "X-API-Key") }
    if let body {
      request.httpBody = try JSONEncoder().encode(body)
      request.setValue("application/json", forHTTPHeaderField: "Content-Type")
    }
    return request
  }

  func send<T: Decodable & Sendable>(
    _ path: String, method: String = "GET", query: [String: String] = [:], body: JSONValue? = nil
  ) async throws -> T {
    let request = try request(path, method: method, query: query, body: body)
    let (data, response) = try await session.data(for: request)
    try validate(response, data: data)
    return try JSONDecoder().decode(T.self, from: data)
  }

  func perform(
    _ path: String, method: String = "POST", query: [String: String] = [:], body: JSONValue? = nil
  ) async throws {
    let request = try request(path, method: method, query: query, body: body)
    let (data, response) = try await session.data(for: request)
    try validate(response, data: data)
  }

  func validate(_ response: URLResponse, data: Data = Data()) throws {
    guard let http = response as? HTTPURLResponse else {
      throw APIError(status: 0, message: "The server returned an invalid response.")
    }
    guard (200..<300).contains(http.statusCode) else {
      let json = try? JSONDecoder().decode(JSONValue.self, from: data)
      let detail = json?.object["detail"]
      let message = detail?.string ?? (detail.map(\.pretty)).flatMap { $0.isEmpty ? nil : $0 }
      throw APIError(
        status: http.statusCode,
        message: message ?? HTTPURLResponse.localizedString(forStatusCode: http.statusCode))
    }
  }

  func hosts() async throws -> [Host] { try await send("api/hosts") }
  func jobs(since: String = "7d", force: Bool = false) async throws -> [JobStatusResponse] {
    try await send(
      "api/status",
      query: [
        "since": since, "limit": "1000", "group_array_jobs": "true", "force_refresh": String(force),
      ])
  }
  func partitions(force: Bool = false) async throws -> [PartitionSnapshot] {
    try await send("api/partitions", query: ["force_refresh": String(force)])
  }
  func job(_ id: JobID) async throws -> Job {
    try await send("api/jobs/\(id.number)", query: ["host": id.host])
  }
  func output(_ id: JobID, source: String, force: Bool = false) async throws -> OutputResponse {
    try await send(
      "api/jobs/\(id.number)/output",
      query: [
        "host": id.host, "output_type": source, "max_bytes": "524288",
        "force_refresh": String(force),
      ])
  }
  func document(_ id: JobID, kind: String) async throws -> JSONValue {
    try await send("api/jobs/\(id.number)/\(kind)", query: ["host": id.host])
  }
  func watchers() async throws -> WatchersResponse {
    try await send("api/watchers", query: ["limit": "300"])
  }
  func watcherEvents(_ id: Int) async throws -> WatcherEventsResponse {
    try await send("api/watchers/events", query: ["watcher_id": String(id), "limit": "200"])
  }
  func cancel(_ id: JobID) async throws {
    try await perform("api/jobs/\(id.number)/cancel", query: ["host": id.host])
  }
  func download(_ id: JobID, source: String) async throws -> URL {
    var request = try request(
      "api/jobs/\(id.number)/output/download", query: ["host": id.host, "output_type": source])
    request.timeoutInterval = 120
    let (location, response) = try await session.download(for: request)
    try validate(response)
    let safe = "\(id.host)-\(id.number)-\(source)".map {
      $0.isLetter || $0.isNumber || "-_.".contains($0) ? $0 : "_"
    }
    let target = FileManager.default.temporaryDirectory.appending(path: UUID().uuidString)
    try FileManager.default.createDirectory(at: target, withIntermediateDirectories: true)
    let file = target.appending(path: String(safe) + ".txt")
    try FileManager.default.moveItem(at: location, to: file)
    return file
  }

  func socket() throws -> URLSessionWebSocketTask {
    var request = try request("ws/jobs")
    var parts = URLComponents(url: request.url!, resolvingAgainstBaseURL: false)!
    parts.scheme = parts.scheme == "https" ? "wss" : "ws"
    request.url = parts.url
    return session.webSocketTask(with: request)
  }
}
