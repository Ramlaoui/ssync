import Foundation
import Combine
import UIKit
@preconcurrency import UserNotifications

@MainActor
final class NotificationManager: NSObject, ObservableObject, UNUserNotificationCenterDelegate {
    static let shared = NotificationManager()

    @Published private(set) var authorizationStatus: UNAuthorizationStatus = .notDetermined
    @Published private(set) var deviceToken: String?
    @Published private(set) var registrationStatusMessage = "Push notifications not configured"
    @Published private(set) var isRemoteRegistrationSynced = false

    private let pendingJobIdKey = "ssync.pending_open_job_id"
    private let pendingHostKey = "ssync.pending_open_job_host"
    private let deviceTokenKey = "ssync.apns.device_token"
    private let deviceIDKey = "ssync.apns.device_id"
    private let center = UNUserNotificationCenter.current()
    private var cancellables = Set<AnyCancellable>()
    private var lastCompletionStateByJobKey: [String: JobState] = [:]
    private let stateQueue = DispatchQueue(label: "ssync.notification.manager.state")
    private var isConfigured = false

    var usesRemoteDelivery: Bool {
        authorizationStatus == .authorized && isRemoteRegistrationSynced
    }

    private override init() {
        deviceToken = UserDefaults.standard.string(forKey: deviceTokenKey)
        super.init()
    }

    func configure() {
        guard !isConfigured else { return }
        isConfigured = true

        center.delegate = self
        setupNotificationCategories()
        refreshAuthorizationStatus()

        NotificationCenter.default.publisher(for: UIApplication.didBecomeActiveNotification)
            .sink { _ in
                Task { @MainActor in
                    NotificationManager.shared.refreshAuthorizationStatus()
                    NotificationManager.shared.syncRemoteRegistrationIfPossible()
                }
            }
            .store(in: &cancellables)
    }

    func requestAuthorization() {
        configure()
        Task {
            let settings = await center.notificationSettings()
            authorizationStatus = settings.authorizationStatus

            switch settings.authorizationStatus {
            case .authorized, .provisional, .ephemeral:
                registrationStatusMessage = "Push permission granted"
                UIApplication.shared.registerForRemoteNotifications()
            case .denied:
                registrationStatusMessage = "Push notifications denied in system settings"
            case .notDetermined:
                do {
                    let granted = try await center.requestAuthorization(options: [.alert, .sound, .badge])
                    if granted {
                        registrationStatusMessage = "Push permission granted"
                        UIApplication.shared.registerForRemoteNotifications()
                    } else {
                        registrationStatusMessage = "Push notifications denied in system settings"
                    }
                    refreshAuthorizationStatus()
                } catch {
                    registrationStatusMessage = "Push permission failed: \(error.localizedDescription)"
                }
            @unknown default:
                registrationStatusMessage = "Push notification permission unavailable"
            }
        }
    }

    func handleDeviceToken(_ tokenData: Data) {
        let token = tokenData.map { String(format: "%02x", $0) }.joined()
        deviceToken = token
        UserDefaults.standard.set(token, forKey: deviceTokenKey)
        registrationStatusMessage = "Device registered with APNs"
        syncRemoteRegistrationIfPossible()
    }

    func handleRemoteRegistrationFailure(_ error: Error) {
        isRemoteRegistrationSynced = false
        registrationStatusMessage = "APNs registration failed: \(error.localizedDescription)"
    }

    func syncRemoteRegistrationIfPossible() {
        guard authorizationStatus == .authorized || authorizationStatus == .provisional || authorizationStatus == .ephemeral else {
            isRemoteRegistrationSynced = false
            if authorizationStatus == .denied {
                registrationStatusMessage = "Push notifications denied in system settings"
            }
            return
        }

        guard let token = deviceToken, !token.isEmpty else {
            isRemoteRegistrationSynced = false
            registrationStatusMessage = "Waiting for APNs device token"
            UIApplication.shared.registerForRemoteNotifications()
            return
        }

        guard AuthenticationManager.shared.isAuthenticated else {
            isRemoteRegistrationSynced = false
            registrationStatusMessage = "Sign in to enable push notifications"
            return
        }

        let payload = NotificationDeviceRegistrationRequest(
            token: token,
            platform: "ios",
            environment: currentAPNsEnvironment,
            bundleId: Bundle.main.bundleIdentifier,
            deviceId: deviceIdentifier,
            enabled: JobPreferencesManager.shared.notificationsEnabledGlobally
        )

        APIClient.shared.registerNotificationDevice(payload)
            .sink { [weak self] completion in
                guard let self else { return }
                if case .failure(let error) = completion {
                    self.isRemoteRegistrationSynced = false
                    self.registrationStatusMessage = "Push registration failed: \(error.localizedDescription)"
                }
            } receiveValue: { [weak self] _ in
                guard let self else { return }
                self.isRemoteRegistrationSynced = true
                self.registrationStatusMessage = "Push notifications active"
                self.syncNotificationPreferences()
            }
            .store(in: &cancellables)
    }

