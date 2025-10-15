#!/bin/bash
#SBATCH --job-name=test-watcher
#SBATCH --time=00:05:00

# Test inline watcher
#WATCHER pattern="Starting training" action=log_event

# Test block watcher with timer mode
#WATCHER_BEGIN
# pattern: HYDRA_OUTPUT_DIR=(.*)
# captures: [output_dir]
# timer_mode_enabled: true
# timer_interval_seconds: 30
# actions:
#   - type: run_command
#     params:
#       command: "echo Syncing $output_dir"
#WATCHER_END

echo "Starting training"
echo "HYDRA_OUTPUT_DIR=/path/to/output"
sleep 60
echo "Training complete"