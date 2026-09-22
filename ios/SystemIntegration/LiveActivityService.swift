import ActivityKit
import Foundation

@MainActor final class LiveActivityService {
  static let shared = LiveActivityService()
  func follow(job: Job, connection: Connection) async throws {
    defer { JobLiveActivities.shared.refresh() }
    guard ActivityAuthorizationInfo().areActivitiesEnabled else {
      throw APIError(status: 0, message: "Live Activities are disabled for ssync in iOS Settings.")
    }
    for activity in Activity<JobActivityAttributes>.activities
    where activity.attributes.connectionID == connection.id {
      await activity.end(nil, dismissalPolicy: .immediate)
    }
    let attributes = JobActivityAttributes(
      host: job.host, number: job.number, name: job.name, connectionID: connection.id)
    let state = JobActivityAttributes.ContentState(
      state: job.state.label, runtime: Format.duration(job.runtime), updatedAt: .now,
      ended: !job.state.active)
    _ = try Activity.request(
      attributes: attributes,
      content: ActivityContent(state: state, staleDate: .now.addingTimeInterval(90)), pushType: nil)
  }
  func update(jobs: [Job], connection: Connection) async {
    defer { JobLiveActivities.shared.refresh() }
    for activity in Activity<JobActivityAttributes>.activities
    where activity.attributes.connectionID == connection.id {
      guard
        let job = jobs.first(where: {
          $0.host == activity.attributes.host && $0.number == activity.attributes.number
        })
      else { continue }
      let state = JobActivityAttributes.ContentState(
        state: job.state.label, runtime: Format.duration(job.runtime), updatedAt: .now,
        ended: !job.state.active)
      let content = ActivityContent(state: state, staleDate: .now.addingTimeInterval(90))
      if job.state.active {
        await activity.update(content)
      } else {
        await activity.end(content, dismissalPolicy: .after(.now.addingTimeInterval(900)))
      }
    }
  }
  func endAll() async {
    defer { JobLiveActivities.shared.refresh() }
    for activity in Activity<JobActivityAttributes>.activities {
      await activity.end(nil, dismissalPolicy: .immediate)
    }
  }
}