    func syncNotificationPreferences() {
        guard AuthenticationManager.shared.isAuthenticated else { return }

        let mutedJobIDs = Set(JobPreferencesManager.shared.mutedJobKeys.compactMap { key in
            key.split(separator: "::", maxSplits: 1).last.map(String.init)
        })

        let payload = NotificationPreferencesPatchRequest(
            enabled: JobPreferencesManager.shared.notificationsEnabledGlobally,
            allowedStates: nil,
            mutedJobIds: Array(mutedJobIDs).sorted(),
            mutedHosts: nil,
            mutedJobNamePatterns: nil,
            allowedUsers: nil
        )

        APIClient.shared.updateNotificationPreferences(payload)
            .sink { [weak self] completion in
                if case .failure(let error) = completion {
                    self?.registrationStatusMessage = "Push preferences sync failed: \(error.localizedDescription)"
                }
            } receiveValue: { [weak self] response in
                guard let self else { return }
                let enabledText = response.enabled ? "enabled" : "muted"
                self.registrationStatusMessage = "Push notifications active (\(enabledText))"
            }
            .store(in: &cancellables)
    }

    func sendRemoteTestNotification() {
        let payload = NotificationTestRequest(
            title: "Test Notification",
            body: "This is a test notification from ssync",
            token: nil
        )

        APIClient.shared.sendTestNotification(payload)
            .sink { [weak self] completion in
                if case .failure(let error) = completion {
                    self?.registrationStatusMessage = "Test push failed: \(error.localizedDescription)"
                }
            } receiveValue: { [weak self] response in
                self?.registrationStatusMessage = response.sent > 0 ? "Test push sent" : "No push was sent"
            }
            .store(in: &cancellables)
    }

    func unregisterCurrentDevice(apiKeyOverride: String? = nil) {
        guard let token = deviceToken, !token.isEmpty else {
            isRemoteRegistrationSynced = false
            return
        }

        APIClient.shared.unregisterNotificationDevice(token: token, apiKeyOverride: apiKeyOverride)
            .sink { [weak self] completion in
                guard let self else { return }
                if case .failure(let error) = completion {
                    self.registrationStatusMessage = "Push unregister failed: \(error.localizedDescription)"
                }
            } receiveValue: { [weak self] _ in
                guard let self else { return }
                self.isRemoteRegistrationSynced = false
                self.registrationStatusMessage = "Push device unregistered"
            }
            .store(in: &cancellables)
    }

    func showJobNotification(job: Job) {
        guard JobPreferencesManager.shared.notificationsEnabled(for: job) else { return }
        guard job.state.isCompleted else { return }
        guard !usesRemoteDelivery else { return }

        let key = "\(job.host.lowercased())::\(job.id)"
        let shouldNotify: Bool = stateQueue.sync {
            if lastCompletionStateByJobKey[key] == job.state {
                return false
            }
            lastCompletionStateByJobKey[key] = job.state
            return true
        }

        if !shouldNotify {
            return
        }

        let content = UNMutableNotificationContent()
        content.title = "Job \(job.state.displayName)"
        content.body = "\(job.name) (\(job.id)) has \(job.state.displayName.lowercased())"
        content.sound = .default
        content.userInfo = [
            "jobId": job.id,
            "host": job.host
        ]
        content.categoryIdentifier = "JOB_NOTIFICATION"

        if #available(iOS 15.0, *), JobPreferencesManager.shared.isFavorite(job) {
            content.interruptionLevel = .timeSensitive
        }

        let request = UNNotificationRequest(
            identifier: "job-\(job.id)-\(job.host)-\(Date().timeIntervalSince1970)",
            content: content,
            trigger: nil
        )

