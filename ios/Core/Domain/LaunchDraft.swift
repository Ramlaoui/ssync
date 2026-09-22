import Foundation

struct LaunchDraft: Codable, Identifiable, Equatable, Sendable {
  var id = UUID()
  var name = ""
  var host = ""
  var source = ""
  var script = "#!/bin/bash\n#SBATCH --job-name=my-job\n\npython train.py\n"
  var partition = ""
  var cpus = ""
  var memory = ""
  var minutes = ""
  var gpus = ""
  var nodes = ""
  var tasksPerNode = ""
  var account = ""
  var qos = ""
  var constraint = ""
  var gres = ""
  var output = ""
  var errorOutput = ""
  var pythonEnvironment = ""
  var include = ""
  var exclude = ""
  var useGitignore = true
  var abortOnSetupFailure = true
  var syncSource = false
  var provenance: String?
  var launchID: String?
  var submittedJobID: String?
  var submissionUnknown = false
  var extraFields: [String: JSONValue] = [:]

  var validation: String? {
    if host.isEmpty { return "Choose a host." }
    if script.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty { return "Add a job script." }
    if syncSource && source.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
      return "Choose a source directory on the ssync API server."
    }
    for (name, text, limit) in [
      ("CPUs", cpus, 256), ("Memory", memory, 1024), ("Nodes", nodes, 100),
      ("Time", minutes, Int.max), ("GPUs", gpus, Int.max),
      ("Tasks per node", tasksPerNode, Int.max),
    ] where !text.isEmpty {
      guard let value = Int(text), value > 0, value <= limit else {
        return "\(name) must be a positive integer"
          + (limit < Int.max ? " no greater than \(limit)." : ".")
      }
    }
    if submissionUnknown {
      return
        "This submission has an unknown result. Check recent jobs before creating another draft."
    }
    return nil
  }

  var requestBody: JSONValue {
    var fields = extraFields
    fields.merge([
      "host": .string(host), "script_content": .string(script),
      "exclude": .array(exclude.split(separator: "\n").map { .string(String($0)) }),
      "include": .array(include.split(separator: "\n").map { .string(String($0)) }),
      "no_gitignore": .bool(!useGitignore), "abort_on_setup_failure": .bool(abortOnSetupFailure),
    ]) { _, new in new }
    if syncSource { fields["source_dir"] = .string(source) } else { fields["source_dir"] = .null }
    for (key, value) in [
      ("job_name", name), ("partition", partition), ("account", account), ("qos", qos),
      ("constraint", constraint), ("gres", gres), ("output", output), ("error", errorOutput),
      ("python_env", pythonEnvironment),
    ] {
      if !value.isEmpty { fields[key] = .string(value) }
    }
    for (key, value) in [
      ("cpus", cpus), ("mem", memory), ("time", minutes), ("gpus_per_node", gpus), ("nodes", nodes),
      ("n_tasks_per_node", tasksPerNode),
    ] {
      if let number = Int(value) { fields[key] = .number(Double(number)) }
    }
    return .object(fields)
  }

  static var sample: LaunchDraft {
    var draft = LaunchDraft()
    draft.name = "protein-fold-v4"
    draft.host = "Atlas"
    draft.partition = "gpu-a100"
    draft.cpus = "32"
    draft.memory = "128"
    draft.gpus = "4"
    draft.minutes = "480"
    draft.script =
      "#!/bin/bash\n#SBATCH --job-name=protein-fold-v4\n\nsrun python train.py --epochs 80\n"
    return draft
  }
}
