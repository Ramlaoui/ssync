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
    
    enum QuickFilter {
        case running, pending, myJobs
    }
    
    var hasActiveFilters: Bool {
        selectedHost != nil || selectedState != nil || !userFilter.isEmpty || showOnlyMyJobs
    }
    
    // Available options
    @Published var availableHosts: [String] = []
    
    private var currentPage = 1
    private let pageSize = 50
    private var cancellables = Set<AnyCancellable>()
    private var pollingTimer: Timer?
    
    init() {
        loadHosts()
        Task {
            await refreshJobs()
        }
    }
    
    func refreshJobs() async {
        isLoading = true
        errorMessage = nil
        currentPage = 1
        
        do {
            let response = try await fetchJobs(page: 1)
            jobs = response.jobs
            hasMorePages = response.jobs.count == pageSize
            availableHosts = response.hosts
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
            hasMorePages = response.jobs.count == pageSize
        } catch {
            errorMessage = error.localizedDescription
            currentPage -= 1
        }
        
        isLoading = false
    }
    
    private func fetchJobs(page: Int) async throws -> JobStatusResponse {
        return try await withCheckedThrowingContinuation { continuation in
            let user = showOnlyMyJobs ? getCurrentUsername() : userFilter.isEmpty ? nil : userFilter
            
            JobManager.shared.fetchJobs(
                host: selectedHost,
                user: user,
                state: selectedState,
                page: page,
                pageSize: pageSize
            )
            .sink(
                receiveCompletion: { completion in
                    if case .failure(let error) = completion {
                        continuation.resume(throwing: error)
                    }
                },
                receiveValue: { response in
                    continuation.resume(returning: response)
                }
            )
            .store(in: &cancellables)
        }
    }
    
    func resetFilters() {
        withAnimation {
            selectedHost = nil
            selectedState = nil
            userFilter = ""
            showOnlyMyJobs = false
        }
        Task {
            await refreshJobs()
        }
    }
    
    func applyQuickFilter(_ filter: QuickFilter) {
        resetFilters()
        
        withAnimation {
            switch filter {
            case .running:
                selectedState = .running
            case .pending:
                selectedState = .pending
            case .myJobs:
                showOnlyMyJobs = true
            }
        }
        
        Task {
            await refreshJobs()
        }
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
            
            // Update jobs while preserving selection
            for newJob in response.jobs {
                if let index = jobs.firstIndex(where: { $0.id == newJob.id }) {
                    jobs[index] = newJob
                } else {
                    // New job appeared, add to top
                    jobs.insert(newJob, at: 0)
                }
            }
            
            // Remove jobs that no longer exist
            jobs.removeAll { existingJob in
                !response.jobs.contains { $0.id == existingJob.id }
            }
        } catch {
            // Silent refresh - don't show errors
        }
    }
    
    private func loadHosts() {
        APIClient.shared.getHosts()
            .sink(
                receiveCompletion: { _ in },
                receiveValue: { [weak self] hosts in
                    self?.availableHosts = hosts.map { $0.displayName }
                }
            )
            .store(in: &cancellables)
    }
    
    private func getCurrentUsername() -> String? {
        // In a real app, this would get the username from the authentication context
        // For now, return nil
        return nil
    }
    
    deinit {
        stopPolling()
    }
}