import SwiftUI

struct AuthenticationView: View {
    @EnvironmentObject var authManager: AuthenticationManager
    @State private var serverURL = ""
    @State private var apiKey = ""
    @State private var isLoading = false
    @State private var errorMessage: String?
    @State private var showingHelp = false
    
    var body: some View {
        NavigationView {
            Form {
                Section {
                    VStack(spacing: 20) {
                        Image(systemName: "server.rack")
                            .font(.system(size: 60))
                            .foregroundColor(.blue)
                        
                        Text("SLURM Manager")
                            .font(.largeTitle)
                            .fontWeight(.bold)
                        
                        Text("Connect to your SLURM cluster")
                            .font(.subheadline)
                            .foregroundColor(.secondary)
                    }
                    .frame(maxWidth: .infinity)
                    .padding(.vertical, 20)
                }
                .listRowBackground(Color.clear)
                
                Section("Server Configuration") {
                    HStack {
                        Image(systemName: "link")
                            .foregroundColor(.secondary)
                        TextField("Server URL", text: $serverURL)
                            .textInputAutocapitalization(.never)
                            .autocorrectionDisabled()
                            .keyboardType(.URL)
                    }
                    
                    HStack {
                        Image(systemName: "key.fill")
                            .foregroundColor(.secondary)
                        SecureField("API Key", text: $apiKey)
                            .textInputAutocapitalization(.never)
                            .autocorrectionDisabled()
                    }
                }
                
                if let error = errorMessage {
                    Section {
                        HStack {
                            Image(systemName: "exclamationmark.triangle.fill")
                                .foregroundColor(.red)
                            Text(error)
                                .foregroundColor(.red)
                                .font(.caption)
                        }
                    }
                }
                
                Section {
                    Button(action: authenticate) {
                        HStack {
                            if isLoading {
                                ProgressView()
                                    .progressViewStyle(CircularProgressViewStyle())
                                    .scaleEffect(0.8)
                            } else {
                                Image(systemName: "arrow.right.circle.fill")
                            }
                            Text("Connect")
                                .fontWeight(.semibold)
                        }
                        .frame(maxWidth: .infinity)
                    }
                    .disabled(serverURL.isEmpty || apiKey.isEmpty || isLoading)
                }
                
                Section {
                    Button(action: { showingHelp = true }) {
                        HStack {
                            Image(systemName: "questionmark.circle")
                            Text("How to get API credentials")
                            Spacer()
                            Image(systemName: "chevron.right")
                                .font(.caption)
                                .foregroundColor(.secondary)
                        }
                    }
                    .foregroundColor(.blue)
                }
            }
            .navigationBarHidden(true)
            .onAppear {
                serverURL = authManager.serverURL
                apiKey = authManager.apiKey
            }
            .sheet(isPresented: $showingHelp) {
                HelpView()
            }
        }
    }
    
    private func authenticate() {
        errorMessage = nil
        isLoading = true
        
        // Update auth manager
        authManager.serverURL = serverURL
        authManager.apiKey = apiKey
        
        // Test connection
        authManager.testConnection { success, error in
            isLoading = false
            
            if success {
                // Save credentials
                if authManager.saveCredentials() {
                    // Success - the view will automatically update
                } else {
                    errorMessage = "Failed to save credentials"
                }
            } else {
                errorMessage = error ?? "Connection failed"
            }
        }
    }
}

struct HelpView: View {
    @Environment(\.dismiss) var dismiss
    
    var body: some View {
        NavigationView {
            ScrollView {
                VStack(alignment: .leading, spacing: 20) {
                    Section {
                        Text("Getting Started")
                            .font(.title2)
                            .fontWeight(.bold)
                        
                        Text("To connect to your SLURM cluster, you need:")
                            .padding(.bottom, 5)
                        
                        VStack(alignment: .leading, spacing: 10) {
                            Label("Server URL (e.g., https://your-server:8042)", systemImage: "1.circle.fill")
                            Label("API Key for authentication", systemImage: "2.circle.fill")
                        }
                        .font(.callout)
                    }
                    
                    Divider()
                    
                    Section {
                        Text("Generate API Key")
                            .font(.title2)
                            .fontWeight(.bold)
                        
                        Text("On your server, run:")
                            .padding(.bottom, 5)
                        
                        CodeBlock(text: "ssync auth setup")
                        
                        Text("This will generate an API key and show you where it's stored.")
                            .font(.caption)
                            .foregroundColor(.secondary)
                    }
                    
                    Divider()
                    
                    Section {
                        Text("Enable Authentication")
                            .font(.title2)
                            .fontWeight(.bold)
                        
                        Text("Make sure the API server has authentication enabled:")
                            .padding(.bottom, 5)
                        
                        CodeBlock(text: "export SSYNC_REQUIRE_API_KEY=true\nssync web")
                        
                        Text("Without authentication, anyone can access your SLURM cluster!")
                            .font(.caption)
                            .foregroundColor(.red)
                    }
                    
                    Divider()
                    
                    Section {
                        Text("Security Notes")
                            .font(.title2)
                            .fontWeight(.bold)
                        
                        VStack(alignment: .leading, spacing: 10) {
                            Label("Your API key is stored securely in the iOS Keychain", systemImage: "lock.shield.fill")
                                .foregroundColor(.green)
                            
                            Label("Use HTTPS to encrypt communication", systemImage: "lock.fill")
                                .foregroundColor(.blue)
                            
                            Label("Enable Face ID/Touch ID for extra security", systemImage: "faceid")
                                .foregroundColor(.blue)
                            
                            Label("Never share your API key with others", systemImage: "exclamationmark.shield.fill")
                                .foregroundColor(.orange)
                        }
                        .font(.callout)
                    }
                }
                .padding()
            }
            .navigationTitle("Help")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .navigationBarTrailing) {
                    Button("Done") {
                        dismiss()
                    }
                }
            }
        }
    }
}

struct CodeBlock: View {
    let text: String
    @State private var copied = false
    
    var body: some View {
        HStack {
            Text(text)
                .font(.system(.caption, design: .monospaced))
                .foregroundColor(.primary)
            
            Spacer()
            
            Button(action: copyToClipboard) {
                Image(systemName: copied ? "checkmark" : "doc.on.doc")
                    .font(.caption)
                    .foregroundColor(.blue)
            }
        }
        .padding(10)
        .background(Color(.systemGray6))
        .cornerRadius(8)
    }
    
    private func copyToClipboard() {
        UIPasteboard.general.string = text
        copied = true
        
        DispatchQueue.main.asyncAfter(deadline: .now() + 2) {
            copied = false
        }
    }
}

#Preview {
    AuthenticationView()
        .environmentObject(AuthenticationManager.shared)
}