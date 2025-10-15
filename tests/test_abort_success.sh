#!/bin/bash
#SBATCH --job-name=test-success
#SBATCH --time=10
#SBATCH --mem=1G

#LOGIN_SETUP_BEGIN
echo "Starting login setup..."
echo "Setup completed successfully"
# This command succeeds
exit 0
#LOGIN_SETUP_END

# This should run since setup succeeded
echo "Job is running on compute node after successful setup"
python -c "print('Hello from compute node!')"