import Foundation
import Combine

#if canImport(ActivityKit)
import ActivityKit

@available(iOS 16.1, *)
struct JobLiveActivityAttributes: ActivityAttributes {
    struct ContentState: Codable, Hashable {
        let stateCode: String
        let stateText: String
        let durationText: String?
        let updatedAt: Date
    }

    let jobId: String
    let jobName: String
    let host: String
}
#endif

@MainActor
final class LiveActivityManager: ObservableObject {
    static let shared = LiveActivityManager()

    @Published private(set) var activeJobKeys: Set<String> = []

    private var activities: [String: Any] = [:]

    private init() {}

    var isSupported: Bool {
        #if canImport(ActivityKit)
        if #available(iOS 16.1, *) {
            guard hasWidgetExtension else { return false }
            return ActivityAuthorizationInfo().areActivitiesEnabled
        }
        #endif
        return false
    }

    private var hasWidgetExtension: Bool {
        guard let pluginsURL = Bundle.main.builtInPlugInsURL else { return false }
        let pluginURLs = (try? FileManager.default.contentsOfDirectory(
            at: pluginsURL,
            includingPropertiesForKeys: nil
        )) ?? []
        return pluginURLs.contains { $0.pathExtension == "appex" }
    }

    func handleJobUpdate(_ job: Job) {
        let prefs = JobPreferencesManager.shared
        let key = prefs.key(for: job)
        let shouldTrack = prefs.liveActivitiesEnabled(for: job) || (prefs.isFavorite(job) && prefs.liveActivitiesEnabledGlobally)

        guard isSupported else {
            endLiveActivity(for: key, finalState: job.state.displayName)
            return
        }

        if !shouldTrack || job.state.isCompleted {
            endLiveActivity(for: key, finalState: job.state.displayName)
            return
        }

        startOrUpdateLiveActivity(for: job, key: key)
    }

    func endLiveActivity(for job: Job) {
        let key = JobPreferencesManager.shared.key(for: job)
        endLiveActivity(for: key, finalState: job.state.displayName)
    }

    func endAllActivities() {
        let keys = Array(activeJobKeys)
        for key in keys {
            endLiveActivity(for: key, finalState: "Stopped")
        }
    }

    private func startOrUpdateLiveActivity(for job: Job, key: String) {
        #if canImport(ActivityKit)
        guard #available(iOS 16.1, *) else { return }

        let state = JobLiveActivityAttributes.ContentState(
            stateCode: job.state.rawValue,
            stateText: job.state.displayName,
            durationText: job.formattedDuration,
            updatedAt: Date()
        )

        if let existing = activities[key] as? Activity<JobLiveActivityAttributes> {
            Task {
                await self.updateActivity(existing, with: state)
            }
            return
        }

        let attributes = JobLiveActivityAttributes(
            jobId: job.id,
            jobName: job.name,
            host: job.host
        )

        Task {
            do {
                let activity = try self.requestActivity(attributes: attributes, state: state)
                self.activities[key] = activity
                self.activeJobKeys.insert(key)
            } catch {
                self.activeJobKeys.remove(key)
            }
        }
        #endif
    }

    private func endLiveActivity(for key: String, finalState: String) {
        #if canImport(ActivityKit)
        guard #available(iOS 16.1, *) else { return }

        guard let activity = activities[key] as? Activity<JobLiveActivityAttributes> else {
            activeJobKeys.remove(key)
            return
        }

        let finalContent = JobLiveActivityAttributes.ContentState(
            stateCode: "DONE",
            stateText: finalState,
            durationText: nil,
            updatedAt: Date()
        )

        Task {
            await self.endActivity(activity, with: finalContent)
            self.activities.removeValue(forKey: key)
            self.activeJobKeys.remove(key)
        }
        #else
        activeJobKeys.remove(key)
        #endif
    }

    #if canImport(ActivityKit)
    @available(iOS 16.1, *)
    private func requestActivity(
        attributes: JobLiveActivityAttributes,
        state: JobLiveActivityAttributes.ContentState
    ) throws -> Activity<JobLiveActivityAttributes> {
        if #available(iOS 16.2, *) {
            let content = ActivityContent(state: state, staleDate: nil)
            return try Activity.request(
                attributes: attributes,
                content: content,
                pushType: nil
            )
        } else {
            return try Activity.request(
                attributes: attributes,
                contentState: state,
                pushType: nil
            )
        }
    }

    @available(iOS 16.1, *)
    private func updateActivity(
        _ activity: Activity<JobLiveActivityAttributes>,
        with state: JobLiveActivityAttributes.ContentState
    ) async {
        if #available(iOS 16.2, *) {
            let content = ActivityContent(state: state, staleDate: nil)
            await activity.update(content)
        } else {
            await activity.update(using: state)
        }
    }

    @available(iOS 16.1, *)
    private func endActivity(
        _ activity: Activity<JobLiveActivityAttributes>,
        with state: JobLiveActivityAttributes.ContentState
    ) async {
        if #available(iOS 16.2, *) {
            let content = ActivityContent(state: state, staleDate: nil)
            await activity.end(content, dismissalPolicy: .immediate)
        } else {
            await activity.end(using: state, dismissalPolicy: .immediate)
        }
    }
    #endif
}