        center.add(request) { error in
            if let error {
                print("Failed to show notification: \(error)")
            }
        }
    }

    func setupNotificationCategories() {
        let viewAction = UNNotificationAction(
            identifier: "VIEW_JOB",
            title: "View Job",
            options: [.foreground]
        )

        let muteAction = UNNotificationAction(
            identifier: "MUTE_JOB",
            title: "Mute This Job",
            options: []
        )

        let favoriteAction = UNNotificationAction(
            identifier: "FAVORITE_JOB",
            title: "Favorite",
            options: []
        )

        let category = UNNotificationCategory(
            identifier: "JOB_NOTIFICATION",
            actions: [viewAction, muteAction, favoriteAction],
            intentIdentifiers: [],
            options: []
        )

        center.setNotificationCategories([category])
    }

    func clearAllNotifications() {
        center.removeAllDeliveredNotifications()
        center.removeAllPendingNotificationRequests()
        let defaults = UserDefaults.standard
        defaults.removeObject(forKey: pendingJobIdKey)
        defaults.removeObject(forKey: pendingHostKey)
        stateQueue.sync {
            lastCompletionStateByJobKey.removeAll()
        }
    }

    func clearJobNotifications(jobId: String) {
        let notificationCenter = center
        notificationCenter.getDeliveredNotifications { notifications in
            let identifiers = notifications
                .filter { ($0.request.content.userInfo["jobId"] as? String) == jobId }
                .map { $0.request.identifier }

            notificationCenter.removeDeliveredNotifications(withIdentifiers: identifiers)
        }
    }

    func userNotificationCenter(
        _ center: UNUserNotificationCenter,
        willPresent notification: UNNotification,
        withCompletionHandler completionHandler: @escaping (UNNotificationPresentationOptions) -> Void
    ) {
        if #available(iOS 14.0, *) {
            completionHandler([.banner, .list, .sound])
        } else {
            completionHandler([.alert, .sound])
        }
    }

    func userNotificationCenter(
        _ center: UNUserNotificationCenter,
        didReceive response: UNNotificationResponse,
        withCompletionHandler completionHandler: @escaping () -> Void
    ) {
        let info = response.notification.request.content.userInfo
        let jobId = info["jobId"] as? String
        let host = (info["host"] as? String) ?? (info["hostname"] as? String)

        if let jobId, let host {
            switch response.actionIdentifier {
            case "MUTE_JOB":
                Task { @MainActor in
                    JobPreferencesManager.shared.setNotificationsEnabled(false, forJobId: jobId, host: host)
                }
            case "FAVORITE_JOB":
                Task { @MainActor in
                    JobPreferencesManager.shared.setFavorite(true, jobId: jobId, host: host)
                }
            case "VIEW_JOB", UNNotificationDefaultActionIdentifier:
                setPendingOpenJob(jobId: jobId, host: host)
                NotificationCenter.default.post(
                    name: .jobNotificationOpenJob,
                    object: nil,
                    userInfo: [
                        "jobId": jobId,
                        "host": host
                    ]
                )
            default:
                break
            }
        }

        completionHandler()
    }

    func consumePendingOpenJob() -> (jobId: String, host: String?)? {
        let defaults = UserDefaults.standard
        guard let jobId = defaults.string(forKey: pendingJobIdKey) else { return nil }
        let host = defaults.string(forKey: pendingHostKey)
        defaults.removeObject(forKey: pendingJobIdKey)
        defaults.removeObject(forKey: pendingHostKey)
        return (jobId, host)
    }

    private func setPendingOpenJob(jobId: String, host: String?) {
        let defaults = UserDefaults.standard
        defaults.set(jobId, forKey: pendingJobIdKey)
        defaults.set(host, forKey: pendingHostKey)
    }

    private func refreshAuthorizationStatus() {
        Task {
            authorizationStatus = await center.notificationSettings().authorizationStatus
        }
    }

    private var currentAPNsEnvironment: String {
        #if DEBUG
        return "sandbox"
        #else
        return "production"
        #endif
    }

    private var deviceIdentifier: String {
        let defaults = UserDefaults.standard
        if let existing = defaults.string(forKey: deviceIDKey), !existing.isEmpty {
            return existing
        }

        let created = UIDevice.current.identifierForVendor?.uuidString ?? UUID().uuidString
        defaults.set(created, forKey: deviceIDKey)
        return created
    }
}
