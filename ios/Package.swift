// swift-tools-version: 6.0
import PackageDescription

let package = Package(
  name: "SsyncCore",
  platforms: [.macOS(.v14), .iOS("26.0")],
  products: [.library(name: "SsyncCore", targets: ["SsyncCore"])],
  targets: [
    .target(name: "SsyncCore", path: "Core", exclude: ["Persistence"]),
    .testTarget(name: "SsyncCoreTests", dependencies: ["SsyncCore"], path: "Tests/Unit"),
  ]
)
