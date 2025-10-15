import SwiftUI

struct ContentView: View {
    @EnvironmentObject var authManager: AuthenticationManager
    @State private var showingSettings = false
    @State private var isUnlocked = false
    
    var body: some View {
        Group {
            if !authManager.isAuthenticated {
                AuthenticationView()
            } else if authManager.requiresBiometric && !isUnlocked {
                BiometricLockView(isUnlocked: $isUnlocked)
            } else {
                MainTabView()
            }
        }
        .onAppear {
            if authManager.requiresBiometric && authManager.isAuthenticated {
                unlockWithBiometrics()
            }
        }
    }
    
    private func unlockWithBiometrics() {
        authManager.authenticateWithBiometrics { success in
            if success {
                isUnlocked = true
            }
        }
    }
}

struct MainTabView: View {
    @State private var selectedTab = 0
    
    var body: some View {
        TabView(selection: $selectedTab) {
            JobListView()
                .tabItem {
                    Label("Jobs", systemImage: "server.rack")
                }
                .tag(0)
            
            HostsView()
                .tabItem {
                    Label("Hosts", systemImage: "network")
                }
                .tag(1)
            
            LaunchJobView()
                .tabItem {
                    Label("Launch", systemImage: "play.circle.fill")
                }
                .tag(2)
            
            SettingsView()
                .tabItem {
                    Label("Settings", systemImage: "gear")
                }
                .tag(3)
        }
    }
}

struct BiometricLockView: View {
    @Binding var isUnlocked: Bool
    @EnvironmentObject var authManager: AuthenticationManager
    
    var body: some View {
        VStack(spacing: 30) {
            Image(systemName: "lock.shield.fill")
                .font(.system(size: 80))
                .foregroundColor(.blue)
            
            Text("SLURM Manager")
                .font(.largeTitle)
                .fontWeight(.bold)
            
            Text("Authentication required")
                .font(.subheadline)
                .foregroundColor(.secondary)
            
            Button(action: unlock) {
                Label("Unlock", systemImage: "faceid")
                    .frame(maxWidth: 200)
                    .padding()
                    .background(Color.blue)
                    .foregroundColor(.white)
                    .cornerRadius(10)
            }
        }
        .padding()
        .onAppear {
            unlock()
        }
    }
    
    private func unlock() {
        authManager.authenticateWithBiometrics { success in
            if success {
                isUnlocked = true
            }
        }
    }
}

#Preview {
    ContentView()
        .environmentObject(AuthenticationManager.shared)
        .environmentObject(APIClient.shared)
        .environmentObject(JobManager.shared)
}