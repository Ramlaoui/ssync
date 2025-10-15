import Foundation
import SwiftUI

// MARK: - App Error Types
enum AppError: LocalizedError {
    case network(NetworkError)
    case authentication(AuthError)
    case validation(ValidationError)
    case server(ServerError)
    case unknown(Error)
    
    var errorDescription: String? {
        switch self {
        case .network(let error):
            return error.userFriendlyMessage
        case .authentication(let error):
            return error.userFriendlyMessage
        case .validation(let error):
            return error.userFriendlyMessage
        case .server(let error):
            return error.userFriendlyMessage
        case .unknown(let error):
            return "An unexpected error occurred: \(error.localizedDescription)"
        }
    }
    
    var recoverySuggestion: String? {
        switch self {
        case .network(let error):
            return error.recoverySuggestion
        case .authentication(let error):
            return error.recoverySuggestion
        case .validation(let error):
            return error.recoverySuggestion
        case .server(let error):
            return error.recoverySuggestion
        case .unknown:
            return "Please try again. If the problem persists, contact support."
        }
    }
    
    var isRetryable: Bool {
        switch self {
        case .network(let error):
            return error.isRetryable
        case .authentication:
            return false
        case .validation:
            return false
        case .server(let error):
            return error.isRetryable
        case .unknown:
            return true
        }
    }
}

// MARK: - Network Errors
enum NetworkError: LocalizedError {
    case noConnection
    case timeout
    case serverUnreachable
    case invalidResponse
    case requestFailed(Int) // HTTP status code
    
    var userFriendlyMessage: String {
        switch self {
        case .noConnection:
            return "No internet connection"
        case .timeout:
            return "Request timed out"
        case .serverUnreachable:
            return "Cannot connect to server"
        case .invalidResponse:
            return "Invalid response from server"
        case .requestFailed(let code):
            return "Request failed (Error \(code))"
        }
    }
    
    var recoverySuggestion: String {
        switch self {
        case .noConnection:
            return "Please check your internet connection and try again."
        case .timeout:
            return "The server is taking too long to respond. Please try again."
        case .serverUnreachable:
            return "Make sure the server is running and the URL is correct."
        case .invalidResponse:
            return "The server returned an unexpected response. Please try again."
        case .requestFailed(let code) where code >= 500:
            return "Server error. Please try again later."
        case .requestFailed(let code) where code == 404:
            return "The requested resource was not found."
        case .requestFailed:
            return "Please check your request and try again."
        }
    }
    
    var isRetryable: Bool {
        switch self {
        case .noConnection, .timeout, .serverUnreachable:
            return true
        case .requestFailed(let code) where code >= 500:
            return true
        case .invalidResponse, .requestFailed:
            return false
        }
    }
}

// MARK: - Authentication Errors
enum AuthError: LocalizedError {
    case invalidCredentials
    case tokenExpired
    case unauthorized
    case biometricFailed
    case keychainError
    
    var userFriendlyMessage: String {
        switch self {
        case .invalidCredentials:
            return "Invalid API key or server URL"
        case .tokenExpired:
            return "Your session has expired"
        case .unauthorized:
            return "You are not authorized to perform this action"
        case .biometricFailed:
            return "Biometric authentication failed"
        case .keychainError:
            return "Failed to access secure storage"
        }
    }
    
    var recoverySuggestion: String {
        switch self {
        case .invalidCredentials:
            return "Please check your API key and server URL."
        case .tokenExpired:
            return "Please sign in again."
        case .unauthorized:
            return "Please check your permissions or contact an administrator."
        case .biometricFailed:
            return "Please try again or use your passcode."
        case .keychainError:
            return "Please try signing in again."
        }
    }
}

// MARK: - Validation Errors
enum ValidationError: LocalizedError {
    case emptyField(String)
    case invalidFormat(String)
    case outOfRange(String, min: Any?, max: Any?)
    
