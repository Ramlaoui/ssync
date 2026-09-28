import SwiftUI

struct WatcherActionFields: View {
  var type: String
  @Binding var parameters: String
  var body: some View {
    Group {
      switch type {
      case "log_event":
        TextField("Event message", text: text("message"))
        Picker("Level", selection: text("level", fallback: "INFO")) {
          Text("Info").tag("INFO")
          Text("Warning").tag("WARNING")
          Text("Error").tag("ERROR")
        }
      case "cancel_job":
        TextField("Cancellation reason", text: text("reason"))
        Text("Stops this job when the watcher matches.").font(.caption).foregroundStyle(.secondary)
      case "resubmit":
        TextField("Remaining resubmits", text: text("remaining_resubmits", numeric: true))
          .keyboardType(.numberPad)
        Toggle("Cancel the previous job first", isOn: flag("cancel_previous", fallback: true))
        Text(
          "Uses the saved submission script and captured values. A limit of 1 permits one resubmission. Set directive changes in Advanced parameters."
        ).font(.caption).foregroundStyle(.secondary)
      case "notify_email":
        TextField("Recipient", text: text("to")).keyboardType(.emailAddress).textContentType(
          .emailAddress)
        TextField("Subject", text: text("subject"))
        TextField("Message", text: text("message"), axis: .vertical)
      case "store_metric":
        TextField("Metric name", text: text("name"))
        TextField("Captured variable", text: text("variable"))
        TextField("Fixed value (optional)", text: text("value"))
      case "run_command":
        TextField("Server command", text: text("command"), axis: .vertical).font(
          .system(.caption, design: .monospaced))
        Text("Runs only when allowed by your server’s command policy.").font(.caption)
          .foregroundStyle(.secondary)
      default:
        Text("This action’s existing parameters are preserved.").font(.caption).foregroundStyle(
          .secondary)
      }
    }.textInputAutocapitalization(.never).autocorrectionDisabled()
  }
  private func text(_ key: String, fallback: String = "", numeric: Bool = false) -> Binding<String>
  {
    Binding(
      get: { object[key]?.string ?? fallback },
      set: { value in
        var fields = object
        if value.isEmpty {
          fields.removeValue(forKey: key)
        } else if numeric, let number = Double(value) {
          fields[key] = .number(number)
        } else {
          fields[key] = .string(value)
        }
        parameters = JSONValue.object(fields).pretty
      })
  }
  private func flag(_ key: String, fallback: Bool) -> Binding<Bool> {
    Binding(
      get: { object[key]?.bool ?? fallback },
      set: { value in
        var fields = object
        fields[key] = .bool(value)
        parameters = JSONValue.object(fields).pretty
      })
  }
  private var object: [String: JSONValue] {
    (try? JSONDecoder().decode(JSONValue.self, from: Data(parameters.utf8)))?.object ?? [:]
  }
}
