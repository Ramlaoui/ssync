#!/bin/bash
#SBATCH --job-name=test-ml-watchers
#SBATCH --time=5
#SBATCH --mem=2G
#SBATCH --output=test_ml_watchers_%j.out

# ML Training simulation with watchers

# Monitor training loss
#WATCHER_BEGIN
# name: loss_monitor
# pattern: "Epoch \[(\d+)\].* Loss: ([\d.]+)"
# captures: [epoch, loss]
# interval: 2
# condition: float(loss) > 0.5
# actions:
#   - log_event(message="High loss detected: ${loss} at epoch ${epoch}")
#   - store_metric(name="max_loss", value="${loss}")
#WATCHER_END

# Monitor accuracy
#WATCHER_BEGIN
# name: accuracy_monitor
# pattern: "Accuracy: ([\d.]+)%"
# captures: [accuracy]
# interval: 2
# actions:
#   - store_metric(name="accuracy", value="${accuracy}")
#   - log_event(message="Accuracy: ${accuracy}%")
#WATCHER_END

# Detect convergence
#WATCHER pattern="Converged at epoch (\d+)" captures=[final_epoch] action=log_event(message="Training converged at epoch ${final_epoch}")

# OOM detection
#WATCHER pattern="out of memory|OOM|MemoryError" action=log_event(message="Memory error detected - would resubmit with more memory")

echo "Starting ML training simulation..."

# Simulate training loop
for epoch in {1..5}; do
    loss=$(echo "scale=4; 1.0 / ($epoch + 1)" | bc)
    accuracy=$(echo "scale=1; $epoch * 18" | bc)
    
    echo "Epoch [$epoch/5] - Loss: $loss - Accuracy: ${accuracy}%"
    
    # Simulate some training output
    echo "  Forward pass completed"
    echo "  Backward pass completed"
    echo "  Weights updated"
    
    sleep 1
done

echo "Converged at epoch 5"
echo "Training completed successfully"

# Simulate a memory warning (not actual OOM)
echo "Warning: GPU memory usage at 95%"