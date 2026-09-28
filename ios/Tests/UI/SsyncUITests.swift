import XCTest

@MainActor final class SsyncUITests: XCTestCase {
  override func setUpWithError() throws { continueAfterFailure = false }

  func testDemoOutputAndClusterNavigation() {
    let app = XCUIApplication()
    app.launchArguments = ["--demo"]
    app.launch()
    XCTAssertTrue(app.buttons["job-48192"].waitForExistence(timeout: 10))
    capture("01-jobs", app: app)
    let running = app.buttons.matching(NSPredicate(format: "label BEGINSWITH 'Running'")).firstMatch
    running.tap()
    XCTAssertTrue(app.buttons["job-48194"].waitForNonExistence(timeout: 3))
    running.tap()
    XCTAssertTrue(app.buttons["job-48194"].waitForExistence(timeout: 3))
    app.buttons["job-48196"].press(forDuration: 1.2)
    XCTAssertTrue(app.buttons["Relaunch…"].waitForExistence(timeout: 3))
    capture("01b-job-preview", app: app)
    app.coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: 0.22)).tap()
    XCTAssertTrue(app.buttons["Relaunch…"].waitForNonExistence(timeout: 3))
    app.buttons["job-48192"].tap()
    XCTAssertTrue(app.buttons["watchOutput"].waitForExistence(timeout: 5))
    capture("02-job-detail", app: app)
    app.swipeUp()
    capture("02b-job-facts", app: app)
    app.swipeDown()
    app.buttons["watchOutput"].tap()
    XCTAssertTrue(app.buttons["outputFind"].waitForExistence(timeout: 5))
    app.buttons["outputFind"].tap()
    XCTAssertTrue(app.textFields["outputSearch"].waitForExistence(timeout: 5))
    app.textFields["outputSearch"].typeText("checkpoint")
    capture("03-output-search", app: app)
    app.navigationBars.buttons.element(boundBy: 0).tap()
    app.navigationBars.buttons.element(boundBy: 0).tap()
    app.tabBars.buttons["Cluster"].tap()
    let host = app.buttons["host-Atlas"]
    XCTAssertTrue(host.waitForExistence(timeout: 5))
    capture("04-cluster", app: app)
    host.tap()
    XCTAssertTrue(app.navigationBars["Atlas"].waitForExistence(timeout: 5))
    capture("05-host-detail", app: app)
    app.tabBars.buttons["Activity"].tap()
    XCTAssertTrue(app.staticTexts["Resume from checkpoint"].waitForExistence(timeout: 5))
    capture("06-activity", app: app)
  }

  func testLaunchReviewRequiresAnExplicitSubmit() {
    let app = XCUIApplication()
    app.launchArguments = ["--demo"]
    app.launch()
    XCTAssertTrue(app.buttons["newLaunch"].waitForExistence(timeout: 10))
    app.buttons["newLaunch"].tap()
    XCTAssertTrue(app.buttons["blankLaunch"].waitForExistence(timeout: 5))
    capture("07-launch-start", app: app)
    app.buttons["blankLaunch"].tap()
    XCTAssertTrue(app.textFields["launchName"].waitForExistence(timeout: 5))
    app.textFields["launchName"].tap()
    app.textFields["launchName"].typeText("ui-review-test")
    capture("08-launch-editor", app: app)
    app.buttons["reviewLaunch"].tap()
    let submit = app.buttons["submitLaunch"]
    XCTAssertTrue(submit.waitForExistence(timeout: 5))
    XCTAssertTrue(submit.isEnabled)
    // Reviewing alone never submits.
    XCTAssertFalse(app.staticTexts["Open job"].exists)
    capture("09-launch-review", app: app)
  }

  private func capture(_ name: String, app: XCUIApplication) {
    let attachment = XCTAttachment(screenshot: app.screenshot())
    attachment.name = name
    attachment.lifetime = .keepAlways
    add(attachment)
  }
}
