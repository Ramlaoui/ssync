import XCTest

@MainActor final class SsyncUITests: XCTestCase {
  override func setUpWithError() throws { continueAfterFailure = false }

  func testDemoOutputAndHostNavigation() {
    let app = XCUIApplication()
    app.launchArguments = ["--demo"]
    app.launch()
    XCTAssertTrue(app.buttons["job-48192"].waitForExistence(timeout: 10))
    capture("01-jobs", app: app)
    if !app.buttons["job-48192"].isHittable { app.swipeUp() }
    app.buttons["job-48192"].tap()
    XCTAssertTrue(app.buttons["watchOutput"].waitForExistence(timeout: 5))
    capture("02-job-detail", app: app)
    app.buttons["watchOutput"].tap()
    XCTAssertTrue(app.textFields["outputSearch"].waitForExistence(timeout: 5))
    app.textFields["outputSearch"].tap()
    app.textFields["outputSearch"].typeText("checkpoint")
    capture("03-output-search", app: app)
    app.swipeDown()
    app.tabBars.buttons["Hosts"].tap()
    let host = app.buttons["host-Atlas"]
    XCTAssertTrue(host.waitForExistence(timeout: 5))
    capture("04-hosts", app: app)
    host.tap()
    XCTAssertTrue(app.staticTexts["Partitions"].waitForExistence(timeout: 5))
    capture("05-host-detail", app: app)
  }

  func testDraftReviewNeverSubmitsWithoutExplicitConfirmation() {
    let app = XCUIApplication()
    app.launchArguments = ["--demo"]
    app.launch()
    app.tabBars.buttons["Launch"].tap()
    app.buttons["newLaunch"].tap()
    XCTAssertTrue(app.textFields["launchName"].waitForExistence(timeout: 5))
    app.textFields["launchName"].tap()
    app.textFields["launchName"].typeText("ui-review-test")
    app.swipeUp()
    app.swipeUp()
    app.swipeUp()
    let review = app.buttons["reviewLaunch"]
    if !review.isHittable { app.swipeUp() }
    review.tap()
    let submit = app.buttons["submitLaunch"]
    if !submit.isHittable { app.swipeUp() }
    XCTAssertTrue(submit.waitForExistence(timeout: 5))
    XCTAssertFalse(submit.isEnabled)
    capture("06-launch-review", app: app)
  }

  private func capture(_ name: String, app: XCUIApplication) {
    let attachment = XCTAttachment(screenshot: app.screenshot())
    attachment.name = name
    attachment.lifetime = .keepAlways
    add(attachment)
  }
}
