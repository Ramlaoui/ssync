# SLURM Manager iOS App

Native iOS client for the SLURM Manager API, providing mobile access to monitor and manage SLURM jobs.

## Features

- 📱 **Native iOS Experience**: Built with SwiftUI for smooth, responsive UI
- 🔐 **Secure Authentication**: API key storage in iOS Keychain with Face ID/Touch ID support
- 📊 **Real-time Updates**: WebSocket connection for live job status updates
- 🔔 **Push Notifications**: Get notified when jobs complete or fail
- 📋 **Job Management**: View, monitor, and cancel jobs from anywhere
- 🌐 **Multi-host Support**: Manage jobs across multiple SLURM clusters
- 🔍 **Search & Filter**: Quickly find jobs by name, ID, user, or state

## Requirements

- iOS 16.0+
- Xcode 14.0+
- Swift 5.9+
- SLURM Manager API server with authentication enabled

## Setup

### 1. Open in Xcode

```bash
cd ios-app/SlurmManager
open SlurmManager.xcodeproj
```

### 2. Configure Bundle ID

In Xcode:
1. Select the project in the navigator
2. Select the SlurmManager target
3. Change Bundle Identifier to your organization's ID (e.g., `com.yourcompany.slurmmanager`)

### 3. Install Dependencies

The app uses Swift Package Manager for dependencies. They should auto-install when you open the project.

Dependencies:
- **Alamofire**: HTTP networking
- **Starscream**: WebSocket client
- **KeychainAccess**: Secure credential storage

### 4. Configure App Transport Security

For development with self-signed certificates, the app is configured to allow localhost connections. For production, update `Info.plist` with your server's domain.

## Building & Running

### Development

1. Select your target device or simulator
2. Press `Cmd+R` to build and run
3. Enter your server URL and API key on first launch

### TestFlight Beta

1. Archive the app: `Product > Archive`
2. Upload to App Store Connect
3. Distribute via TestFlight

### Production Release

1. Ensure all development settings are updated for production
2. Update version and build numbers
3. Archive and submit to App Store

## Architecture

```
SlurmManager/
├── Models/           # Data models matching API responses
├── Services/         # API client, WebSocket, Auth, Notifications
├── Views/            # SwiftUI views
├── ViewModels/       # View logic and state management
└── Utilities/        # Keychain, helpers
```

### Key Components

- **APIClient**: Handles all REST API communication
- **WebSocketManager**: Manages real-time job updates
- **AuthenticationManager**: Handles API key and biometric auth
- **JobManager**: Central job data management and caching
- **NotificationManager**: Push notification handling

## Security

- API keys stored in iOS Keychain (hardware encrypted)
- Optional Face ID/Touch ID protection
- Certificate pinning for production (needs configuration)
- All network traffic over HTTPS/WSS

## Configuration

### Server URL

The server URL can be changed in Settings after authentication. Format:
- Development: `https://localhost:8042`
- Production: `https://your-server.com:8042`

### API Key Generation

On your SLURM server:
```bash
# Generate API key
ssync auth setup

# Enable authentication
export SSYNC_REQUIRE_API_KEY=true
ssync web
```

## Features Roadmap

- [ ] Widget for home screen job status
- [ ] Siri Shortcuts integration
- [ ] iPad optimized UI
- [ ] Offline mode with sync
- [ ] Job template library
- [ ] Dark mode support
- [ ] Export job data
- [ ] Multiple API key profiles

## Troubleshooting

### Connection Issues

1. Verify server is running: `ssync web --status`
2. Check API key is valid: `ssync auth validate`
3. Ensure phone and server are on same network (for localhost)
4. Check firewall allows port 8042

### Certificate Warnings

For development with self-signed certificates:
1. The app accepts self-signed certs for localhost
2. For other hosts, add certificate exception in Info.plist

### WebSocket Connection

If real-time updates aren't working:
1. Check WebSocket status in Settings
2. Ensure server has WebSocket support enabled
3. Try disconnecting and reconnecting

## Contributing

1. Fork the repository
2. Create a feature branch
3. Implement your feature with tests
4. Submit a pull request

## License

Same as SLURM Manager main project