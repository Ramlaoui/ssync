#!/bin/bash
#SBATCH --job-name=comprehensive-watcher-test
#SBATCH --time=10
#SBATCH --mem=2G
#SBATCH --cpus-per-task=2
#SBATCH --output=comprehensive_watcher_%j.out

# Comprehensive test of all watcher features

# 1. Simple pattern matching
#WATCHER pattern="START" action=log_event(message="Job started")
#WATCHER pattern="END" action=log_event(message="Job finished")

# 2. Pattern with variable capture
#WATCHER pattern="Memory: (\d+)MB" captures=[mem_mb] action=store_metric(name="memory_mb", value="${mem_mb}")

# 3. Pattern with condition
#WATCHER pattern="CPU: (\d+)%" captures=[cpu] condition="int(cpu) > 90" action=log_event(message="High CPU usage: ${cpu}%", level="WARNING")

# 4. Multi-capture pattern
#WATCHER pattern="Epoch \[(\d+)/(\d+)\]" captures=[current_epoch,total_epochs] action=store_metric(name="epoch", value="${current_epoch}")

# 5. Complex condition with multiple captures
#WATCHER_BEGIN
# name: convergence_monitor
# pattern: "Loss: ([\d.]+), Accuracy: ([\d.]+)%"
# captures: [loss, accuracy]
# interval: 5
# condition: float(loss) < 0.1 and float(accuracy) > 95
# action: log_event(message="Model converged! Loss=${loss}, Accuracy=${accuracy}%")
#WATCHER_END

# 6. Error detection with resubmit (simulation)
#WATCHER_BEGIN
# name: oom_handler
# pattern: "CUDA out of memory|OOM"
# interval: 10
# actions:
#   - log_event(message="OOM detected - would resubmit with more memory", level="ERROR")
#   - store_metric(name="oom_detected", value="1")
#WATCHER_END

# 7. Progress tracking with multiple actions
#WATCHER_BEGIN
# name: progress_tracker
# pattern: "CHECKPOINT_(\d+)"
# captures: [checkpoint_num]
# interval: 10
# actions:
#   - store_metric(name="last_checkpoint", value="${checkpoint_num}")
#   - log_event(message="Checkpoint ${checkpoint_num} saved")
#WATCHER_END

echo "START"
echo "Initializing comprehensive watcher test..."
sleep 1

# Simulate various outputs
echo "Memory: 1024MB"
echo "CPU: 45%"
sleep 1

echo "Epoch [1/10]"
echo "Loss: 0.523, Accuracy: 82.3%"
echo "Memory: 1536MB"
sleep 1

echo "Epoch [5/10]" 
echo "Loss: 0.087, Accuracy: 96.2%"  # This should trigger convergence
echo "CPU: 95%"  # This should trigger high CPU warning
echo "CHECKPOINT_1"
sleep 1

echo "Epoch [10/10]"
echo "Loss: 0.045, Accuracy: 98.1%"  # This should also trigger convergence
echo "Memory: 2048MB"
echo "CHECKPOINT_2"
sleep 1

# Simulate an error (won't actually trigger resubmit in test)
echo "Warning: GPU memory usage high"
echo "CUDA out of memory"  # This should trigger OOM handler
sleep 1

echo "END"
echo "Comprehensive test completed successfully"