import Foundation
import Combine

@MainActor
final class JobPreferencesManager: ObservableObject {
    static let shared = JobPreferencesManager()

    @Published private(set) var favoriteJobKeys: Set<String>
    @Published private(set) var mutedJobKeys: Set<String>
    @Published private(set) var liveActivityJobKeys: Set<String>
    @Published private(set) var notificationsEnabledGlobally: Bool
    @Published private(set) var liveActivitiesEnabledGlobally: Bool

    private let defaults: UserDefaults
    private let favoriteKey = "ssync.favorite_job_keys"
    private let mutedKey = "ssync.muted_job_keys"
    private let liveActivitiesKey = "ssync.live_activity_job_keys"
    private let notificationsGlobalKey = "ssync.notifications_enabled_global"
    private let liveActivitiesGlobalKey = "ssync.live_activities_enabled_global"

    private init(defaults: UserDefaults = .standard) {
        self.defaults = defaults
        self.favoriteJobKeys = Set(defaults.stringArray(forKey: favoriteKey) ?? [])
        self.mutedJobKeys = Set(defaults.stringArray(forKey: mutedKey) ?? [])
        self.liveActivityJobKeys = Set(defaults.stringArray(forKey: liveActivitiesKey) ?? [])
        if defaults.object(forKey: notificationsGlobalKey) == nil {
            defaults.set(true, forKey: notificationsGlobalKey)
        }
        if defaults.object(forKey: liveActivitiesGlobalKey) == nil {
            defaults.set(true, forKey: liveActivitiesGlobalKey)
        }
        self.notificationsEnabledGlobally = defaults.bool(forKey: notificationsGlobalKey)
        self.liveActivitiesEnabledGlobally = defaults.bool(forKey: liveActivitiesGlobalKey)
    }

    func setNotificationsEnabledGlobally(_ enabled: Bool) {
        notificationsEnabledGlobally = enabled
        defaults.set(enabled, forKey: notificationsGlobalKey)
        NotificationManager.shared.syncNotificationPreferences()
    }

    func setLiveActivitiesEnabledGlobally(_ enabled: Bool) {
        liveActivitiesEnabledGlobally = enabled
        defaults.set(enabled, forKey: liveActivitiesGlobalKey)
    }

    func isFavorite(_ job: Job) -> Bool {
        favoriteJobKeys.contains(key(for: job))
    }

    func toggleFavorite(_ job: Job) {
        setFavorite(!isFavorite(job), for: job)
    }

    func setFavorite(_ favorite: Bool, for job: Job) {
        setFavorite(favorite, jobId: job.id, host: job.host)
    }

    func setFavorite(_ favorite: Bool, jobId: String, host: String) {
        let jobKey = makeKey(jobId: jobId, host: host)
        if favorite {
            favoriteJobKeys.insert(jobKey)
        } else {
            favoriteJobKeys.remove(jobKey)
        }
        defaults.set(Array(favoriteJobKeys), forKey: favoriteKey)
    }

    func notificationsEnabled(for job: Job) -> Bool {
        notificationsEnabled(forJobId: job.id, host: job.host)
    }

    func notificationsEnabled(forJobId jobId: String, host: String) -> Bool {
        guard notificationsEnabledGlobally else { return false }
        return !mutedJobKeys.contains(makeKey(jobId: jobId, host: host))
    }

    func toggleNotifications(for job: Job) {
        setNotificationsEnabled(!notificationsEnabled(for: job), for: job)
    }

    func setNotificationsEnabled(_ enabled: Bool, for job: Job) {
        setNotificationsEnabled(enabled, forJobId: job.id, host: job.host)
    }

    func setNotificationsEnabled(_ enabled: Bool, forJobId jobId: String, host: String) {
        let jobKey = makeKey(jobId: jobId, host: host)
        if enabled {
            mutedJobKeys.remove(jobKey)
        } else {
            mutedJobKeys.insert(jobKey)
        }
        defaults.set(Array(mutedJobKeys), forKey: mutedKey)
        NotificationManager.shared.syncNotificationPreferences()
    }

    func liveActivitiesEnabled(for job: Job) -> Bool {
        guard liveActivitiesEnabledGlobally else { return false }
        return liveActivityJobKeys.contains(key(for: job))
    }

    func toggleLiveActivities(for job: Job) {
        setLiveActivitiesEnabled(!liveActivitiesEnabled(for: job), for: job)
    }

    func setLiveActivitiesEnabled(_ enabled: Bool, for job: Job) {
        let jobKey = key(for: job)
        if enabled {
            liveActivityJobKeys.insert(jobKey)
        } else {
            liveActivityJobKeys.remove(jobKey)
        }
        defaults.set(Array(liveActivityJobKeys), forKey: liveActivitiesKey)
    }

    func key(for job: Job) -> String {
        makeKey(jobId: job.id, host: job.host)
    }

    private func makeKey(jobId: String, host: String) -> String {
        "\(host.lowercased())::\(jobId)"
    }
}
