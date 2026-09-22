import Observation
import UIKit
import UserNotifications

extension Notification.Name {
  static let ssyncDeepLink = Notification.Name("ssyncDeepLink")
}

@MainActor @Observable final class NotificationService {
  static let shared = NotificationService()
  var status = "Not requested"
  var error: String?
  var registration = "Not registered"
  var pendingURL: URL?
  @ObservationIgnored var api: APIClient?
  func connect(api: APIClient?) async {
    self.api = api
    guard api != nil else { return }
    await refresh()
    if status == "Allowed" {
      UIApplication.shared.registerForRemoteNotifications()
    }
  }
  func enable(api: APIClient?) async {
    self.api = api
    do {
      let granted = try await UNUserNotificationCenter.current().requestAuthorization(options: [
        .alert, .sound, .badge,
      ])
      status = granted ? "Allowed" : "Not allowed"
      if granted { UIApplication.shared.registerForRemoteNotifications() }
    } catch { self.error = error.localizedDescription }
  }
  func refresh() async {
    let settings = await UNUserNotificationCenter.current().notificationSettings()
    switch settings.authorizationStatus {
    case .authorized, .provisional, .ephemeral: status = "Allowed"
    case .denied: status = "Not allowed"
    default: status = "Not requested"
    }
  }
  func register(token: String) async {
    UserDefaults.standard.set(token, forKey: "apnsToken")
    guard let api else {
      registration = "Connect a server to register this device"
      return
    }
    let deviceID: String
    if let saved = UserDefaults.standard.string(forKey: "deviceID") {
      deviceID = saved
    } else {
      deviceID = UUID().uuidString
      UserDefaults.standard.set(deviceID, forKey: "deviceID")
    }
    do {
      try await api.perform(
        "api/notifications/devices",
        body: .object([
          "token": .string(token), "platform": .string("ios"), "token_type": .string("apns"),
          "client_type": .string("native"), "payload_format": .string("apns"),
          "environment": .string(
            (Bundle.main.object(forInfoDictionaryKey: "SsyncAPNSEnvironment") as? String)
              == "development" ? "sandbox" : "production"),
          "bundle_id": .string(Bundle.main.bundleIdentifier ?? "com.ssync.mobile"),
          "device_id": .string(deviceID), "enabled": .bool(true),
        ]))
      registration = "Device registered"
      error = nil
    } catch {
      self.error = error.localizedDescription
      registration = "Registration failed"
    }
  }
}

@MainActor
final class NotificationDelegate: NSObject, UIApplicationDelegate, UNUserNotificationCenterDelegate
{
  func application(
    _ application: UIApplication,
    didFinishLaunchingWithOptions launchOptions: [UIApplication.LaunchOptionsKey: Any]? = nil
  ) -> Bool {
    UNUserNotificationCenter.current().delegate = self
    let open = UNNotificationAction(
      identifier: "OPEN_JOB", title: "Open job", options: [.foreground])
    UNUserNotificationCenter.current().setNotificationCategories([
      UNNotificationCategory(identifier: "JOB_NOTIFICATION", actions: [open], intentIdentifiers: [])
    ])
    return true
  }
  func application(
    _ application: UIApplication, didRegisterForRemoteNotificationsWithDeviceToken deviceToken: Data
  ) {
    let token = deviceToken.map { String(format: "%02x", $0) }.joined()
    Task { await NotificationService.shared.register(token: token) }
  }
  func application(
    _ application: UIApplication, didFailToRegisterForRemoteNotificationsWithError error: any Error
  ) {
    NotificationService.shared.error = error.localizedDescription
  }
  nonisolated func userNotificationCenter(
    _ center: UNUserNotificationCenter, willPresent notification: UNNotification
  ) async -> UNNotificationPresentationOptions {
    [.banner, .sound, .list]
  }
  nonisolated func userNotificationCenter(
    _ center: UNUserNotificationCenter, didReceive response: UNNotificationResponse
  ) async {
    let info = response.notification.request.content.userInfo
    let data = info["data"] as? [AnyHashable: Any] ?? info
    guard let host = data["hostname"] as? String else { return }
    let number = (data["job_id"] as? String) ?? (data["job_id"] as? NSNumber)?.stringValue
    guard let number else { return }
    let url = SystemJob(host: host, number: number, name: "", state: "", runtime: "", pinned: false)
      .url(connection: nil)
    await MainActor.run { NotificationService.shared.pendingURL = url }
  }
}
