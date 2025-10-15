#!/bin/bash
#SBATCH --job-name=test_timer_watcher
#SBATCH --time=00:10:00
#SBATCH --mem=1G
#SBATCH --output=test_timer_%j.out

# Watcher that triggers on wandb run detection, then switches to timer mode
#WATCHER_BEGIN
# name: wandb_sync_monitor
# pattern: "wandb: Run (\S+) created"
# captures: [run_id]
# timer_mode_enabled: true
# timer_interval_seconds: 30
# actions:
#   - run_command(command="echo '[WATCHER] Timer triggered at $(date) - syncing wandb run ${run_id}' >> watcher_log.txt")
#   - run_command(command="echo '[WATCHER] Would execute: wandb sync ${run_id} --include-offline' >> watcher_log.txt")
#WATCHER_END

echo "Starting test job at $(date)"
echo "This simulates a training run with wandb"

# Simulate wandb initialization
echo "wandb: Run abc123xyz created"
echo "Training started..."

# Simulate training loop that runs for 3 minutes
for i in {1..18}; do
    echo "Epoch $i/18 - loss: $(echo "scale=4; 5.0 - $i * 0.2" | bc)"
    sleep 10
done

echo "Training completed at $(date)"
