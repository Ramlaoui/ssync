import Foundation
import Combine

@MainActor
class JobListViewModel: ObservableObject {
    @Published var jobs: [Job] = []
    @Published var isLoading = false
    @Published var errorMessage: String?
    @Published var hasMorePages = false
    
    // Filters
    @Published var selectedHost: String?
    @Published var selectedState: JobState?
    @Published var userFilter = ""
    @Published var showOnlyMyJobs = false
    @Published var hostOptions: [Host] = []
    
    enum QuickFilter {
        case running, pending, myJobs
    }
    
    var hasActiveFilters: Bool {
        selectedHost != nil || selectedState != nil || !userFilter.isEmpty || showOnlyMyJobs
    }
    
    private var currentPage = 1
    private let pageSize = 50
    private var cancellables = Set<AnyCancellable>()
    private var pollingTimer: Timer?
    
    init() {
        setupRealtimeUpdates()
        loadHosts()
        Task {
            await refreshJobs()
        }
    }
    
    func refreshJobs() async {
        guard !isLoading else { return }
        isLoading = true
        errorMessage = nil
        currentPage = 1
        
        do {
            let response = try await fetchJobs(page: 1)
            jobs = response.jobs.sorted(by: Job.listSortComparator)
            hasMorePages = (response.page * response.pageSize) < response.total
            mergeHosts(from: response.hosts)
            for job in response.jobs {
                LiveActivityManager.shared.handleJobUpdate(job)
            }
        } catch {
            errorMessage = error.localizedDescription
            jobs = []
        }
        
        isLoading = false
    }
    
    func loadMoreJobs() async {
        guard !isLoading, hasMorePages else { return }
        
        isLoading = true
        currentPage += 1
        
        do {
            let response = try await fetchJobs(page: currentPage)
            jobs.append(contentsOf: response.jobs)
            jobs.sort(by: Job.listSortComparator)
            hasMorePages = (response.page * response.pageSize) < response.total
            for job in response.jobs {
                LiveActivityManager.shared.handleJobUpdate(job)
            }
        } catch {
            errorMessage = error.localizedDescription
            currentPage -= 1
        }
        
        isLoading = false
    }
    
    private func fetchJobs(page: Int) async throws -> JobStatusResponse {
        let enteredUser = userFilter.trimmingCharacters(in: .whitespacesAndNewlines)
        let currentUser = showOnlyMyJobs ? getCurrentUsername() : nil
        if showOnlyMyJobs && currentUser == nil && enteredUser.isEmpty {
            throw NSError(
                domain: "JobListViewModel",
                code: 1,
                userInfo: [NSLocalizedDescriptionKey: "Current username is unavailable. Disable 'My Jobs' or set a user filter."]
            )
        }
        let user = showOnlyMyJobs ? (currentUser ?? (enteredUser.isEmpty ? nil : enteredUser)) : (enteredUser.isEmpty ? nil : enteredUser)

        return try await JobManager.shared.fetchJobs(
            host: selectedHost,
            user: user,
            state: selectedState,
            page: page,
            pageSize: pageSize
        ).async()
    }
    
    func resetFilters() {
        clearFilters()
        Task {
            await refreshJobs()
        }
    }

    func applyQuickFilter(_ filter: QuickFilter) {
        clearFilters()

        switch filter {
        case .running:
            selectedState = .running
        case .pending:
            selectedState = .pending
        case .myJobs:
            guard getCurrentUsername() != nil else {
                errorMessage = "Current username is unavailable. Use the User filter instead."
                return
            }
            showOnlyMyJobs = true
        }

        Task {
            await refreshJobs()
        }
    }

    private func clearFilters() {
        selectedHost = nil
        selectedState = nil
        userFilter = ""
        showOnlyMyJobs = false
    }
    
    func startPolling() {
        stopPolling()
        
        pollingTimer = Timer.scheduledTimer(withTimeInterval: 10, repeats: true) { _ in
            Task { @MainActor in
                // Only refresh if not loading and on first page
                if !self.isLoading && self.currentPage == 1 {
                    await self.silentRefresh()
                }
            }
        }
    }
    
