#!/bin/bash
#SBATCH --job-name=test-watchers-basic
#SBATCH --time=5
#SBATCH --mem=1G
#SBATCH --output=test_watchers_basic_%j.out

# Test 1: Simple error detection
#WATCHER pattern="ERROR" action=log_event(message="Error detected in output")

# Test 2: Pattern with capture
#WATCHER pattern="Progress: (\d+)%" captures=[progress] action=store_metric(name="progress", value="${progress}")

# Test 3: Conditional trigger
#WATCHER pattern="Temperature: (\d+)" captures=[temp] condition="int(temp) > 80" action=log_event(message="High temperature: ${temp}")

echo "Starting watcher tests..."
echo "Progress: 25%"
sleep 1

echo "Progress: 50%"
echo "Temperature: 75"
sleep 1

echo "Progress: 75%"
echo "Temperature: 85"  # This should trigger the temperature watcher
sleep 1

echo "ERROR: Something went wrong"  # This should trigger the error watcher
echo "Progress: 100%"

echo "Test completed"