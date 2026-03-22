// swift-tools-version: 5.9
import PackageDescription

let package = Package(
    name: "ssync",
    platforms: [
        .iOS(.v16)
    ],
    products: [
        .library(
            name: "ssync",
            targets: ["ssync"]
        ),
    ],
    dependencies: [
        .package(url: "https://github.com/Alamofire/Alamofire.git", from: "5.8.0"),
        .package(url: "https://github.com/daltoniam/Starscream.git", from: "4.0.0"),
        .package(url: "https://github.com/kishikawakatsumi/KeychainAccess.git", from: "4.2.0")
    ],
    targets: [
        .target(
            name: "ssync",
            dependencies: [
                "Alamofire",
                "Starscream",
                "KeychainAccess"
            ]
        ),
        .testTarget(
            name: "ssyncTests",
            dependencies: ["ssync"]
        ),
    ]
)