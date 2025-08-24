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

    def launch_job(
        self,
        script_path: str | Path,
        source_dir: str | Path,
        host: str,
        slurm_params: SlurmParams,
        python_env: Optional[str] = None,
        exclude: List[str] = None,
        include: List[str] = None,
        no_gitignore: bool = False,
    ) -> Optional[Job]:
        """Launch a job with sync and submission.

        Args:
            script_path: Path to the script to submit (.sh or .slurm)
            source_dir: Source directory to sync to remote
            host: Target host (required)
            job_name: SLURM job name
            cpus: Number of CPUs per task
            mem: Memory in GB
            time: Time limit in minutes
            n_tasks_per_node: Number of tasks per node
            nodes: Number of nodes
            gpus_per_node: Number of GPUs per node
            gres: Generic resources (e.g., "gpu:1")
            partition: SLURM partition
            output: Output file path
            error: Error file path
            constraint: Node constraints (e.g., "gpu", "bigmem")
            account: SLURM account for billing
            python_env: Python environment setup command
            exclude: Patterns to exclude from sync
            include: Patterns to include in sync
            no_gitignore: Disable .gitignore usage

        Returns:
            Job object if successful, None otherwise
        """
        # Validate inputs
        script_path = Path(script_path)
        source_dir = Path(source_dir)

        if not script_path.exists():
            logger.error(f"Script not found: {script_path}")
            return None

        if not source_dir.exists():
            logger.error(f"Source directory not found: {source_dir}")
            return None

        # Get target host
        try:
            slurm_host = self.slurm_manager.get_host_by_name(host)
        except ValueError as e:
            logger.error(str(e))
            return None

        logger.info(f"Launching job on {slurm_host.host.hostname}")

        try:
            # Step 1: Sync source directory to remote
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

            # Step 2: Prepare script for submission
            logger.info("Preparing script for SLURM submission...")

            # Create remote script directory in work_dir
            remote_work_dir = Path(slurm_host.work_dir) / source_dir.name
            remote_script_dir = remote_work_dir / "scripts"

            # Process script locally first to determine parameters
            temp_dir = Path("/tmp/slurm_launch")

            prepared_script = ScriptProcessor.prepare_script(
                script_path, temp_dir, params=slurm_params
            )

            # Upload prepared script to remote
            conn = self.slurm_manager._get_connection(slurm_host.host)

            # Create remote script directory
            conn.run(f"mkdir -p {remote_script_dir}")

            # Upload the prepared script
            remote_script_path = send_file(
                conn,
                local_path=str(prepared_script),
                remote_path=str(remote_script_dir / prepared_script.name),
                is_remote_dir=False,
            )
            conn.run(f"chmod +x {remote_script_path}")

            logger.info(f"Script uploaded to {remote_script_path}")

            # Step 3: Add Python environment setup if specified
            if python_env:
                # Prepend python environment setup to the script
                env_setup = f"# Python environment setup\n{python_env}\n\n"
                conn.run(f'sed -i "1a\\{env_setup}" {remote_script_path}')

            # Step 4: Submit job to SLURM
            logger.info("Submitting job to SLURM...")

            # slurm_params was created earlier and can be reused for submission

            # Submit the job
            job = self.slurm_manager.submit_script(
                slurm_host, params=slurm_params, remote_script_path=remote_script_path
            )

            if job:
                logger.info(f"Job submitted successfully with ID: {job.job_id}")
                return job
            else:
                logger.error("Failed to submit job")
                return None

        except Exception as e:
            logger.error(f"Error during job launch: {e}")
            return None
        finally:
            # Clean up temporary files
            if "temp_dir" in locals() and temp_dir.exists():
                import shutil

                shutil.rmtree(temp_dir, ignore_errors=True)
