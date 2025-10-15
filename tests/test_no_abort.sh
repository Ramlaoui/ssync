#!/bin/bash  
#SBATCH --job-name=test-no-abort
#SBATCH --time=10
#SBATCH --mem=1G

#LOGIN_SETUP_BEGIN
echo "Starting login setup..."
echo "This will fail but job should continue with --no-abort-on-setup-failure"
# This command will fail
exit 1
#LOGIN_SETUP_END

# This SHOULD run when using --no-abort-on-setup-failure flag
echo "Job is running despite setup failure!"
echo "This proves the --no-abort-on-setup-failure flag works"
python -c "print('Running on compute node even though setup failed')"