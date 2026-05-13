RUN_STAMP="${RUN_STAMP:-$(date +%Y%m%d-%H%M%S)}"
RUN_DIR="${PWD}/run-outputs/${EXPERIMENT_NAME}/${RUN_STAMP}"

echo "RUN_OUTPUT_DIR=${RUN_DIR}"

srun python main.py \
  "$CONFIG" \
  max_steps="$MAX_STEPS" \
  run.dir="${RUN_DIR}" \
  ${resume_run_dir:+ +checkpoint.config_dir=${resume_run_dir}}

