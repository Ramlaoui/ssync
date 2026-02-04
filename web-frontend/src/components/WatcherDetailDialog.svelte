<script lang="ts">
  import { run } from "svelte/legacy";

  import { createEventDispatcher } from "svelte";
  import Dialog from "../lib/components/ui/Dialog.svelte";
  import { api } from "../services/api";
  import type { Watcher } from "../types/watchers";

  interface Props {
    watcher?: Watcher | null;
    jobId?: string;
    hostname?: string;
    open?: boolean;
  }

  let {
    watcher = $bindable(null),
    jobId = "",
    hostname = "",
    open = $bindable(true),
  }: Props = $props();

  const dispatch = createEventDispatcher();

  // UI state
  let activeTab: "view" | "edit" | "code" = $state("view");
  let isEditing = $state(false);
  let isSaving = $state(false);
  let error: string | null = $state(null);
  let copySuccess = $state(false);
  let codeFormat: "inline" | "file" = "file"; // Default to block format

  // Editable fields
  let editName = $state("");
  let editPattern = $state("");
  let editInterval = $state(30);
  let editCaptures: string[] = $state([]);
  let editCondition = $state("");
  let editActions: any[] = $state([]);
  let editTimerMode = $state(false);
  let editTimerInterval = $state(30);

  // Track if we've initialized the edit fields
  let previousWatcherId: number | null = $state(null);

  // Initialize edit fields only when watcher changes (not on every update)
  run(() => {
    if (watcher && watcher.id !== previousWatcherId) {
      previousWatcherId = watcher.id;
      editName = watcher.name;
      editPattern = watcher.pattern;
      editInterval = watcher.interval_seconds;
      editCaptures = watcher.captures || [];
      editCondition = watcher.condition || "";
      // Deep copy actions to preserve config and condition fields
      editActions = (watcher.actions || []).map((action) => ({
        type: action.type,
        condition: action.condition || "",
        config: { ...(action.config || action.params || {}) },
      }));
      editTimerMode = watcher.timer_mode_enabled || false;
      editTimerInterval = watcher.timer_interval_seconds || 30;
    }
  });

  function formatTime(timeStr: string | null): string {
    if (!timeStr) return "Never";
    try {
      const date = new Date(timeStr);
      return date.toLocaleString();
    } catch {
      return "Invalid date";
    }
  }

  function getActionDescription(action: any): string {
    // Support both config and params fields for backward compatibility
    const params = action.config || action.params || {};

    switch (action.type) {
      case "log_event":
        return params.message ? `"${params.message}"` : "Log event to output";
      case "store_metric":
        const metricName = params.metric_name || params.name;
        const metricValue = params.value;
        if (metricName && metricValue) {
          return `${metricName} = ${metricValue}`;
        } else if (metricName) {
          return metricName;
        }
        return "Store metric value";
      case "run_command":
        return params.command
          ? `${params.command.substring(0, 80)}${params.command.length > 80 ? "..." : ""}`
          : "Run command";
      case "notify_email":
        const emailParts = [];
        if (params.to) emailParts.push(`To: ${params.to}`);
        if (params.subject) emailParts.push(`Subject: ${params.subject}`);
        return emailParts.length > 0
          ? emailParts.join(", ")
          : "Send email notification";
      case "notify_slack":
        return params.webhook
          ? "Send to configured Slack"
          : "Send Slack notification";
      case "cancel_job":
        return params.reason ? `Reason: ${params.reason}` : "Cancel job";
      case "resubmit":
        const resubmitParts = [];
        if (params.delay) resubmitParts.push(`Delay: ${params.delay}s`);
        if (params.modifications) {
          const modCount = Object.keys(params.modifications).length;
          if (modCount > 0) resubmitParts.push(`${modCount} modifications`);
        }
        return resubmitParts.length > 0
          ? resubmitParts.join(", ")
          : "Resubmit job";
      case "pause_watcher":
        return "Pause this watcher";
      default:
        return action.type || "Unknown action";
    }
  }

  function getActionTypeLabel(type: string): string {
    switch (type) {
      case "log_event":
        return "Log Event";
      case "store_metric":
        return "Store Metric";
      case "run_command":
        return "Run Command";
      case "notify_email":
        return "Send Email";
      case "notify_slack":
        return "Slack Notification";
      case "cancel_job":
        return "Cancel Job";
      case "resubmit":
        return "Resubmit Job";
      case "pause_watcher":
        return "Pause Watcher";
      default:
        return type;
    }
  }

  function generateWatcherCode(): string {
    if (!watcher) return "";

    // Always generate block format
    let code = "#WATCHER_BEGIN\n";
    code += `# name: ${watcher.name}\n`;
    code += `# pattern: "${watcher.pattern}"\n`;
    code += `# interval: ${watcher.interval_seconds}\n`;

    if (watcher.captures && watcher.captures.length > 0) {
      code += `# captures: [${watcher.captures.map((c) => `"${c}"`).join(", ")}]\n`;
    }

    if (watcher.condition) {
      code += `# condition: ${watcher.condition}\n`;
    }

    if (watcher.timer_mode_enabled) {
      code += `# timer_mode: true\n`;
      code += `# timer_interval: ${watcher.timer_interval_seconds}\n`;
    }

    if (watcher.actions && watcher.actions.length > 0) {
      code += "# actions:\n";
      watcher.actions.forEach((action) => {
        let actionStr = `#   - ${action.type}`;
        // Support both config and params fields
        const params = action.config || action.params || {};
        if (action.condition) {
          actionStr += ` if="${action.condition}"`;
        }
        if (Object.keys(params).length > 0) {
          const paramStr = Object.entries(params)
            .map(([k, v]) => `${k}="${v}"`)
            .join(", ");
          actionStr += `(${paramStr})`;
        }
        code += actionStr + "\n";
      });
    }

    code += "#WATCHER_END";

    return code;
  }

  async function copyCode() {
    const code = generateWatcherCode();
    try {
      await navigator.clipboard.writeText(code);
      copySuccess = true;
      setTimeout(() => {
        copySuccess = false;
      }, 2000);
    } catch (err) {
      console.error("Failed to copy:", err);
      error = "Failed to copy to clipboard";
    }
  }

  async function saveChanges() {
    if (!watcher) return;

    // Validate required fields
    if (!editName.trim()) {
      error = "Watcher name is required";
      return;
    }

    if (!editPattern.trim()) {
      error = "Pattern is required";
      return;
    }

    if (editInterval < 1 || editInterval > 3600) {
      error = "Check interval must be between 1 and 3600 seconds";
      return;
    }

    if (editTimerMode && (editTimerInterval < 1 || editTimerInterval > 3600)) {
      error = "Timer interval must be between 1 and 3600 seconds";
      return;
    }

    // Validate actions
    for (let i = 0; i < editActions.length; i++) {
      const action = editActions[i];
      const fields = getConfigFieldsForType(action.type);

      for (const field of fields) {
        if (field.required && !action.config?.[field.name]) {
          error = `Action ${i + 1}: ${field.label} is required`;
          return;
        }

        if (field.type === "email" && action.config?.[field.name]) {
          const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
          if (!emailRegex.test(action.config[field.name])) {
            error = `Action ${i + 1}: Invalid email address`;
            return;
          }
        }

        if (field.type === "url" && action.config?.[field.name]) {
          try {
            new URL(action.config[field.name]);
            if (field.pattern) {
              const pattern = new RegExp(field.pattern);
              if (!pattern.test(action.config[field.name])) {
                error = `Action ${i + 1}: Invalid URL format`;
                return;
              }
            }
          } catch {
            error = `Action ${i + 1}: Invalid URL`;
            return;
          }
        }
      }
    }

    isSaving = true;
    error = null;

    try {
      // Format actions for the API - ensure config field is properly set
      const formattedActions = editActions.map((action) => ({
        type: action.type,
        condition: action.condition || undefined,
        config:
          action.config && Object.keys(action.config).length > 0
            ? action.config
            : undefined,
      }));

      const updatedConfig = {
        name: editName,
        pattern: editPattern,
        interval_seconds: editInterval,
        capture_groups: editCaptures.length > 0 ? editCaptures : undefined,
        condition: editCondition || undefined,
        actions: formattedActions,
        timer_mode_enabled: editTimerMode,
        timer_interval_seconds: editTimerMode ? editTimerInterval : undefined,
      };

      // API call to update watcher
      const response = await api.put(
        `/api/watchers/${watcher.id}`,
        updatedConfig,
      );

      if (response.data) {
        // Update the watcher object with the response data
        watcher = response.data;
        dispatch("updated", response.data);
        isEditing = false;
        activeTab = "view";
      }
    } catch (err: any) {
      error =
        err.response?.data?.detail || err.message || "Failed to update watcher";
    } finally {
      isSaving = false;
    }
  }

  async function deleteWatcher() {
    if (!watcher) return;

    if (
      !confirm(`Are you sure you want to delete the watcher "${watcher.name}"?`)
    ) {
      return;
    }

    try {
      await api.delete(`/api/watchers/${watcher.id}`);
      dispatch("deleted", watcher.id);
      handleClose();
    } catch (err: any) {
      error =
        err.response?.data?.detail || err.message || "Failed to delete watcher";
    }
  }

  function handleClose() {
    open = false;
    dispatch("close");
  }

  function addCapture() {
    editCaptures = [...editCaptures, ""];
  }

  function updateCapture(index: number, value: string) {
    editCaptures[index] = value;
    editCaptures = editCaptures;
  }

  function removeCapture(index: number) {
    editCaptures = editCaptures.filter((_, i) => i !== index);
  }

  function addAction() {
    editActions = [
      ...editActions,
      {
        type: "log_event",
        condition: "",
        config: getDefaultConfigForType("log_event"),
      },
    ];
  }

  function removeAction(index: number) {
    editActions = editActions.filter((_, i) => i !== index);
  }

  function updateAction(index: number, field: string, value: any) {
    if (field === "type") {
      const oldConfig = editActions[index].config || {};
      editActions[index].type = value;
      // Only reset config if the type actually changed, and preserve compatible fields
      if (editActions[index].type !== value) {
        const newDefaults = getDefaultConfigForType(value);
        // Preserve fields that exist in both old and new config
        const preservedConfig: any = {};
        for (const key in newDefaults) {
          if (key in oldConfig) {
            preservedConfig[key] = oldConfig[key];
          } else {
            preservedConfig[key] = newDefaults[key];
          }
        }
        editActions[index].config = preservedConfig;
      }
    } else if (field === "condition") {
      editActions[index].condition = value;
    } else if (field.startsWith("config.")) {
      const configField = field.substring(7);
      if (!editActions[index].config) {
        editActions[index].config = {};
      }

      // Validate based on the field type
      const fieldInfo = getConfigFieldsForType(editActions[index].type).find(
        (f) => f.name === configField,
      );

      let validatedValue = value;
      if (fieldInfo) {
        if (fieldInfo.type === "number") {
          // Convert to number and validate
          const numValue = Number(value);
          validatedValue = isNaN(numValue) ? 0 : numValue;

          // Apply min/max constraints if defined
          if (fieldInfo.min !== undefined && validatedValue < fieldInfo.min) {
            validatedValue = fieldInfo.min;
          }
          if (fieldInfo.max !== undefined && validatedValue > fieldInfo.max) {
            validatedValue = fieldInfo.max;
          }
        } else if (fieldInfo.type === "email") {
          // Basic email validation
          const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
          if (value && !emailRegex.test(value)) {
            // Keep the value but mark it as potentially invalid
            // We'll add visual feedback later
          }
        } else if (fieldInfo.type === "url") {
          // Basic URL validation
          try {
            if (value && value.trim()) {
              new URL(value);
            }
          } catch {
            // Keep the value but mark it as potentially invalid
          }
        }
      }

      editActions[index].config = {
        ...editActions[index].config,
        [configField]: validatedValue,
      };
    }
    editActions = editActions; // Trigger reactivity
  }

  function getDefaultConfigForType(type: string): any {
    switch (type) {
      case "log_event":
        return { message: "" };
      case "store_metric":
        return { metric_name: "", value: "" };
      case "run_command":
        return { command: "" };
      case "notify_email":
        return { to: "", subject: "", message: "" };
      case "notify_slack":
        return { webhook: "", message: "" };
      case "cancel_job":
        return { reason: "" };
      case "resubmit":
        return { delay: 0, cancel_previous: true, modifications: {} };
      case "pause_watcher":
        return {};
      default:
        return {};
    }
  }

  function getConfigFieldsForType(
    type: string,
  ): Array<{
    name: string;
    label: string;
    type: string;
    placeholder?: string;
    hint?: string;
    min?: number;
    max?: number;
    pattern?: string;
    required?: boolean;
  }> {
    switch (type) {
      case "log_event":
        return [
          {
            name: "message",
            label: "Message",
            type: "text",
            placeholder: "Log message to output",
            hint: "Can use captured variables like $1, $2",
          },
        ];
      case "store_metric":
        return [
          {
            name: "metric_name",
            label: "Metric Name",
            type: "text",
            placeholder: "e.g., gpu_usage, loss, accuracy",
            required: true,
            pattern: "^[a-zA-Z_][a-zA-Z0-9_]*$",
          },
          {
            name: "value",
            label: "Value Expression",
            type: "text",
            placeholder: "e.g., $1 or float($1)",
            hint: "Python expression using captured groups",
            required: true,
          },
        ];
      case "run_command":
        return [
          {
            name: "command",
            label: "Command",
            type: "text",
            placeholder: "e.g., wandb sync, python script.py, uv run train.py",
            hint: "Supports: echo, ls, cat, cd, python, uv, wandb, and more. Use && to chain commands.",
          },
        ];
      case "notify_email":
        return [
          {
            name: "to",
            label: "To",
            type: "email",
            placeholder: "email@example.com",
            required: true,
            pattern: "^[^\\s@]+@[^\\s@]+\\.[^\\s@]+$",
          },
          {
            name: "subject",
            label: "Subject",
            type: "text",
            placeholder: "Alert: Job $JOB_ID",
            required: true,
          },
          {
            name: "message",
            label: "Message",
            type: "text",
            placeholder: "Watcher triggered for job on $HOSTNAME",
          },
        ];
      case "notify_slack":
        return [
          {
            name: "webhook",
            label: "Webhook URL",
            type: "url",
            placeholder: "https://hooks.slack.com/services/...",
            required: true,
            pattern: "^https://hooks\\.slack\\.com/services/.+",
          },
          {
            name: "message",
            label: "Message",
            type: "text",
            placeholder: "Job alert: $1",
          },
        ];
      case "cancel_job":
        return [
          {
            name: "reason",
            label: "Reason",
            type: "text",
            placeholder: "e.g., Memory limit exceeded, Training diverged",
          },
        ];
      case "resubmit":
        return [
          {
            name: "delay",
            label: "Delay (seconds)",
            type: "number",
            placeholder: "0",
            hint: "Wait time before resubmitting",
            min: 0,
            max: 86400,
          },
          {
            name: "cancel_previous",
            label: "Cancel Previous",
            type: "checkbox",
            placeholder: "true",
            hint: "Cancel the original job before resubmitting",
          },
        ];
      case "pause_watcher":
        return [];
      default:
        return [];
    }
  }