    var userFriendlyMessage: String {
        switch self {
        case .emptyField(let field):
            return "\(field) cannot be empty"
        case .invalidFormat(let field):
            return "\(field) has an invalid format"
        case .outOfRange(let field, let min, let max):
            if let min = min, let max = max {
                return "\(field) must be between \(min) and \(max)"
            } else if let min = min {
                return "\(field) must be at least \(min)"
            } else if let max = max {
                return "\(field) must be at most \(max)"
            }
            return "\(field) is out of range"
        }
    }
    
    var recoverySuggestion: String {
        switch self {
        case .emptyField:
            return "Please fill in all required fields."
        case .invalidFormat:
            return "Please check the format and try again."
        case .outOfRange:
            return "Please enter a valid value."
        }
    }
}

// MARK: - Server Errors
enum ServerError: LocalizedError {
    case jobNotFound(String)
    case hostUnavailable(String)
    case operationFailed(String)
    case quotaExceeded
    case maintenance
    
    var userFriendlyMessage: String {
        switch self {
        case .jobNotFound(let id):
            return "Job \(id) not found"
        case .hostUnavailable(let host):
            return "Host \(host) is unavailable"
        case .operationFailed(let operation):
            return "\(operation) failed"
        case .quotaExceeded:
            return "Resource quota exceeded"
        case .maintenance:
            return "Server is under maintenance"
        }
    }
    
    var recoverySuggestion: String {
        switch self {
        case .jobNotFound:
            return "The job may have been deleted or completed."
        case .hostUnavailable:
            return "Please try a different host or check the connection."
        case .operationFailed:
            return "Please try again or contact support if the problem persists."
        case .quotaExceeded:
            return "Please wait for resources to become available or contact an administrator."
        case .maintenance:
            return "Please try again later."
        }
    }
    
    var isRetryable: Bool {
        switch self {
        case .jobNotFound:
            return false
        case .hostUnavailable, .operationFailed, .quotaExceeded, .maintenance:
            return true
        }
    }
}

// MARK: - Error Alert Modifier
struct ErrorAlert: ViewModifier {
    @Binding var error: AppError?
    let onRetry: (() -> Void)?
    
    func body(content: Content) -> some View {
        content
            .alert(
                "Error",
                isPresented: .constant(error != nil),
                presenting: error
            ) { error in
                if error.isRetryable, let onRetry = onRetry {
                    Button("Retry") {
                        HapticManager.impact(.light)
                        onRetry()
                    }
                }
                Button("OK", role: .cancel) {
                    self.error = nil
                }
            } message: { error in
                VStack {
                    Text(error.errorDescription ?? "Unknown error")
                    if let suggestion = error.recoverySuggestion {
                        Text(suggestion)
                            .font(.caption)
                    }
                }
            }
    }
}

extension View {
    func errorAlert(error: Binding<AppError?>, onRetry: (() -> Void)? = nil) -> some View {
        modifier(ErrorAlert(error: error, onRetry: onRetry))
    }
}

// MARK: - Toast Manager
class ToastManager: ObservableObject {
    static let shared = ToastManager()
    
    @Published var currentToast: Toast?
    
    struct Toast: Identifiable {
        let id = UUID()
        let message: String
        let type: ToastView.ToastType
    }
    
    func show(_ message: String, type: ToastView.ToastType = .info) {
        DispatchQueue.main.async {
            self.currentToast = Toast(message: message, type: type)
            
            // Auto dismiss after 3 seconds
            DispatchQueue.main.asyncAfter(deadline: .now() + 3) {
                if self.currentToast?.id == self.currentToast?.id {
                    withAnimation {
                        self.currentToast = nil
                    }
                }
            }
        }
        
        // Haptic feedback
        switch type {
        case .success:
            HapticManager.notification(.success)
        case .error:
            HapticManager.notification(.error)
        case .warning:
            HapticManager.notification(.warning)
        case .info:
            HapticManager.impact(.light)
        }
    }
}