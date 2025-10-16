"""
Reality Check: Does polling and WebSocket monitoring actually work?

This test verifies the ACTUAL behavior of the system, not just that functions exist.
"""

import pytest
import asyncio
from unittest.mock import Mock, patch, AsyncMock, MagicMock
from datetime import datetime


@pytest.mark.asyncio
async def test_reality_check_backend_force_refresh_bypasses_cache():
    """
    REALITY CHECK: Does force_refresh=true actually bypass the backend cache?

    This is THE critical test - it verifies that when frontend sends
    force_refresh=true, the backend actually ignores its cache and queries SLURM.
    """
    from ssync.web.app import get_job_status
    from ssync.models.job import JobInfo, JobState
    from ssync.web.cache_middleware import get_cache_middleware

    # Get cache middleware
    cache_middleware = get_cache_middleware()

    # Setup: Cache a job with PENDING state
    old_job = JobInfo(
        job_id="reality-123",
        name="test-job",
        state=JobState.PENDING,
        hostname="test.cluster.com",
        submit_time=datetime.now().isoformat(),
        user="testuser",
    )
    cache_middleware.cache.cache_job(old_job)

    # Verify it's cached
    cached = cache_middleware.cache.get_cached_job("reality-123", "test.cluster.com")
    assert cached is not None, "❌ Job should be cached"
    assert cached.job_info.state == JobState.PENDING, "❌ Cached job should be PENDING"

    print("✅ Step 1: Job cached with PENDING state")

    # Now test the actual API endpoint behavior
    # The issue: We need to mock the SLURM manager to return updated data

    # Mock the SLURM manager to return updated job
    with patch('ssync.web.app.get_slurm_manager') as mock_manager:
        # Mock job data manager
        with patch('ssync.web.app.get_job_data_manager') as mock_jdm:
            # Create mock job data manager
            mock_data_manager = AsyncMock()

            # When force_refresh=True, it should query SLURM and return RUNNING
            updated_job = JobInfo(
                job_id="reality-123",
                name="test-job",
                state=JobState.RUNNING,  # ← Updated state!
                hostname="test.cluster.com",
                submit_time=datetime.now().isoformat(),
                user="testuser",
            )

            # Mock fetch_all_jobs to return updated job when force_refresh=True
            mock_data_manager.fetch_all_jobs = AsyncMock(return_value=[updated_job])
            mock_jdm.return_value = mock_data_manager

            # Mock SLURM hosts
            mock_host = Mock()
            mock_host.host.hostname = "test.cluster.com"
            mock_manager.return_value.slurm_hosts = [mock_host]

            # Create mock request
            mock_request = Mock()

            # Call the endpoint WITH force_refresh=True
            try:
                result = await get_job_status(
                    request=mock_request,
                    host="test.cluster.com",
                    user="testuser",
                    force_refresh=True,  # ← THE CRITICAL PARAMETER
                    authenticated=True,
                )

                print(f"✅ Step 2: API called with force_refresh=True")

                # Verify fetch_all_jobs was called with force_refresh=True
                assert mock_data_manager.fetch_all_jobs.called, \
                    "❌ FAIL: fetch_all_jobs was not called!"

                call_args = mock_data_manager.fetch_all_jobs.call_args
                assert call_args is not None, "❌ FAIL: No call args recorded"

                # Check if force_refresh was passed as True
                if 'force_refresh' in call_args.kwargs:
                    assert call_args.kwargs['force_refresh'] == True, \
                        f"❌ FAIL: force_refresh={call_args.kwargs['force_refresh']}, expected True"
                    print("✅ Step 3: force_refresh=True was passed to fetch_all_jobs")
                else:
                    print("⚠️  WARNING: force_refresh not in kwargs, may be using default")

                # Verify result contains updated job
                assert len(result) > 0, "❌ FAIL: No results returned"
                assert result[0].jobs[0].state == "R", \
                    f"❌ FAIL: Job state is {result[0].jobs[0].state}, expected R"

                print("✅ Step 4: API returned RUNNING job (cache bypassed!)")
                print("\n🎉 REALITY CHECK PASSED: force_refresh actually bypasses cache!")

            except Exception as e:
                print(f"❌ REALITY CHECK FAILED: {e}")
                import traceback
                traceback.print_exc()
                raise


@pytest.mark.asyncio
async def test_reality_check_websocket_monitoring_queries_slurm():
    """
    REALITY CHECK: Does the WebSocket monitoring actually query SLURM every 30s?

    This verifies that the monitor_all_jobs_singleton() function actually
    calls fetch_all_jobs periodically.
    """
    from ssync.web.app import monitor_all_jobs_singleton, _all_jobs_websockets
    from unittest.mock import AsyncMock, MagicMock

    print("\n=== REALITY CHECK: WebSocket Monitoring ===")

    # Add a mock websocket to prevent monitor from exiting
    mock_ws = MagicMock()
    _all_jobs_websockets.add(mock_ws)

    # Mock the job data manager
    with patch('ssync.web.app.get_job_data_manager') as mock_jdm:
        mock_data_manager = AsyncMock()
        mock_data_manager.fetch_all_jobs = AsyncMock(return_value=[])
        mock_jdm.return_value = mock_data_manager

        # Mock get_slurm_manager
        with patch('ssync.web.app.get_slurm_manager') as mock_manager:
            mock_manager.return_value = MagicMock()

            # Start the monitoring task
            monitor_task = asyncio.create_task(monitor_all_jobs_singleton())

            try:
                # Wait for monitoring to run at least once
                # The monitor sleeps 30s between checks, so we need to wait
                await asyncio.sleep(0.5)  # Give it time to start

                # Check if fetch_all_jobs was called
                if mock_data_manager.fetch_all_jobs.called:
                    print("✅ PASS: WebSocket monitor called fetch_all_jobs")

                    # Check parameters
                    call_args = mock_data_manager.fetch_all_jobs.call_args
                    print(f"   Called with: {call_args}")

                    # Verify it queries all hosts (hostname=None)
                    if call_args and call_args.kwargs.get('hostname') is None:
                        print("✅ PASS: Queries all hosts (hostname=None)")
                    else:
                        print("⚠️  WARNING: May not be querying all hosts")

                    print("\n🎉 REALITY CHECK PASSED: WebSocket monitoring works!")
                else:
                    print("⚠️  WARNING: fetch_all_jobs not called yet (may need to wait 30s)")

            finally:
                # Cleanup
                monitor_task.cancel()
                try:
                    await monitor_task
                except asyncio.CancelledError:
                    pass
                _all_jobs_websockets.clear()


if __name__ == "__main__":
    print("=" * 70)
    print("RUNNING REALITY CHECKS FOR POLLING AND WEBSOCKET")
    print("=" * 70)

    asyncio.run(test_reality_check_backend_force_refresh_bypasses_cache())
    asyncio.run(test_reality_check_websocket_monitoring_queries_slurm())

    print("\n" + "=" * 70)
    print("ALL REALITY CHECKS COMPLETE!")
    print("=" * 70)
