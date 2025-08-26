"""Integrated job launch manager that handles sync and submission."""

from pathlib import Path
from typing import List, Optional

from .manager import Job, SlurmManager
from .script_processor import ScriptProcessor
from .sync import SyncManager
from .utils.logging import setup_logger
from .utils.slurm_params import SlurmParams
from .utils.ssh import send_file

logger = setup_logger(__name__, "DEBUG")


class LaunchManager:
    """Manages the complete job launch workflow: sync + submit."""

    def __init__(self, slurm_manager: SlurmManager):
        self.slurm_manager = slurm_manager

    def _parse_structured_script(self, script_content: str) -> tuple[str, str]:
        """
        Parse structured script format to separate login node setup from compute script.

        Format:
        #!/bin/bash
        #SBATCH directives...

        #LOGIN_SETUP_BEGIN
        login node commands here
        #LOGIN_SETUP_END

        compute node commands here

        Args:
            script_content: Raw script content

        Returns:
            Tuple of (login_setup_commands, clean_compute_script)
        """
        lines = script_content.split("\n")
        login_setup_lines = []
        compute_script_lines = []

        in_login_setup = False
        login_setup_found = False

        for line in lines:
            stripped = line.strip()

            if stripped == "#LOGIN_SETUP_BEGIN":
                in_login_setup = True
                login_setup_found = True
                continue
            elif stripped == "#LOGIN_SETUP_END":
                in_login_setup = False
                continue
            elif in_login_setup:
                login_setup_lines.append(line)
            else:
                compute_script_lines.append(line)

        login_setup_commands = "\n".join(login_setup_lines).strip()
        clean_compute_script = "\n".join(compute_script_lines)

        if not login_setup_found:
            return "", script_content

        logger.debug(
            f"Parsed structured script: {len(login_setup_lines)} login setup lines, {len(compute_script_lines)} compute script lines"
        )

        return login_setup_commands, clean_compute_script

    async def launch_job(
        self,
        script_path: str | Path,
        source_dir: Optional[str | Path],
        host: str,
        slurm_params: SlurmParams,
        python_env: Optional[str] = None,
        exclude: List[str] = None,
        include: List[str] = None,
        no_gitignore: bool = False,
        sync_enabled: bool = True,
    ) -> Optional[Job]:
        """Launch a job with optional sync and submission.

        Args:
            script_path: Path to the script to submit (.sh or .slurm)
            source_dir: Source directory to sync to remote (optional, required only if sync_enabled=True)
            host: Target host (required)
            slurm_params: SLURM parameters for job submission
            python_env: Python environment setup command
            exclude: Patterns to exclude from sync
            include: Patterns to include in sync
            no_gitignore: Disable .gitignore usage
            sync_enabled: Whether to sync source directory (default: True)

        Returns:
            Job object if successful, None otherwise
        """
        script_path = Path(script_path)

        if not script_path.exists():
            logger.error(f"Script not found: {script_path}")
            return None

        if sync_enabled:
            if source_dir is None:
                logger.error("Source directory is required when sync is enabled")
                return None
            source_dir = Path(source_dir)
            if not source_dir.exists():
                logger.error(f"Source directory not found: {source_dir}")
                return None
        else:
            if source_dir is not None:
                source_dir = Path(source_dir)

        try:
            slurm_host = self.slurm_manager.get_host_by_name(host)
        except ValueError as e:
            logger.error(str(e))
            return None

        logger.info(f"Launching job on {slurm_host.host.hostname}")

        try:
            if sync_enabled and source_dir:
                logger.info("Syncing source directory to remote host...")
                sync_manager = SyncManager(
                    self.slurm_manager, source_dir, use_gitignore=not no_gitignore
                )

                sync_success = sync_manager.sync_to_host(
                    slurm_host, exclude=exclude, include_patterns=include
                )

                if not sync_success:
                    logger.error("Failed to sync source directory")
                    return None

                logger.info("Sync completed successfully")
                remote_work_dir = Path(slurm_host.work_dir) / source_dir.name
            else:
                logger.info("Skipping sync - submitting job in host work directory")
                remote_work_dir = Path(slurm_host.work_dir)

            logger.info("Parsing script for login node setup and compute commands...")

            with open(script_path, "r") as f:
                original_script_content = f.read()

            login_setup_commands, clean_compute_script = self._parse_structured_script(
                original_script_content
            )

            if python_env:
                if login_setup_commands:
                    logger.info(
                        "Combining structured script login setup with python_env parameter"
                    )
                    login_setup_commands = f"{login_setup_commands}\n{python_env}"
                else:
                    login_setup_commands = python_env

            logger.info("Preparing clean compute script for SLURM submission...")
            remote_script_dir = remote_work_dir / "scripts"
            temp_dir = Path("/tmp/slurm_launch")
            temp_dir.mkdir(exist_ok=True)
            clean_script_path = temp_dir / f"clean_{script_path.name}"

            with open(clean_script_path, "w") as f:
                f.write(clean_compute_script)

            prepared_script = ScriptProcessor.prepare_script(
                clean_script_path, temp_dir, params=slurm_params
            )

            conn = self.slurm_manager._get_connection(slurm_host.host)
            conn.run(f"mkdir -p {remote_script_dir}")
            remote_script_path = send_file(
                conn,
                local_path=str(prepared_script),
                remote_path=str(remote_script_dir / prepared_script.name),
                is_remote_dir=False,
            )
            conn.run(f"chmod +x {remote_script_path}")

            logger.info(f"Script uploaded to {remote_script_path}")

            if login_setup_commands:
                logger.info("Executing login node setup commands...")
                logger.debug(f"Login setup commands:\n{login_setup_commands}")
                try:
                    with conn.cd(remote_work_dir):
                        setup_result = conn.run(login_setup_commands, warn=True)

                        if setup_result.ok:
                            logger.info("Login node setup completed successfully")
                            logger.debug(f"Setup output: {setup_result.stdout}")
                        else:
                            logger.warning("Login node setup completed with warnings")
                            logger.warning(f"Setup stderr: {setup_result.stderr}")

                except Exception as e:
                    logger.error(f"Login node setup failed: {e}")

            logger.info("Submitting job to SLURM...")
            logger.info(f"Changing to working directory: {remote_work_dir}")
            conn.run(f"cd {remote_work_dir}")
            job = self._submit_script_in_workdir(
                slurm_host, slurm_params, remote_script_path, remote_work_dir
            )

            if job:
                logger.info(f"Job submitted successfully with ID: {job.job_id}")
                try:
                    from .job_data_manager import get_job_data_manager

                    job_data_manager = get_job_data_manager()
                    await job_data_manager.capture_job_submission(
                        job.job_id, slurm_host.host.hostname, clean_compute_script
                    )
                    logger.debug(f"Captured submission data for job {job.job_id}")
                except Exception as e:
                    logger.warning(
                        f"Failed to capture submission data for job {job.job_id}: {e}"
                    )

                return job
            else:
                logger.error("Failed to submit job")
                return None

        except Exception as e:
            logger.error(f"Error during job launch: {e}")
            return None
        finally:
            try:
                if "clean_script_path" in locals() and clean_script_path.exists():
                    clean_script_path.unlink()
                    logger.debug("Cleaned up temporary clean script file")
            except Exception as e:
                logger.debug(f"Could not clean up temporary file: {e}")

            try:
                if "temp_dir" in locals() and temp_dir.exists():
                    import shutil

                    shutil.rmtree(temp_dir, ignore_errors=True)
                    logger.debug("Cleaned up temporary directory")
            except Exception as e:
                logger.debug(f"Could not clean up temporary directory: {e}")

    def _submit_script_in_workdir(
        self,
        slurm_host,
        slurm_params: SlurmParams,
        remote_script_path: str,
        work_dir: Path,
    ) -> Optional[Job]:
        """Submit a script to SLURM from a specific working directory.

        Args:
            slurm_host: The SLURM host to submit to
            slurm_params: SLURM parameters for the job
            remote_script_path: Path to the script on the remote host
            work_dir: Working directory to run sbatch from

        Returns:
            Job object if successful, None otherwise
        """
        import re

        conn = self.slurm_manager._get_connection(slurm_host.host)

        try:
            cmd = ["sbatch"]

            if slurm_params.job_name:
                cmd.append(f"--job-name={slurm_params.job_name}")
            if slurm_params.time_min:
                cmd.append(f"--time={slurm_params.time_min}")
            if slurm_params.cpus_per_task:
                cmd.append(f"--cpus-per-task={slurm_params.cpus_per_task}")
            if slurm_params.mem_gb:
                cmd.append(f"--mem={slurm_params.mem_gb}G")
            if slurm_params.partition:
                cmd.append(f"--partition={slurm_params.partition}")
            if slurm_params.output:
                cmd.append(f"--output={slurm_params.output}")
            if slurm_params.error:
                cmd.append(f"--error={slurm_params.error}")
            if slurm_params.constraint:
                cmd.append(f"--constraint={slurm_params.constraint}")
            if slurm_params.account:
                cmd.append(f"--account={slurm_params.account}")
            if slurm_params.nodes:
                cmd.append(f"--nodes={slurm_params.nodes}")
            if slurm_params.n_tasks_per_node:
                cmd.append(f"--ntasks-per-node={slurm_params.n_tasks_per_node}")
            if slurm_params.gpus_per_node:
                cmd.append(f"--gpus-per-node={slurm_params.gpus_per_node}")
            if slurm_params.gres:
                cmd.append(f"--gres={slurm_params.gres}")

            cmd.append(remote_script_path)
            full_cmd = f"cd {work_dir} && {' '.join(cmd)}"
            logger.info(f"Running: {full_cmd}")

            result = conn.run(full_cmd, hide=False)
            job_id_match = re.search(r"Submitted batch job (\d+)", result.stdout)
            if job_id_match:
                job_id = job_id_match.group(1)
                return Job(job_id, slurm_host, self.slurm_manager)
            else:
                logger.error(f"Could not parse job ID from: {result.stdout}")
                return None

        except Exception as e:
            logger.error(f"Failed to submit job from {work_dir}: {e}")
            return None
