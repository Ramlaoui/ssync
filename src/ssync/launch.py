"""Integrated job launch manager that handles sync and submission."""

import asyncio
import re
import shutil
from pathlib import Path
from typing import List, Optional

from .manager import Job, SlurmManager
from .script_processor import ScriptProcessor
from .sync import SyncManager
from .utils.logging import setup_logger
from .utils.slurm_params import SlurmParams
from .utils.ssh import send_file

logger = setup_logger(__name__, "INFO")


class LaunchManager:
    """Manages the complete job launch workflow: sync + submit."""

    def __init__(self, slurm_manager: SlurmManager, executor=None):
        self.slurm_manager = slurm_manager
        self.executor = executor

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
        abort_on_setup_failure: bool = True,
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
            abort_on_setup_failure: Whether to abort job submission if login setup fails (default: True)

        Returns:
            Job object if successful, None otherwise
        """
        script_path = Path(script_path)

        if not script_path.exists():
            error_msg = f"Script not found: {script_path}"
            logger.error(error_msg)
            raise FileNotFoundError(error_msg)

        if sync_enabled:
            if source_dir is None:
                error_msg = "Source directory is required when sync is enabled"
                logger.error(error_msg)
                raise ValueError(error_msg)
            source_dir = Path(source_dir)
            if not source_dir.exists():
                error_msg = f"Source directory not found: {source_dir}"
                logger.error(error_msg)
                raise FileNotFoundError(error_msg)
        else:
            if source_dir is not None:
                source_dir = Path(source_dir)

        try:
            slurm_host = self.slurm_manager.get_host_by_name(host)
        except ValueError as e:
            logger.error(str(e))
            raise

        logger.info(f"Launching job on {slurm_host.host.hostname}")

        try:
            loop = asyncio.get_event_loop()
            executor = self.executor

            if sync_enabled and source_dir:
                logger.info("Syncing source directory to remote host...")
                sync_manager = SyncManager(
                    self.slurm_manager, source_dir, use_gitignore=not no_gitignore
                )

                sync_success = await loop.run_in_executor(
                    executor, sync_manager.sync_to_host, slurm_host, exclude, include
                )

                if not sync_success:
                    error_msg = f"Failed to sync source directory {source_dir} to {slurm_host.host.hostname}"
                    logger.error(error_msg)
                    raise RuntimeError(error_msg)

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

            # Log what was extracted for debugging
            if login_setup_commands:
                logger.info(
                    f"Extracted login setup commands ({len(login_setup_commands)} chars)"
                )
                logger.debug(f"Login setup commands:\n{login_setup_commands}")

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

            await loop.run_in_executor(
                executor, conn.run, f"mkdir -p {remote_script_dir}"
            )

            remote_script_path = await loop.run_in_executor(
                executor,
                send_file,
                conn,
                str(prepared_script),
                str(remote_script_dir / prepared_script.name),
                False,
            )

            await loop.run_in_executor(
                executor, conn.run, f"chmod +x {remote_script_path}"
            )

            logger.info(f"Script uploaded to {remote_script_path}")

            if login_setup_commands:
                logger.info("Executing login node setup commands...")
                logger.debug(
                    f"Setup commands: {login_setup_commands[:500]}..."
                )  # Log first 500 chars
                setup_result = None
                try:

                    def run_setup():
                        with conn.cd(remote_work_dir):
                            # Use pty=False to ensure we capture all output
                            # Don't hide output to see what's happening
                            result = conn.run(
                                login_setup_commands, warn=True, hide=False, pty=False
                            )
                            # Log the result immediately for debugging
                            logger.debug(
                                f"Setup command exit code: {result.return_code}"
                            )
                            logger.debug(f"Setup stdout: {result.stdout}")
                            logger.debug(f"Setup stderr: {result.stderr}")
                            return result

                    setup_result = await loop.run_in_executor(executor, run_setup)

                    if setup_result.ok:
                        logger.info("Login node setup completed successfully")
                    else:
                        stderr_output = (
                            setup_result.stderr.strip()
                            if setup_result.stderr
                            else "No stderr captured"
                        )
                        stdout_output = (
                            setup_result.stdout.strip()
                            if setup_result.stdout
                            else "No stdout captured"
                        )

                        if abort_on_setup_failure and setup_result.return_code != 0:
                            error_msg = (
                                f"Login node setup failed with exit code {setup_result.return_code}\n"
                                f"Setup stdout:\n{stdout_output}\n"
                                f"Setup stderr:\n{stderr_output}"
                            )
                            logger.error(error_msg)
                            logger.error("Aborting job submission due to setup failure")
                            raise RuntimeError(error_msg)
                        else:
                            logger.warning("Login node setup completed with warnings")
                            logger.warning(f"Setup stdout: {stdout_output}")
                            logger.warning(f"Setup stderr: {stderr_output}")

                except Exception as e:
                    # Try to extract more details from the exception
                    error_details = str(e)

                    # If we have a setup_result, include its output
                    if setup_result:
                        stderr_output = (
                            setup_result.stderr.strip()
                            if setup_result.stderr
                            else "No stderr captured"
                        )
                        stdout_output = (
                            setup_result.stdout.strip()
                            if setup_result.stdout
                            else "No stdout captured"
                        )
                        error_msg = (
                            f"Login node setup failed with exception: {error_details}\n"
                            f"Setup stdout:\n{stdout_output}\n"
                            f"Setup stderr:\n{stderr_output}"
                        )
                    else:
                        # No setup_result means the exception happened before the command ran
                        error_msg = (
                            f"Login node setup failed with exception: {error_details}"
                        )

                    logger.error(error_msg)
                    if abort_on_setup_failure:
                        logger.error("Aborting job submission due to setup failure")
                        raise RuntimeError(error_msg)
                    else:
                        logger.warning(
                            "Continuing despite setup failure (abort_on_setup_failure=False)"
                        )

            logger.info("Submitting job to SLURM...")
            logger.info(f"Changing to working directory: {remote_work_dir}")

            await loop.run_in_executor(executor, conn.run, f"cd {remote_work_dir}")

            job = await loop.run_in_executor(
                executor,
                self._submit_script_in_workdir,
                slurm_host,
                slurm_params,
                remote_script_path,
                remote_work_dir,
            )

            if job:
                logger.info(f"Job submitted successfully with ID: {job.job_id}")
                try:
                    from .job_data_manager import get_job_data_manager

                    job_data_manager = get_job_data_manager()
                    await job_data_manager.capture_job_submission(
                        job.job_id, slurm_host.host.hostname, clean_compute_script
                    )
                except Exception as e:
                    logger.warning(
                        f"Failed to capture submission data for job {job.job_id}: {e}"
                    )

                return job
            else:
                error_msg = f"Failed to submit job to {slurm_host.host.hostname}. Check SLURM configuration and script syntax."
                logger.error(error_msg)
                raise RuntimeError(error_msg)

        except Exception as e:
            logger.error(f"Error during job launch: {e}")
            raise
        finally:
            try:
                if "clean_script_path" in locals() and clean_script_path.exists():
                    clean_script_path.unlink()
            except Exception:
                pass

            try:
                if "temp_dir" in locals() and temp_dir.exists():
                    shutil.rmtree(temp_dir, ignore_errors=True)
            except Exception:
                pass

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
        conn = self.slurm_manager._get_connection(slurm_host.host)

        try:
            # Read the script to check for existing SBATCH directives
            result = conn.run(f"head -50 {remote_script_path}", hide=True)
            script_header = result.stdout

            # Check if script already has comprehensive SBATCH directives
            has_partition = "#SBATCH --partition" in script_header
            has_time = "#SBATCH --time" in script_header
            has_cpus = "#SBATCH --cpus" in script_header
            has_gpus = (
                "#SBATCH --gpus" in script_header
                or "#SBATCH --gres=gpu" in script_header
            )

            # If script has key SBATCH directives, use minimal command line params
            # to avoid conflicts (command line overrides script directives)
            is_comprehensive_script = has_partition or (has_time and has_cpus)

            cmd = ["sbatch"]

            if is_comprehensive_script:
                logger.info(
                    "Script has SBATCH directives, using minimal command-line parameters"
                )
                # Only add parameters that are NOT likely to be in the script
                # and won't conflict with script directives
                if slurm_params.output and "#SBATCH --output" not in script_header:
                    cmd.append(f"--output={slurm_params.output}")
                if slurm_params.error and "#SBATCH --error" not in script_header:
                    cmd.append(f"--error={slurm_params.error}")
            else:
                # Script doesn't have SBATCH directives, use all provided params
                logger.info(
                    "Script lacks SBATCH directives, using command-line parameters"
                )
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

            # Store the sbatch command for caching (without the 'cd' part)
            submit_line = " ".join(cmd)
            logger.info(f"Running: {full_cmd}")

            # Extract watchers from the local script before submission
            watchers = []
            try:
                # Read the local script to extract watchers
                local_script_path = (
                    remote_script_path  # This assumes the script was copied
                )
                # We need to read from the original local script instead
                # Find the original script path from earlier in the method
                result_read = conn.run(f"cat {remote_script_path}", hide=True)
                script_content = result_read.stdout

                from .script_processor import ScriptProcessor

                watchers, _ = ScriptProcessor.extract_watchers(script_content)

                if watchers:
                    logger.info(f"Found {len(watchers)} watchers in script")
            except Exception as e:
                logger.warning(f"Failed to extract watchers: {e}")

            result = conn.run(full_cmd, hide=False)
            job_id_match = re.search(r"Submitted batch job (\d+)", result.stdout)
            if job_id_match:
                job_id = job_id_match.group(1)
                job = Job(job_id, slurm_host, self.slurm_manager)

                # Cache the submit line for this job
                try:
                    from .cache import get_cache
                    from .models.job import JobInfo, JobState

                    cache = get_cache()
                    # Create a basic job info with the submit line for running jobs
                    job_info = JobInfo(
                        job_id=job_id,
                        name=slurm_params.job_name or "unknown",
                        state=JobState.PENDING,  # Will be updated when job is queried
                        hostname=slurm_host.host.hostname,
                        submit_line=submit_line,
                        user=None,  # Will be updated when job is queried
                    )
                    cache.cache_job(job_info)
                except Exception as e:
                    logger.warning(f"Failed to cache submit line for job {job_id}: {e}")

                # Start watchers if any were found
                if watchers:
                    try:
                        import asyncio

                        from .watchers import get_watcher_engine
                        from .watchers.daemon import start_daemon_if_needed

                        engine = get_watcher_engine()

                        # Check if there's an existing event loop (e.g., from web server)
                        try:
                            loop = asyncio.get_running_loop()
                            # We're in an async context, can directly create the task
                            asyncio.create_task(
                                engine.start_watchers_for_job(
                                    job_id,
                                    slurm_host.host.hostname,
                                    watchers,
                                )
                            )
                            logger.info(
                                f"Scheduled {len(watchers)} watchers for job {job_id}"
                            )
                        except RuntimeError:
                            # No running loop, create one temporarily just to register watchers
                            loop = asyncio.new_event_loop()
                            asyncio.set_event_loop(loop)
                            try:
                                watcher_ids = loop.run_until_complete(
                                    engine.start_watchers_for_job(
                                        job_id,
                                        slurm_host.host.hostname,
                                        watchers,
                                    )
                                )
                                logger.info(
                                    f"Registered {len(watcher_ids)} watchers for job {job_id}"
                                )

                                # Start the watcher daemon to monitor them
                                if start_daemon_if_needed():
                                    logger.info(
                                        "Watcher daemon is running to monitor watchers"
                                    )
                                else:
                                    logger.warning(
                                        "Failed to start watcher daemon - watchers won't be monitored"
                                    )
                            finally:
                                loop.close()
                    except Exception as e:
                        logger.error(f"Failed to start watchers for job {job_id}: {e}")

                return job
            else:
                logger.error(f"Could not parse job ID from: {result.stdout}")
                return None

        except Exception as e:
            logger.error(f"Failed to submit job from {work_dir}: {e}")
            return None