    func stopPolling() {
        pollingTimer?.invalidate()
        pollingTimer = nil
    }
    
    private func silentRefresh() async {
        do {
            let response = try await fetchJobs(page: 1)
            jobs = response.jobs.sorted(by: Job.listSortComparator)
            hasMorePages = (response.page * response.pageSize) < response.total
            mergeHosts(from: response.hosts)
            for job in response.jobs {
                LiveActivityManager.shared.handleJobUpdate(job)
            }
        } catch {
            // Silent refresh - don't show errors
        }
    }
    
    private func loadHosts() {
        APIClient.shared.getHosts()
            .sink(
                receiveCompletion: { [weak self] completion in
                    if case .failure(let error) = completion {
                        self?.errorMessage = error.localizedDescription
                    }
                },
                receiveValue: { [weak self] hosts in
                    guard let self else { return }
                    self.hostOptions = hosts.sorted { $0.displayName.localizedCaseInsensitiveCompare($1.displayName) == .orderedAscending }
                    if let selectedHost = self.selectedHost,
                       !self.hostOptions.contains(where: { $0.hostname == selectedHost }) {
                        self.selectedHost = nil
                    }
                }
            )
            .store(in: &cancellables)
    }
    
    private func setupRealtimeUpdates() {
        NotificationCenter.default.publisher(for: .jobStatusUpdated)
            .compactMap { $0.object as? Job }
            .receive(on: DispatchQueue.main)
            .sink { [weak self] updatedJob in
                self?.handleRealtimeUpdate(updatedJob)
            }
            .store(in: &cancellables)
    }

    private func handleRealtimeUpdate(_ updatedJob: Job) {
        guard currentPage == 1 else { return }

        if jobMatchesCurrentFilters(updatedJob) {
            if let existingIndex = jobs.firstIndex(where: { $0.id == updatedJob.id }) {
                jobs[existingIndex] = updatedJob
            } else {
                jobs.insert(updatedJob, at: 0)
            }
            jobs.sort(by: Job.listSortComparator)
        } else {
            jobs.removeAll { $0.id == updatedJob.id }
        }
    }

    private func jobMatchesCurrentFilters(_ job: Job) -> Bool {
        if let selectedHost {
            let normalizedSelected = selectedHost.lowercased()
            let normalizedJobHost = job.host.lowercased()
            let matchesHost = normalizedJobHost == normalizedSelected || normalizedJobHost.hasPrefix("\(normalizedSelected).")
            if !matchesHost {
                return false
            }
        }

        if let selectedState, job.state != selectedState {
            return false
        }

        let enteredUser = userFilter.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
        if !enteredUser.isEmpty {
            if (job.user ?? "").lowercased() != enteredUser {
                return false
            }
        }

        if showOnlyMyJobs, let currentUser = getCurrentUsername()?.lowercased() {
            if (job.user ?? "").lowercased() != currentUser {
                return false
            }
        }

        return true
    }

    private func mergeHosts(from hostnames: [String]) {
        guard !hostnames.isEmpty else { return }

        let existing = Set(hostOptions.map { $0.hostname.lowercased() })
        let unknownHosts = hostnames
            .filter { !existing.contains($0.lowercased()) }
            .map {
                Host(
                    id: $0,
                    name: $0,
                    hostname: $0,
                    username: nil,
                    port: 22,
                    workDir: "",
                    isDefault: false,
                    isAvailable: true,
                    lastError: nil
                )
            }

        if !unknownHosts.isEmpty {
            hostOptions.append(contentsOf: unknownHosts)
            hostOptions.sort {
                $0.displayName.localizedCaseInsensitiveCompare($1.displayName) == .orderedAscending
            }
        }
    }

    private func getCurrentUsername() -> String? {
        let stored = UserDefaults.standard.string(forKey: "ssync_current_username")?
            .trimmingCharacters(in: .whitespacesAndNewlines)
        if let stored, !stored.isEmpty {
            return stored
        }
        return nil
    }
    
    deinit {
        Task { @MainActor [weak self] in
            self?.stopPolling()
        }
    }
}
