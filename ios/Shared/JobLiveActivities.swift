import ActivityKit
import AppIntents
import Foundation
import Observation

@MainActor @Observable final class JobLiveActivities {
  static let shared = JobLiveActivities()
  private(set) var activities: [Activity<JobActivityAttributes>] = []
  @ObservationIgnored private var activityUpdates: Task<Void, Never>?
  @ObservationIgnored private var stateUpdates: [String: Task<Void, Never>] = [:]

  private init() {
    refresh()
    activityUpdates = Task { [weak self] in
      for await _ in Activity<JobActivityAttributes>.activityUpdates {
        guard !Task.isCancelled else { return }
        self?.refresh()
      }
    }
  }

  func activityID(host: String, number: String, connectionID: UUID) -> String? {
    activities.first {
      $0.attributes.host == host && $0.attributes.number == number
        && $0.attributes.connectionID == connectionID
    }?.id
  }

  func refresh() {
    activities = Activity<JobActivityAttributes>.activities.filter {
      $0.activityState != .dismissed
    }
    let currentIDs = Set(activities.map(\.id))
    for id in Array(stateUpdates.keys) where !currentIDs.contains(id) {
      stateUpdates.removeValue(forKey: id)?.cancel()
    }
    for activity in activities where stateUpdates[activity.id] == nil {
      stateUpdates[activity.id] = Task { [weak self] in
        for await _ in activity.activityStateUpdates {
          guard !Task.isCancelled else { return }
          self?.refresh()
        }
      }
    }
  }

  func stop(activityID: String) async {
    await Self.dismiss(activityID: activityID)
    refresh()
  }

  private nonisolated static func dismiss(activityID: String) async {
    // Target the displayed activity, so a stale button cannot stop a newer follow.
    guard
      let activity = Activity<JobActivityAttributes>.activities.first(where: {
        $0.id == activityID
      })
    else {
      return
    }
    await activity.end(nil, dismissalPolicy: .immediate)
  }
}

struct StopFollowingJobIntent: LiveActivityIntent {
  static let title: LocalizedStringResource = "Stop following job"
  static let description = IntentDescription("Dismiss this Live Activity. The job keeps running.")
  static let isDiscoverable = false
  static let openAppWhenRun = false

  @Parameter(title: "Live Activity") var activityID: String

  init() {}
  init(activityID: String) { self.activityID = activityID }

  @MainActor func perform() async throws -> some IntentResult {
    await JobLiveActivities.shared.stop(activityID: activityID)
    return .result()
  }
}
