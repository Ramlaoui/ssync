import AppIntents
import Foundation

struct ShowJobsIntent: AppIntent {
  static let title: LocalizedStringResource = "Show jobs"
  static let description = IntentDescription("Open your ssync workspace and job queue.")
  static let openAppWhenRun = true
  @MainActor func perform() async throws -> some IntentResult & OpensIntent {
    .result(opensIntent: OpenURLIntent(URL(string: "ssync://jobs")!))
  }
}
struct PrepareLaunchIntent: AppIntent {
  static let title: LocalizedStringResource = "Prepare a launch"
  static let description = IntentDescription(
    "Open ssync to prepare and review a launch. This never submits a job automatically.")
  static let openAppWhenRun = true
  @MainActor func perform() async throws -> some IntentResult & OpensIntent {
    .result(opensIntent: OpenURLIntent(URL(string: "ssync://launch")!))
  }
}
struct OpenJobIntent: AppIntent {
  static let title: LocalizedStringResource = "Open a job"
  static let openAppWhenRun = true
  @Parameter(title: "Host") var host: String
  @Parameter(title: "Job ID") var jobID: String
  @MainActor func perform() async throws -> some IntentResult & OpensIntent {
    let url = SystemJob(host: host, number: jobID, name: "", state: "", runtime: "", pinned: false)
      .url(connection: nil)
    return .result(opensIntent: OpenURLIntent(url))
  }
}
struct SsyncShortcuts: AppShortcutsProvider {
  static var appShortcuts: [AppShortcut] {
    AppShortcut(
      intent: ShowJobsIntent(),
      phrases: ["Show my jobs in \(.applicationName)", "Open my \(.applicationName) queue"],
      shortTitle: "Show jobs", systemImageName: "square.stack.3d.up")
    AppShortcut(
      intent: PrepareLaunchIntent(), phrases: ["Prepare a launch in \(.applicationName)"],
      shortTitle: "Prepare launch", systemImageName: "arrow.up.right")
  }
}
