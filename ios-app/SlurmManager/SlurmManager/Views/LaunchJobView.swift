import SwiftUI

struct LaunchJobView: View {
    @State private var scriptPath = ""
    @State private var sourceDir = ""
    @State private var selectedHost = ""
    @State private var jobName = ""
    
    var body: some View {
        NavigationView {
            Form {
                Section("Job Configuration") {
                    TextField("Job Name", text: $jobName)
                    TextField("Script Path", text: $scriptPath)
                    TextField("Source Directory", text: $sourceDir)
                    Picker("Host", selection: $selectedHost) {
                        Text("Select Host").tag("")
                    }
                }
                
                Section {
                    Button(action: launchJob) {
                        HStack {
                            Image(systemName: "play.circle.fill")
                            Text("Launch Job")
                        }
                        .frame(maxWidth: .infinity)
                    }
                    .disabled(scriptPath.isEmpty || sourceDir.isEmpty || selectedHost.isEmpty)
                }
            }
            .navigationTitle("Launch Job")
        }
    }
    
    func launchJob() {
        // Implementation would submit job via API
    }
}