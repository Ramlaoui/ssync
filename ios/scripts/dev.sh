#!/bin/bash
set -euo pipefail

ios_root="$(cd "$(dirname "$0")/.." && pwd)"
derived_data="${SSYNC_DERIVED_DATA:-/private/tmp/ssync-ios-build}"
action="${1:-build}"

case "$action" in
  generate)
    xcodegen generate --spec "$ios_root/project.yml"
    ;;
  build)
    xcodegen generate --spec "$ios_root/project.yml"
    xcodebuild -project "$ios_root/Ssync.xcodeproj" -scheme Ssync \
      -configuration Debug -sdk iphonesimulator \
      -destination 'generic/platform=iOS Simulator' \
      -derivedDataPath "$derived_data" CODE_SIGNING_ALLOWED=NO build-for-testing
    ;;
  test-core)
    export CLANG_MODULE_CACHE_PATH="${SSYNC_MODULE_CACHE:-/private/tmp/ssync-module-cache}"
    export SWIFTPM_MODULECACHE_OVERRIDE="$CLANG_MODULE_CACHE_PATH"
    swift test --package-path "$ios_root" --scratch-path /private/tmp/ssync-core-tests
    ;;
  test-ios)
    : "${SSYNC_SIMULATOR_ID:?Set SSYNC_SIMULATOR_ID to the ID of your booted iOS simulator}"
    xcodebuild -project "$ios_root/Ssync.xcodeproj" -scheme Ssync \
      -configuration Debug -destination "platform=iOS Simulator,id=$SSYNC_SIMULATOR_ID" \
      -derivedDataPath "$derived_data" CODE_SIGNING_ALLOWED=NO \
      -parallel-testing-enabled NO test
    ;;
  demo)
    : "${SSYNC_SIMULATOR_ID:?Set SSYNC_SIMULATOR_ID to the ID of your booted iOS simulator}"
    xcrun simctl install "$SSYNC_SIMULATOR_ID" "$derived_data/Build/Products/Debug-iphonesimulator/Ssync.app"
    xcrun simctl launch "$SSYNC_SIMULATOR_ID" com.ssync.mobile --demo
    ;;
  *)
    echo "Usage: ios/scripts/dev.sh {generate|build|test-core|test-ios|demo}" >&2
    exit 2
    ;;
esac
