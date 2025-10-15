#!/bin/bash
#SBATCH --partition=gpu
#SBATCH --time=60
#SBATCH --cpus-per-task=4
#SBATCH --mem=16G
#SBATCH --job-name=script_job

# This script has SBATCH directives that should be overridden by CLI args
echo "Job started with:"
echo "  Partition: $SLURM_JOB_PARTITION"
echo "  CPUs: $SLURM_CPUS_PER_TASK"
echo "  Job Name: $SLURM_JOB_NAME"
echo "  Time Limit: $SLURM_JOB_TIME_LIMIT"

# The job should use CLI values, not these script values