</script>

{#if watcher}
  <Dialog
    bind:open
    on:close={handleClose}
    size="xl"
    showCloseButton={true}
    contentClass="watcher-dialog-content"
  >
    {#snippet header()}
      <div class="watcher-header">
        <div class="header-content">
          <h2>Watcher Details</h2>
          <p class="watcher-subtitle">{watcher?.name ?? ''}</p>
        </div>
      </div>
    {/snippet}

    <!-- Tab Navigation -->
    <div class="tabs">
      <button
        class="tab"
        class:active={activeTab === "view"}
        onclick={() => {
          activeTab = "view";
          isEditing = false;
        }}
      >
        <svg viewBox="0 0 24 24" fill="currentColor">
          <path
            d="M12,9A3,3 0 0,0 9,12A3,3 0 0,0 12,15A3,3 0 0,0 15,12A3,3 0 0,0 12,9M12,17A5,5 0 0,1 7,12A5,5 0 0,1 12,7A5,5 0 0,1 17,12A5,5 0 0,1 12,17M12,4.5C7,4.5 2.73,7.61 1,12C2.73,16.39 7,19.5 12,19.5C17,19.5 21.27,16.39 23,12C21.27,7.61 17,4.5 12,4.5Z"
          />
        </svg>
        View
      </button>
      <button
        class="tab"
        class:active={activeTab === "edit"}
        onclick={() => {
          activeTab = "edit";
          isEditing = true;
        }}
      >
        <svg viewBox="0 0 24 24" fill="currentColor">
          <path
            d="M20.71,7.04C21.1,6.65 21.1,6 20.71,5.63L18.37,3.29C18,2.9 17.35,2.9 16.96,3.29L15.12,5.12L18.87,8.87M3,17.25V21H6.75L17.81,9.93L14.06,6.18L3,17.25Z"
          />
        </svg>
        Edit
      </button>
      <button
        class="tab"
        class:active={activeTab === "code"}
        onclick={() => (activeTab = "code")}
      >
        <svg viewBox="0 0 24 24" fill="currentColor">
          <path
            d="M14.6,16.6L19.2,12L14.6,7.4L16,6L22,12L16,18L14.6,16.6M9.4,16.6L4.8,12L9.4,7.4L8,6L2,12L8,18L9.4,16.6Z"
          />
        </svg>
        Code
      </button>
    </div>

    {#if error}
      <div class="error-message">{error}</div>
    {/if}

    {#if activeTab === "view"}
      <!-- View Mode -->
      <div class="detail-section">
        <h3>Configuration</h3>
        <div class="detail-grid">
          <div class="detail-item">
            <span class="detail-label">Status:</span>
            <span class="status-badge status-{watcher.state}"
              >{watcher.state}</span
            >
          </div>
          <div class="detail-item">
            <span class="detail-label">Job ID:</span>
            <span>#{watcher.job_id}</span>
          </div>
          <div class="detail-item">
            <span class="detail-label">Host:</span>
            <span>{watcher.hostname}</span>
          </div>
          <div class="detail-item">
            <span class="detail-label">Check Interval:</span>
            <span>{watcher.interval_seconds}s</span>
          </div>
          {#if watcher.timer_mode_enabled}
            <div class="detail-item">
              <span class="detail-label">Timer Mode:</span>
              <span>Every {watcher.timer_interval_seconds}s</span>
            </div>
          {/if}
          <div class="detail-item">
            <span class="detail-label">Triggers:</span>
            <span>{watcher.trigger_count}</span>
          </div>
          <div class="detail-item">
            <span class="detail-label">Last Check:</span>
            <span>{formatTime(watcher?.last_check ?? null)}</span>
          </div>
        </div>
      </div>

      <div class="detail-section">
        <h3>Pattern</h3>
        <div class="pattern-display">
          <code>{watcher.pattern}</code>
        </div>

        {#if watcher.captures && watcher.captures.length > 0}
          <div class="captures-display">
            <span class="section-label">Capture Groups:</span>
            <div class="capture-tags">
              {#each watcher.captures as capture, i}
                <span class="capture-tag">${i + 1}: {capture}</span>
              {/each}
            </div>
          </div>
        {/if}

        {#if watcher.condition}
          <div class="condition-display">
            <span class="section-label">Condition:</span>
            <code>{watcher.condition}</code>
          </div>
        {/if}
      </div>

      <div class="detail-section">
        <h3>Actions ({watcher.actions?.length || 0})</h3>
        <div class="actions-list">
          {#each watcher.actions || [] as action, i}
            <div class="action-card">
              <span class="action-number">{i + 1}</span>
              <div class="action-content">
                <div class="action-type">{getActionTypeLabel(action.type)}</div>
                <div class="action-desc">{getActionDescription(action)}</div>
                {#if action.condition}
                  <div class="action-condition-view">
                    <span class="condition-label">If:</span>
                    <code>{action.condition}</code>
                  </div>
                {/if}
              </div>
            </div>
          {/each}
        </div>
      </div>
    {:else if activeTab === "edit"}
      <!-- Edit Mode -->
      <div class="edit-section">
        <div class="form-group">
          <label for="edit-name">Name</label>
          <input
            id="edit-name"
            type="text"
            bind:value={editName}
            placeholder="Watcher name"
          />
        </div>

        <div class="form-group">
          <label for="edit-pattern">Pattern</label>
          <input
            id="edit-pattern"
            type="text"
            bind:value={editPattern}
            placeholder="Regular expression pattern"
          />
        </div>

        <div class="form-group">
          <label for="edit-interval">Check Interval (seconds)</label>
          <input
            id="edit-interval"
            type="number"
            bind:value={editInterval}
            min="1"
            max="3600"
          />
          {#if editInterval < 1 || editInterval > 3600}
            <span class="field-error"
              >Interval must be between 1 and 3600 seconds</span
            >
          {/if}
        </div>

        <div class="form-group">
          <label>
            <input type="checkbox" bind:checked={editTimerMode} />
            Timer Mode
          </label>
          {#if editTimerMode}
            <input
              type="number"
              bind:value={editTimerInterval}
              min="1"
              max="3600"
              placeholder="Timer interval (seconds)"
            />
            {#if editTimerInterval < 1 || editTimerInterval > 3600}
              <span class="field-error"
                >Timer interval must be between 1 and 3600 seconds</span
              >
            {/if}
          {/if}
        </div>

        <div class="form-group">
          <span class="section-label">Capture Groups</span>
          {#each editCaptures as capture, i}
            <div class="capture-edit">
              <input
                type="text"
                value={capture}
                oninput={(e) => updateCapture(i, (e.target as HTMLInputElement).value)}
                placeholder="Capture name"
              />
              <button onclick={() => removeCapture(i)}>Remove</button>
            </div>
          {/each}
          <button class="add-btn" onclick={addCapture}>Add Capture</button>
        </div>

        <div class="form-group">
          <label for="edit-condition">Condition (Optional)</label>
          <input
            id="edit-condition"
            type="text"
            bind:value={editCondition}
            placeholder="Python expression"
          />
        </div>

        <div class="form-group">
          <span class="section-label">Actions</span>
          <div class="actions-edit-list">
            {#each editActions as action, i}
              <div class="action-edit-card">
                <div class="action-header">
                  <span class="action-number">{i + 1}</span>
                  <select
                    value={action.type}
                    onchange={(e) => updateAction(i, "type", (e.target as HTMLSelectElement).value)}
                  >
                    <option value="log_event">Log Event</option>
                    <option value="store_metric">Store Metric</option>
                    <option value="run_command">Run Command</option>
                    <option value="notify_email">Send Email</option>
                    <option value="notify_slack">Send Slack Notification</option
                    >
                    <option value="cancel_job">Cancel Job</option>
                    <option value="resubmit">Resubmit Job</option>
                    <option value="pause_watcher">Pause Watcher</option>
                  </select>
                  <button
                    class="remove-action-btn"
                    onclick={() => removeAction(i)}
                    aria-label="Remove action"
                  >
                    <svg viewBox="0 0 24 24" fill="currentColor">
                      <path
                        d="M19,6.41L17.59,5L12,10.59L6.41,5L5,6.41L10.59,12L5,17.59L6.41,19L12,13.41L17.59,19L19,17.59L13.41,12L19,6.41Z"
                      />
                    </svg>
                  </button>
                </div>

                <div class="action-condition">
                  <input
                    type="text"
                    value={action.condition || ""}
                    oninput={(e) =>
                      updateAction(i, "condition", (e.target as HTMLInputElement).value)}
                    placeholder="Condition (optional, e.g., float($1) > 80)"
                  />
                </div>

                {#if action.type !== "pause_watcher"}
                  <div class="action-config">
                    {#each getConfigFieldsForType(action.type) as field}
                      <div class="config-field">
                        <span class="config-label">{field.label}:</span>
                        {#if field.type === "checkbox"}
                          <input
                            type="checkbox"
                            checked={action.config?.[field.name] ?? true}
                            onchange={(e) =>
                              updateAction(
                                i,
                                `config.${field.name}`,
                                (e.target as HTMLInputElement).checked,
                              )}
                          />
                        {:else if field.type === "number"}
                          <input
                            type="number"
                            value={action.config?.[field.name] || ""}
                            oninput={(e) =>
                              updateAction(
                                i,
                                `config.${field.name}`,
                                (e.target as HTMLInputElement).value,
                              )}
                            placeholder={field.placeholder}
                            min={field.min}
                            max={field.max}
                            class:invalid={field.required &&
                              !action.config?.[field.name]}
                          />
                        {:else if field.type === "email"}
                          <input
                            type="email"
                            value={action.config?.[field.name] || ""}
                            oninput={(e) =>
                              updateAction(
                                i,
                                `config.${field.name}`,
                                (e.target as HTMLInputElement).value,
                              )}
                            placeholder={field.placeholder}
                            pattern={field.pattern}
                            required={field.required}
                            class:invalid={field.required &&
                              !action.config?.[field.name]}
                          />
                        {:else if field.type === "url"}
                          <input
                            type="url"
                            value={action.config?.[field.name] || ""}
                            oninput={(e) =>
                              updateAction(
                                i,
                                `config.${field.name}`,
                                (e.target as HTMLInputElement).value,
                              )}
                            placeholder={field.placeholder}
                            pattern={field.pattern}
                            required={field.required}
                            class:invalid={field.required &&
                              !action.config?.[field.name]}
                          />
                        {:else}
                          <input
                            type="text"
                            value={action.config?.[field.name] || ""}
                            oninput={(e) =>
                              updateAction(
                                i,
                                `config.${field.name}`,
                                (e.target as HTMLInputElement).value,
                              )}
                            placeholder={field.placeholder}
                            pattern={field.pattern}
                            class:invalid={field.required &&
                              !action.config?.[field.name]}
                          />
                        {/if}
                        {#if field.hint}
                          <span class="field-hint">{field.hint}</span>
                        {/if}
                      </div>
                    {/each}
                  </div>
                {/if}
              </div>
            {/each}
          </div>
          <button class="add-btn" onclick={addAction}>Add Action</button>
        </div>

        <div class="edit-actions">
          <button class="btn-primary" onclick={saveChanges} disabled={isSaving}>
            {isSaving ? "Saving..." : "Save Changes"}
          </button>
          <button
            class="btn-secondary"
            onclick={() => {
              activeTab = "view";
              isEditing = false;
            }}
          >
            Cancel
          </button>
        </div>
      </div>
    {:else if activeTab === "code"}
      <!-- Code Generation -->
      <div class="code-section">
        <div class="code-header">
          <h3>Submit Script Integration</h3>
        </div>

        <div class="code-instructions">
          <p>Add this block to your Slurm script (after #SBATCH directives):</p>
        </div>

        <div class="code-container">
          <pre><code>{generateWatcherCode()}</code></pre>
          <button
            class="copy-code-btn"
            class:success={copySuccess}
            onclick={copyCode}
          >
            {#if copySuccess}
              <svg viewBox="0 0 24 24" fill="currentColor">
                <path
                  d="M21,7L9,19L3.5,13.5L4.91,12.09L9,16.17L19.59,5.59L21,7Z"
                />
              </svg>
              Copied!
            {:else}
              <svg viewBox="0 0 24 24" fill="currentColor">
                <path
                  d="M19,21H8V7H19M19,5H8A2,2 0 0,0 6,7V21A2,2 0 0,0 8,23H19A2,2 0 0,0 21,21V7A2,2 0 0,0 19,5M16,1H4A2,2 0 0,0 2,3V17H4V3H16V1Z"
                />
              </svg>
              Copy Code
            {/if}
          </button>
        </div>

        <div class="code-notes">
          <h4>Notes:</h4>
          <ul>
            <li>
              Place this #WATCHER_BEGIN...#WATCHER_END block after your #SBATCH
              directives
            </li>
            <li>
              The block format supports multiple actions and complex conditions
            </li>
            <li>
              Multiple watcher blocks can be added to monitor different
              conditions
            </li>
            <li>Watchers automatically stop when the job completes</li>
            <li>
              All parameters inside the block must start with # and be indented
            </li>
          </ul>
        </div>
      </div>
    {/if}

    {#snippet footer()}
      <div class="watcher-footer">
        {#if activeTab === "view"}
          <button class="btn-danger" onclick={deleteWatcher}>
            Delete Watcher
          </button>
        {/if}
        <button class="btn-secondary" onclick={handleClose}> Close </button>
      </div>
    {/snippet}
  </Dialog>
{/if}

<style>
  /* Custom styling for watcher dialog content */
  :global(.watcher-dialog-content) {
    padding: 0 !important;
  }

  .watcher-header {
    width: 100%;
  }

  .header-content h2 {
    margin: 0;
    font-size: 1.5rem;
    color: var(--foreground);
  }

  .watcher-subtitle {
    margin: 0.25rem 0 0 0;
    color: var(--muted-foreground);
    font-size: 0.875rem;
  }

  /* Tabs */
  .tabs {
    display: flex;
    gap: 0.5rem;
    padding: 0 1.5rem;
    border-bottom: 1px solid var(--border);
    margin-top: -0.5rem;
  }

  .tab {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    padding: 0.75rem 1rem;
    background: none;
    border: none;
    border-bottom: 2px solid transparent;
    cursor: pointer;
    color: var(--muted-foreground);
    font-size: 0.875rem;
    font-weight: 500;
    transition: all 0.2s;
  }

  .tab svg {
    width: 18px;
    height: 18px;
  }

  .tab:hover {
    color: var(--foreground);
  }

  .tab.active {
    color: var(--accent);
    border-bottom-color: var(--accent);
  }

  .error-message {
    background: var(--error-bg);
    border: 1px solid var(--error-bg);
    color: var(--destructive);
    padding: 0.75rem;
    border-radius: 6px;
    margin: 1.5rem 1.5rem 1rem;
  }

  /* View Mode */
  .detail-section {
    margin-bottom: 2rem;
    padding: 0 1.5rem;
  }

  .detail-section:first-of-type {
    padding-top: 1.5rem;
  }

  .detail-section h3 {
    margin: 0 0 1rem 0;
    font-size: 1.1rem;
    color: var(--foreground);
  }

  .detail-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
    gap: 1rem;
  }

  .detail-item {
    display: flex;
    flex-direction: column;
    gap: 0.25rem;
  }

  .detail-item .detail-label {
    font-size: 0.75rem;
    font-weight: 500;
    color: var(--muted-foreground);
    text-transform: uppercase;
  }

  .detail-item span {
    font-size: 0.875rem;
    color: var(--foreground);
  }

  .status-badge {
    display: inline-block;
    padding: 0.25rem 0.75rem;
    border-radius: 9999px;
    font-size: 0.75rem;
    font-weight: 600;
    text-transform: uppercase;
  }

  .status-active {
    background: var(--success-bg);
    color: #065f46;
  }

  .status-paused {
    background: #fed7aa;
    color: #92400e;
  }

  .status-completed {
    background: var(--info-bg);
    color: #1e40af;
  }

  .status-failed {
    background: var(--error-bg);
    color: #991b1b;
  }

  .pattern-display {
    background: var(--secondary);
    padding: 1rem;
    border-radius: 6px;
    margin-bottom: 1rem;
  }

  .pattern-display code {
    font-family: "Monaco", "Courier New", monospace;
    font-size: 0.875rem;
    color: var(--foreground);
    word-break: break-all;
  }

  .captures-display,
  .condition-display {
    margin-top: 1rem;
  }

  .captures-display .section-label,
  .condition-display .section-label {
    display: block;
    font-size: 0.875rem;
    font-weight: 500;
    color: var(--foreground);
    margin-bottom: 0.5rem;
  }

  .capture-tags {
    display: flex;
    flex-wrap: wrap;
    gap: 0.5rem;
  }

  .capture-tag {
    display: inline-block;
    padding: 0.25rem 0.75rem;
    background: var(--info-bg);
    border: 1px solid #bfdbfe;
    border-radius: 6px;
    font-family: monospace;
    font-size: 0.75rem;
    color: #1e40af;
  }

  .condition-display code {
    display: block;
    padding: 0.5rem;
    background: var(--secondary);
    border: 1px solid var(--border);
    border-radius: 4px;
    font-family: monospace;
    font-size: 0.875rem;
  }

  .actions-list {
    display: flex;
    flex-direction: column;
    gap: 0.75rem;
  }

  .action-card {
    display: flex;
    align-items: flex-start;
    gap: 1rem;
    padding: 0.75rem;
    background: var(--secondary);
    border: 1px solid var(--border);
    border-radius: 6px;
  }

  .action-number {
    display: flex;
    align-items: center;
    justify-content: center;
    width: 24px;
    height: 24px;
    background: var(--accent);
    color: white;
    border-radius: 50%;
    font-size: 0.75rem;
    font-weight: 600;
    flex-shrink: 0;
  }

  .action-content {
    flex: 1;
  }

  .action-type {
    font-size: 0.875rem;
    font-weight: 600;
    color: var(--foreground);
    margin-bottom: 0.25rem;
  }

  .action-desc {
    font-size: 0.75rem;
    color: var(--muted-foreground);
  }

  .action-condition-view {
    margin-top: 0.5rem;
    font-size: 0.75rem;
  }

  .action-condition-view .condition-label {
    font-weight: 500;
    color: var(--foreground);
    margin-right: 0.25rem;
  }

  .action-condition-view code {
    background: var(--secondary);
    padding: 0.125rem 0.375rem;
    border-radius: 3px;
    font-family: monospace;
    font-size: 0.75rem;
    color: var(--foreground);
  }

  /* Edit Mode */
  .edit-section {
    display: flex;
    flex-direction: column;
    gap: 1.5rem;
    padding: 1.5rem;
  }

  .form-group {
    display: flex;
    flex-direction: column;
    gap: 0.5rem;
  }

  .form-group label {
    font-size: 0.875rem;
    font-weight: 500;
    color: var(--foreground);
  }

  .form-group .section-label {
    font-size: 0.875rem;
    font-weight: 500;
    color: var(--foreground);
    display: block;
    margin-bottom: 0.5rem;
  }

  .form-group input[type="text"],
  .form-group input[type="number"] {
    padding: 0.5rem 0.75rem;
    border: 1px solid var(--border);
    border-radius: 6px;
    font-size: 0.875rem;
  }

  .form-group input[type="checkbox"] {
    margin-right: 0.5rem;
  }

  .capture-edit {
    display: flex;
    gap: 0.5rem;
    margin-bottom: 0.5rem;
  }

  .capture-edit input {
    flex: 1;
  }

  .capture-edit button {
    padding: 0.5rem 1rem;
    background: var(--destructive);
    color: white;
    border: none;
    border-radius: 4px;
    font-size: 0.75rem;
    cursor: pointer;
  }

  .add-btn {
    padding: 0.5rem 1rem;
    background: var(--accent);
    color: white;
    border: none;
    border-radius: 6px;
    font-size: 0.875rem;
    cursor: pointer;
    align-self: flex-start;
  }

  .add-btn:hover {
    background: var(--accent);
  }

  /* Action Edit List */
  .actions-edit-list {
    display: flex;
    flex-direction: column;
    gap: 1rem;
    margin-bottom: 0.5rem;
  }

  .action-edit-card {
    background: var(--secondary);
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: 1rem;
  }

  .action-header {
    display: flex;
    align-items: center;
    gap: 0.75rem;
    margin-bottom: 0.75rem;
  }

  .action-header .action-number {
    display: flex;
    align-items: center;
    justify-content: center;
    width: 24px;
    height: 24px;
    background: var(--accent);
    color: white;
    border-radius: 50%;
    font-size: 0.75rem;
    font-weight: 600;
    flex-shrink: 0;
  }

  .action-header select {
    flex: 1;
    padding: 0.5rem;
    border: 1px solid var(--border);
    border-radius: 6px;
    font-size: 0.875rem;
    background: white;
  }

  .remove-action-btn {
    background: var(--destructive);
    color: white;
    border: none;
    border-radius: 4px;
    padding: 0.25rem;
    cursor: pointer;
    display: flex;
    align-items: center;
    justify-content: center;
  }

  .remove-action-btn:hover {
    background: var(--destructive);
  }

  .remove-action-btn svg {
    width: 16px;
    height: 16px;
  }

  .action-condition {
    margin-bottom: 0.75rem;
  }

  .action-condition input {
    width: 100%;
    padding: 0.5rem 0.75rem;
    border: 1px solid var(--border);
    border-radius: 6px;
    font-size: 0.875rem;
    font-family: monospace;
  }

  .action-config {
    display: flex;
    flex-direction: column;
    gap: 0.5rem;
  }

  .config-field {
    display: flex;
    flex-direction: column;
    gap: 0.25rem;
  }

  .config-field .config-label {
    font-size: 0.75rem;
    font-weight: 500;
    color: var(--muted-foreground);
  }

  .config-field input {
    padding: 0.5rem 0.75rem;
    border: 1px solid var(--border);
    border-radius: 6px;
    font-size: 0.875rem;
  }

  .config-field input[type="checkbox"] {
    width: auto;
    margin-top: 0.25rem;
  }

  .field-hint {
    font-size: 0.75rem;
    color: var(--muted-foreground);
    font-style: italic;
    display: block;
    margin-top: 0.25rem;
  }

  .field-error {
    font-size: 0.75rem;
    color: var(--destructive);
    display: block;
    margin-top: 0.25rem;
  }

  .config-field input.invalid {
    border-color: var(--destructive);
  }

  .config-field input:invalid {
    border-color: var(--destructive);
  }

  .edit-actions {
    display: flex;
    gap: 1rem;
    margin-top: 1rem;
  }

  /* Code Section */
  .code-section {
    display: flex;
    flex-direction: column;
    gap: 1.5rem;
    padding: 1.5rem;
  }

  .code-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
  }

  .code-header h3 {
    margin: 0;
    font-size: 1.1rem;
    color: var(--foreground);
  }

  .format-selector {
    display: flex;
    gap: 1rem;
  }

  .code-instructions {
    padding: 0.75rem;
    background: var(--info-bg);
    border: 1px solid #bfdbfe;
    border-radius: 6px;
  }

  .code-instructions p {
    margin: 0;
    font-size: 0.875rem;
    color: #1e40af;
  }

  .code-container {
    position: relative;
    background: var(--foreground);
    border-radius: 8px;
    overflow: hidden;
  }

  .code-container pre {
    margin: 0;
    padding: 1rem;
    overflow-x: auto;
  }

  .code-container code {
    font-family: "Monaco", "Courier New", monospace;
    font-size: 0.875rem;
    color: var(--border);
    line-height: 1.5;
  }

  .copy-code-btn {
    position: absolute;
    top: 0.75rem;
    right: 0.75rem;
    display: flex;
    align-items: center;
    gap: 0.5rem;
    padding: 0.5rem 1rem;
    background: var(--accent);
    color: white;
    border: none;
    border-radius: 6px;
    font-size: 0.875rem;
    cursor: pointer;
    transition: all 0.2s;
  }

  .copy-code-btn:hover {
    background: var(--accent);
  }

  .copy-code-btn.success {
    background: var(--success);
  }

  .copy-code-btn svg {
    width: 16px;
    height: 16px;
  }

  .code-notes {
    background: var(--secondary);
    padding: 1rem;
    border-radius: 6px;
  }

  .code-notes h4 {
    margin: 0 0 0.5rem 0;
    font-size: 0.875rem;
    font-weight: 600;
    color: var(--foreground);
  }

  .code-notes ul {
    margin: 0;
    padding-left: 1.5rem;
  }

  .code-notes li {
    font-size: 0.75rem;
    color: var(--muted-foreground);
    margin-bottom: 0.25rem;
  }

  /* Footer */
  .watcher-footer {
    display: flex;
    justify-content: space-between;
    align-items: center;
    width: 100%;
  }

  .btn-primary,
  .btn-secondary,
  .btn-danger {
    padding: 0.5rem 1rem;
    border: none;
    border-radius: 6px;
    font-size: 0.875rem;
    font-weight: 500;
    cursor: pointer;
    transition: all 0.2s;
  }

  .btn-primary {
    background: var(--accent);
    color: white;
  }

  .btn-primary:hover:not(:disabled) {
    background: var(--accent);
  }

  .btn-secondary {
    background: white;
    color: var(--foreground);
    border: 1px solid var(--border);
    margin-left: auto;
  }

  .btn-secondary:hover {
    background: var(--secondary);
  }

  .btn-danger {
    background: var(--destructive);
    color: white;
  }

  .btn-danger:hover {
    background: var(--destructive);
  }

  .btn-primary:disabled {
    opacity: 0.5;
    cursor: not-allowed;
  }

  @media (max-width: 640px) {
    .detail-grid {
      grid-template-columns: 1fr;
    }

    .tabs {
      padding: 0 1rem;
    }

    .detail-section {
      padding: 0 1rem;
    }

    .edit-section,
    .code-section {
      padding: 1rem;
    }
  }
</style>
