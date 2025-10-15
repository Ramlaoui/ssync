#!/bin/bash
#SBATCH --job-name=watcher-test
#SBATCH --time=10
#SBATCH --mem=1G
#SBATCH --output=watcher_test_%j.out

# Simple inline watcher for errors
#WATCHER pattern="ERROR|FAIL" interval=30 action=notify_email

# Watcher for specific loss values in ML training
#WATCHER_BEGIN
# name: loss_monitor
# pattern: "loss: ([0-9.]+)"
# interval: 60
# captures: [loss_value]
# condition: float(loss_value) > 5.0
# actions:
#   - cancel_job(reason="Loss too high")
#   - notify_email(subject="Training diverged", message="Loss exceeded threshold: ${loss_value}")
#WATCHER_END

# Watcher for memory issues
#WATCHER_BEGIN
# name: oom_monitor  
# pattern: "out of memory|OOM|MemoryError"
# interval: 30
# action: resubmit(modifications={"mem": "8G"}, cancel_original=true)
#WATCHER_END

# Watcher for progress tracking
#WATCHER pattern="Step (\d+)/(\d+)" captures=[current,total] action=store_metric(name="progress", value="${current}")

echo "Starting job with watchers..."
echo "Step 1/10 completed"
sleep 2

echo "Step 5/10 completed" 
sleep 2

# Simulate an error condition
echo "ERROR: Something went wrong!"
sleep 2

echo "loss: 7.5"
sleep 2

echo "Step 10/10 completed"
echo "Job finished"