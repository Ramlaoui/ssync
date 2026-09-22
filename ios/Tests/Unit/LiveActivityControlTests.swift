#if os(iOS) && canImport(Ssync)
  import ActivityKit
  import Foundation
  import Testing
  @testable import Ssync

  @MainActor struct LiveActivityControlTests {
    @Test func stoppingOneActivityPreservesOtherConnectionsAndIsRepeatable() async throws {
      let controller = JobLiveActivities.shared
      var createdIDs: [String] = []
      do {
        let firstConnection = UUID()
        let secondConnection = UUID()
        let first = try makeActivity(connection: firstConnection)
        createdIDs.append(first.id)
        let second = try makeActivity(connection: secondConnection)
        createdIDs.append(second.id)
        controller.refresh()

        #expect(
          controller.activityID(host: "ssync-test", number: "1", connectionID: firstConnection)
            == first.id)
        #expect(
          controller.activityID(host: "ssync-test", number: "1", connectionID: secondConnection)
            == second.id)

        _ = try await StopFollowingJobIntent(activityID: first.id).perform()
        #expect(first.activityState == .ended || first.activityState == .dismissed)
        #expect(second.activityState == .active || second.activityState == .stale)

        _ = try await StopFollowingJobIntent(activityID: first.id).perform()
        #expect(second.activityState == .active || second.activityState == .stale)

        await controller.stop(activityID: second.id)
        #expect(second.activityState == .ended || second.activityState == .dismissed)
      } catch {
        for id in createdIDs { await controller.stop(activityID: id) }
        throw error
      }
      for id in createdIDs { await controller.stop(activityID: id) }
    }

    private func makeActivity(connection: UUID) throws -> Activity<JobActivityAttributes> {
      try Activity.request(
        attributes: JobActivityAttributes(
          host: "ssync-test", number: "1", name: "ssync Live Activity check",
          connectionID: connection),
        content: ActivityContent(
          state: JobActivityAttributes.ContentState(
            state: "Running", runtime: "1 h 8 m", updatedAt: .now, ended: false),
          staleDate: .now.addingTimeInterval(90)),
        pushType: nil)
    }
  }
#endif
