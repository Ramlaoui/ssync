import Foundation
import Testing

#if canImport(Ssync)
  @testable import Ssync
#else
  @testable import SsyncCore
#endif

struct NetworkContractTests {
  @Test func decodesServerResponsesThroughURLSession() async throws {
    let configuration = URLSessionConfiguration.ephemeral
    configuration.protocolClasses = [FixtureProtocol.self]
    let session = URLSession(configuration: configuration)
    defer { session.invalidateAndCancel() }
    let api = APIClient(
      connection: Connection(name: "Fixture", baseURL: "https://ssync.invalid"),
      apiKey: "fixture-key", session: session)
    let hosts = try await api.hosts()
    #expect(hosts.map(\.hostname) == ["Atlas"])
    let jobs = try await api.jobs()
    #expect(jobs[0].allJobs[0].id == JobID(host: "Atlas", number: "123"))
    let output = try await api.output(JobID(host: "Atlas", number: "123"), source: "stderr")
    #expect(output.stderr == "warning\n")
    #expect(output.stdout == nil)
    let watchers = try await api.watchers()
    #expect(watchers.watchers[0].id == 7)
    let status: JSONValue = try await api.send(
      "api/jobs/launch", method: "POST", body: LaunchDraft.sample.requestBody)
    #expect(status.object["launch_id"]?.string == "abc123")
    #expect(status.object["job_id"] == .null)
  }

  @Test func distinguishesRejectedRequestsFromSuccessfulEmptyResults() async throws {
    let configuration = URLSessionConfiguration.ephemeral
    configuration.protocolClasses = [FixtureProtocol.self]
    let session = URLSession(configuration: configuration)
    defer { session.invalidateAndCancel() }
    let api = APIClient(
      connection: Connection(name: "Fixture", baseURL: "https://ssync.invalid"),
      apiKey: "fixture-key", session: session)
    do {
      _ = try await api.jobs(since: "2026-09-22T00:00:00Z")
      Issue.record("The server only accepts relative since values")
    } catch let error as APIError { #expect(error.status == 422) }
  }
}

private final class FixtureProtocol: URLProtocol, @unchecked Sendable {
  override class func canInit(with request: URLRequest) -> Bool {
    request.url?.host == "ssync.invalid"
  }
  override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }
  override func startLoading() {
    guard let url = request.url else { return }
    let query = URLComponents(url: url, resolvingAgainstBaseURL: false)?.queryItems ?? []
    var status = 200
    let payload: String
    if request.value(forHTTPHeaderField: "X-API-Key") != "fixture-key" {
      status = 401
      payload = #"{"detail":"Invalid API key"}"#
    } else {
      switch url.path {
      case "/api/hosts":
        payload =
          #"[{"hostname":"Atlas","work_dir":"[CONFIGURED]","scratch_dir":"[CONFIGURED]","slurm_defaults":{"partition":"gpu"}}]"#
      case "/api/status":
        if query.first(where: { $0.name == "since" })?.value == "7d" {
          payload =
            #"[{"hostname":"Atlas","jobs":[{"hostname":"Atlas","job_id":"123","state":"R","name":"train","memory":null}],"query_time":"2026-09-22T10:00:00.123456","total_jobs":1,"cached":false,"array_groups":null}]"#
        } else {
          status = 422
          payload = #"{"detail":"since must match ^[0-9]+[hdwm]$"}"#
        }
      case "/api/jobs/123/output":
        if query.first(where: { $0.name == "host" })?.value == "Atlas"
          && query.first(where: { $0.name == "output_type" })?.value == "stderr"
        {
          payload =
            #"{"job_id":"123","hostname":"Atlas","output_type":"stderr","stdout":null,"stderr":"warning\n","content_truncated":false,"cached":false,"stale":false}"#
        } else {
          status = 400
          payload = #"{"detail":"Host and stream required"}"#
        }
      case "/api/watchers":
        payload =
          #"{"watchers":[{"id":7,"name":"Checkpoint","job_id":"123","hostname":"Atlas","state":"active","actions":[{"type":"log_event","config":{"message":"saved"}}]}],"count":1}"#
      case "/api/jobs/launch":
        if request.httpMethod == "POST" {
          payload =
            #"{"success":true,"job_id":null,"launch_id":"abc123","message":"Launch started","hostname":"Atlas"}"#
        } else {
          status = 405
          payload = #"{"detail":"Method not allowed"}"#
        }
      default:
        status = 404
        payload = #"{"detail":"Not found"}"#
      }
    }
    client?.urlProtocol(
      self,
      didReceive: HTTPURLResponse(
        url: url, statusCode: status, httpVersion: "HTTP/1.1",
        headerFields: ["Content-Type": "application/json"])!, cacheStoragePolicy: .notAllowed)
    client?.urlProtocol(self, didLoad: Data(payload.utf8))
    client?.urlProtocolDidFinishLoading(self)
  }
  override func stopLoading() {}
}
