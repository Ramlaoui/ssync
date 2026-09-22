import Foundation
import Testing

#if canImport(Ssync)
  @testable import Ssync
#else
  @testable import SsyncCore
#endif

struct IdentityAndModelTests {
  @Test func sameJobNumberOnDifferentHostsDoesNotCollide() throws {
    let atlas = JobID(host: "Atlas", number: "48192")
    let boreal = JobID(host: "Boreal", number: "48192")
    #expect(Set([atlas, boreal]).count == 2)
    #expect(try JSONDecoder().decode(JobID.self, from: JSONEncoder().encode(atlas)) == atlas)
  }

  @Test func preservesUnknownSchedulerFieldsAndNulls() throws {
    let data = Data(
      #"{"hostname":"Atlas","job_id":"48192","name":"fold","state":"OUT_OF_MEMORY","runtime":"1-02:03:04","memory":null,"future_metric":{"peak":42},"cpus":32}"#
        .utf8)
    let job = try JSONDecoder().decode(Job.self, from: data)
    #expect(job.state == .failed)
    #expect(job.fields.text("cpus") == "32")
    #expect(job.fields["memory"] == .null)
    #expect(try JSONDecoder().decode(Job.self, from: JSONEncoder().encode(job)) == job)
  }

  @Test func slurmDurationsAndElapsedFractionAreBounded() {
    #expect(Format.seconds("1-02:03:04") == 93784)
    #expect(Format.seconds("UNLIMITED") == nil)
    #expect(Format.seconds("00:00:00") == 0)
    #expect(Format.seconds("-1:30") == nil)
    let job = Job(["runtime": .string("09:00:00"), "time_limit": .string("08:00:00")])
    #expect(job.timeFraction == 1)
  }

  @Test func partitionsDecodeWithoutGPUDataAndKeepObservationTime() throws {
    let data = Data(
      #"[{"hostname":"Atlas","partitions":[{"partition":"cpu","availability":"up","states":["mixed","drained"],"nodes_total":8,"cpus_alloc":48,"cpus_idle":8,"cpus_other":8,"cpus_total":64}],"query_time":"0.32s","cached":true,"stale":true,"updated_at":"2026-09-22T09:30:00+00:00","cache_age_seconds":60}]"#
        .utf8)
    let snapshots = try JSONDecoder().decode([PartitionSnapshot].self, from: data)
    #expect(snapshots[0].partitions[0].gpus_used == nil)
    #expect(snapshots[0].partitions[0].hasGPUs == false)
    #expect(snapshots[0].observedAt != nil)
    #expect(snapshots[0].stale == true)
  }

  @Test func watcherAPIConfigIsPreserved() throws {
    let data = Data(
      #"{"watchers":[{"id":1,"job_id":"48192","hostname":"Atlas","name":"Checkpoint","state":"active","pattern":"checkpoint (.+)","captures":["checkpoint"],"actions":[{"type":"resubmit","condition":"loss < 1","config":{"cancel_previous":false,"remaining_resubmits":2}}]}],"count":1}"#
        .utf8)
    let response = try JSONDecoder().decode(WatchersResponse.self, from: data)
    #expect(
      response.watchers[0].actions[0].object["config"]?.object["remaining_resubmits"]?.int == 2)
    #expect(response.watchers[0].jobID == JobID(host: "Atlas", number: "48192"))
  }

  @Test func statusesIncludeArrayTasksWithQualifiedIdentities() throws {
    let task = DemoData.job("100_1", name: "array task", host: "")
    let group = ArrayGroup(
      array_job_id: "100", hostname: "Atlas", job_name: "array", total_tasks: 1, tasks: [task],
      pending_count: 0, running_count: 1, completed_count: 0, failed_count: 0, cancelled_count: 0)
    let response = JobStatusResponse(
      hostname: "Atlas", jobs: [DemoData.job("99", name: "single")], array_groups: [group])
    #expect(response.allJobs.count == 2)
    #expect(response.allJobs.contains { $0.id == JobID(host: "Atlas", number: "100_1") })
  }
}

struct RequestTests {
  @Test func credentialsStayInHeaderAndHostStaysInQuery() throws {
    let client = APIClient(
      connection: Connection(name: "Test", baseURL: "https://example.invalid/ssync/"),
      apiKey: "test-only-key")
    let request = try client.request(
      "api/jobs/48192", query: ["host": "host & gpu", "output_type": "stdout"])
    #expect(request.url?.path == "/ssync/api/jobs/48192")
    #expect(request.value(forHTTPHeaderField: "X-API-Key") == "test-only-key")
    #expect(request.url?.absoluteString.contains("test-only-key") == false)
    let query = URLComponents(url: request.url!, resolvingAgainstBaseURL: false)?.queryItems
    #expect(query?.first { $0.name == "host" }?.value == "host & gpu")
  }

