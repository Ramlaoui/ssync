#!/bin/bash
#SBATCH --job-name=test-watcher-actions
#SBATCH --time=5
#SBATCH --mem=1G
#SBATCH --output=test_watcher_actions_%j.out

# Test various watcher actions

# Test store_metric action
#WATCHER pattern="Metric: (\w+)=([\d.]+)" captures=[name,value] action=store_metric(name="${name}", value="${value}")

# Test log_event with different levels
#WATCHER pattern="WARNING:" action=log_event(level="WARNING", message="Warning detected")
#WATCHER pattern="INFO:" action=log_event(level="INFO", message="Info message logged")

# Test command execution (safe commands only)
#WATCHER pattern="CHECKPOINT" action=run_command(command="echo 'Checkpoint triggered at $(date)'")

# Test email notification (will log if mail not configured)
#WATCHER pattern="CRITICAL:" action=notify_email(subject="Critical Event", message="Critical event in job ${JOB_ID}")

echo "Testing watcher actions..."

echo "INFO: Starting process"
sleep 20

echo "Metric: cpu_usage=45.2"
echo "Metric: memory_gb=1.8"
sleep 20

echo "WARNING: High resource usage"
echo "CHECKPOINT"
sleep 20

echo "Metric: gpu_util=89.5"
echo "CRITICAL: System overload detected"
sleep 20

echo "Actions test completed"
