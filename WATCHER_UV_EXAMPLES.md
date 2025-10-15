# Using UV Commands with Watchers

Watchers now support `uv run` and `uvx` commands, enabling Python script execution with proper dependency management.

## Supported UV Commands

- `uv run` - Run Python scripts with dependencies from pyproject.toml/requirements.txt
- `uvx` - Run Python packages/tools directly without installation
- `python -m uv` - Alternative uv invocation

## Key Benefits

1. **Automatic dependency resolution** - uv handles all dependencies
2. **No virtual environment needed** - uv manages isolation
3. **Works in job directory** - Commands run in the job's working directory
4. **Tool access** - uvx provides access to Python tools without installation

## Example Watcher Configurations

### 1. Run Python Script on Error Detection
```python
watchers = [
    {
        "name": "error_analyzer",
        "pattern": r"ERROR|FAILED|Exception",
        "output_type": "stderr",
        "actions": [
            {
                "type": "RUN_COMMAND",
                "params": {
                    "command": "uv run python analyze_error.py --job ${JOB_ID}"
                }
            }
        ]
    }
]
```

### 2. Extract and Store Metrics
```python
watchers = [
    {
        "name": "metric_extractor",
        "pattern": r"Loss: ([\d.]+).*Accuracy: ([\d.]+)",
        "capture_groups": ["loss", "accuracy"],
        "actions": [
            {
                "type": "RUN_COMMAND",
                "params": {
                    "command": "uv run python -c 'import json; print(json.dumps({\"loss\": ${loss}, \"acc\": ${accuracy}}))' > metrics.json"
                }
            }
        ]
    }
]
```

### 3. Use Python Tools via uvx
```python
watchers = [
    {
        "name": "memory_monitor",
        "pattern": r"OutOfMemoryError|memory allocation failed",
        "actions": [
            {
                "type": "RUN_COMMAND",
                "params": {
                    # Use memray tool to analyze memory
                    "command": "uvx memray tree memory_dump.bin"
                }
            }
        ]
    }
]
```

### 4. Data Processing on Completion
```python
watchers = [
    {
        "name": "post_processor",
        "pattern": r"Job completed successfully",
        "actions": [
            {
                "type": "RUN_COMMAND",
                "params": {
                    # Run data processing script with dependencies
                    "command": "uv run python process_results.py --input output.dat --format parquet"
                }
            }
        ]
    }
]
```

### 5. Send Notifications with Rich Content
```python
watchers = [
    {
        "name": "completion_notifier",
        "pattern": r"Training completed.*final loss: ([\d.]+)",
        "capture_groups": ["final_loss"],
        "actions": [
            {
                "type": "RUN_COMMAND",
                "params": {
                    # Use uvx to run notification script
                    "command": "uvx --from notifiers notify --provider slack --message 'Training done: loss=${final_loss}'"
                }
            }
        ]
    }
]
```

### 6. Conditional Script Execution
```python
watchers = [
    {
        "name": "adaptive_handler",
        "pattern": r"Iteration (\d+).*Loss: ([\d.]+)",
        "capture_groups": ["iteration", "loss"],
        "actions": [
            {
                "type": "RUN_COMMAND",
                "params": {
                    # Run Python script that decides next action
                    "command": "uv run python -c 'import sys; loss=float(${loss}); sys.exit(0 if loss < 0.1 else 1)' && echo 'Converged!'"
                }
            }
        ]
    }
]
```

## How It Works

1. **Working Directory**: Commands automatically run in the job's working directory
2. **Dependency Resolution**: uv reads pyproject.toml or requirements.txt in that directory
3. **Isolation**: Each command runs in an isolated environment
4. **Variable Substitution**: Captured variables (${var}) are replaced before execution

## Example pyproject.toml for Job Directory

```toml
[project]
dependencies = [
    "numpy",
    "pandas",
    "matplotlib",
    "requests",
]

[tool.uv]
dev-dependencies = [
    "ipython",
    "rich",
]
```

## Best Practices

1. **Keep scripts simple** - Complex logic should be in separate Python files
2. **Use uvx for tools** - Don't install tools globally, use uvx
3. **Handle errors** - Python scripts should exit with proper codes
4. **Limit output** - Watcher captures only first 500 chars of output
5. **Test locally** - Test uv commands in job directory before deploying

## Security Notes

- Commands run on login node, not compute node
- Limited to 500 characters of output
- Commands have access to job's working directory
- Use environment variables for sensitive data

## Limitations

- Commands run via SSH on login node
- No access to compute node environment
- Module system not automatically loaded
- Time limit for command execution