  @Test func rejectsEmbeddedCredentialsAndUnsupportedSchemes() {
    for url in [
      "https://user:password@example.invalid", "file:///tmp/jobs", "wss://example.invalid",
    ] {
      let client = APIClient(connection: Connection(name: "Test", baseURL: url), apiKey: "")
      #expect(throws: APIError.self) { try client.request("api/hosts") }
    }
  }

  @Test func serverErrorDetailSurvives() {
    let client = APIClient(
      connection: Connection(name: "Test", baseURL: "https://example.invalid"), apiKey: "")
    let response = HTTPURLResponse(
      url: URL(string: "https://example.invalid")!, statusCode: 401, httpVersion: nil,
      headerFields: nil)!
    do {
      try client.validate(response, data: Data(#"{"detail":"Invalid API key"}"#.utf8))
      Issue.record("Unauthorized responses must throw")
    } catch let error as APIError {
      #expect(error.status == 401)
      #expect(error.message == "Invalid API key")
    } catch { Issue.record("Unexpected error \(error)") }
  }

  @Test func launchRequestUsesBackendResourceKeysAndDisablesUnrequestedSync() {
    var draft = LaunchDraft.sample
    draft.source = "/server/project"
    draft.tasksPerNode = "4"
    draft.exclude = "*.tmp\ncache/"
    draft.extraFields["slurm_exclude"] = .string("node42")
    let fields = draft.requestBody.object
    #expect(fields["source_dir"] == .null)
    #expect(fields["n_tasks_per_node"]?.int == 4)
    #expect(fields["mem"]?.int == 128)
    #expect(fields["exclude"]?.array.count == 2)
    #expect(fields["slurm_exclude"]?.string == "node42")
    draft.syncSource = true
    #expect(draft.requestBody.object["source_dir"]?.string == "/server/project")
  }

  @Test func unknownSubmissionCannotBeRetriedAndDraftSurvivesRoundTrip() throws {
    var draft = LaunchDraft.sample
    #expect(draft.validation == nil)
    draft.submissionUnknown = true
    let restored = try JSONDecoder().decode(LaunchDraft.self, from: JSONEncoder().encode(draft))
    #expect(restored.validation != nil)
    #expect(restored.id == draft.id)
    #expect(restored.submissionUnknown)
  }

  @Test func rejectsResourceClampingAndMissingSource() {
    var draft = LaunchDraft.sample
    draft.cpus = "257"
    #expect(draft.validation != nil)
    draft.cpus = "32"
    draft.syncSource = true
    #expect(draft.validation != nil)
    draft.source = "/server/project"
    #expect(draft.validation == nil)
  }
}

struct OutputTests {
  @Test func streamedUnicodeRemainsBoundedAndSearchUsesLoadedTextOnly() {
    var buffer = OutputBuffer()
    buffer.append("old-only-line\n")
    buffer.append(String(repeating: "step λ loss=0.123\n", count: 40_000))
    #expect(buffer.text.utf8.count <= OutputBuffer.limit)
    #expect(buffer.trimmed)
    #expect(!buffer.text.contains("�"))
    #expect(buffer.matchingLines("old-only-line").isEmpty)
    #expect(!buffer.matchingLines("LOSS").isEmpty)
  }

  @Test func replacingSourceClearsThePreviousStream() {
    var buffer = OutputBuffer()
    buffer.replace("stdout checkpoint")
    buffer.replace("stderr warning")
    #expect(buffer.matchingLines("checkpoint").isEmpty)
    #expect(buffer.matchingLines("warning") == [0])
  }

  @Test func sseSupportsCommentsMultilineDataAndEventBoundaries() {
    var parser = SSEParser()
    #expect(parser.consume(": heartbeat") == nil)
    #expect(parser.consume("event: update") == nil)
    #expect(parser.consume("data: first") == nil)
    #expect(parser.consume("data: second") == nil)
    #expect(parser.consume("") == "first\nsecond")
    #expect(parser.consume("") == nil)
    #expect(parser.consume("data:{\"type\":\"complete\"}") == nil)
    #expect(parser.consume("") == #"{"type":"complete"}"#)
  }
}
