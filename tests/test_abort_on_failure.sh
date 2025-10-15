#!/bin/bash
#SBATCH --job-name=test-abort
#SBATCH --time=10
#SBATCH --mem=1G

#LOGIN_SETUP_BEGIN
echo "Starting login setup..."
# This command will fail intentionally
exit 1
#LOGIN_SETUP_END

# This should not run if abort_on_setup_failure is true (default)
echo "This message should not appear if setup failed"
python -c "print('Job is running on compute node')"