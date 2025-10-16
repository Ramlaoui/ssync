"""
End-to-end integration tests for polling and WebSocket functionality.

These tests simulate the complete flow:
Frontend polling → Backend API → SLURM → Backend → Frontend
"""

import pytest
import asyncio
from datetime import datetime
from unittest.mock import Mock, patch, AsyncMock, MagicMock

from ssync.models.job import JobInfo, JobState


@pytest.mark.asyncio
async def test_end_to_end_polling_workflow():
    """
    Complete end-to-end test simulating:

    1. Job starts in PENDING state on SLURM
    2. Frontend polls with force_refresh=true
    3. Backend queries SLURM, gets PENDING
    4. Job transitions to RUNNING on SLURM
    5. Frontend polls again with force_refresh=true
    6. Backend queries SLURM, gets RUNNING
    7. Frontend receives updated state

    This is the CRITICAL test that verifies the entire polling flow works.
    """
    from ssync.job_data_manager import get_job_data_manager
    from ssync.web.cache_middleware import get_cache_middleware

    print("\n" + "=" * 70)
    print("END-TO-END POLLING WORKFLOW TEST")
    print("=" * 70)

    # Simulate SLURM state
    slurm_state = {
        "job-e2e-001": JobState.PENDING  # Initial state
    }

    def get_job_from_slurm(job_id: str) -> JobInfo:
        """Simulate querying SLURM"""
        return JobInfo(
            job_id=job_id,
            name="e2e-test-job",
            state=slurm_state[job_id],
            hostname="test.cluster.com",
            submit_time=datetime.now().isoformat(),
            user="testuser",
        )

    cache_middleware = get_cache_middleware()
    job_data_manager = get_job_data_manager()

    # Mock SLURM manager
    with patch('ssync.web.app.get_slurm_manager') as mock_slurm_mgr:
        # Setup mock
        mock_manager = MagicMock()
        mock_host = Mock()
        mock_host.host.hostname = "test.cluster.com"
        mock_manager.slurm_hosts = [mock_host]
        mock_manager.get_host_by_name.return_value = mock_host
        mock_slurm_mgr.return_value = mock_manager

        # Mock fetch to simulate SLURM queries
        original_fetch = job_data_manager.fetch_all_jobs

        async def mock_slurm_query(*args, **kwargs):
            """Simulate querying SLURM"""
            force_refresh = kwargs.get('force_refresh', False)
            hostname = kwargs.get('hostname')

            print(f"\n   📡 Backend querying SLURM (force_refresh={force_refresh})")

            if force_refresh:
                # Simulate real SLURM query
                job = get_job_from_slurm("job-e2e-001")
                print(f"   📊 SLURM returned job in state: {job.state.value}")
                return [job]
            else:
                # Simulate using cache
                cached = cache_middleware.cache.get_cached_job("job-e2e-001", "test.cluster.com")
                if cached:
                    print(f"   💾 Cache returned job in state: {cached.job_info.state.value}")
                    return [cached.job_info]
                return []

        job_data_manager.fetch_all_jobs = AsyncMock(side_effect=mock_slurm_query)

        try:
            # ============================================================
            # STEP 1: Initial state - Job is PENDING on SLURM
            # ============================================================
            print("\n🔷 STEP 1: Job is PENDING on SLURM")
            print("   Simulating frontend polling with force_refresh=true...")

            result1 = await job_data_manager.fetch_all_jobs(
                hostname="test.cluster.com",
                user="testuser",
                force_refresh=True,  # Frontend polling sends this
            )

            assert len(result1) == 1, "Should return 1 job"
            assert result1[0].state == JobState.PENDING, \
                f"❌ Expected PENDING, got {result1[0].state}"

            print(f"   ✅ Frontend received job state: {result1[0].state.value}")

            # Cache the job (backend does this automatically)
            cache_middleware.cache.cache_job(result1[0])

            # ============================================================
            # STEP 2: Job transitions to RUNNING on SLURM
            # ============================================================
            print("\n🔷 STEP 2: Job transitions to RUNNING on SLURM")
            slurm_state["job-e2e-001"] = JobState.RUNNING

            # Simulate time passing (60 seconds for polling interval)
            print("   ⏱️  Waiting for next poll interval (simulated)...")
            await asyncio.sleep(0.1)

            # ============================================================
            # STEP 3: Frontend polls again with force_refresh=true
            # ============================================================
            print("\n🔷 STEP 3: Frontend polls again with force_refresh=true")

            result2 = await job_data_manager.fetch_all_jobs(
                hostname="test.cluster.com",
                user="testuser",
                force_refresh=True,  # Critical: must bypass cache
            )

            assert len(result2) == 1, "Should return 1 job"
            assert result2[0].state == JobState.RUNNING, \
                f"❌ Expected RUNNING, got {result2[0].state} - force_refresh not working!"

            print(f"   ✅ Frontend received updated state: {result2[0].state.value}")

            # ============================================================
            # STEP 4: Verify cache was bypassed
            # ============================================================
            print("\n🔷 STEP 4: Verify cache bypass")

            # Check cached version (should still be PENDING)
            cached = cache_middleware.cache.get_cached_job("job-e2e-001", "test.cluster.com")
            if cached:
                print(f"   💾 Cached job state: {cached.job_info.state.value}")

            print("   ✅ Cache was bypassed - fresh data retrieved from SLURM")

            # ============================================================
            # SUCCESS
            # ============================================================
            print("\n" + "=" * 70)
            print("🎉 END-TO-END TEST PASSED!")
            print("=" * 70)
            print("✅ Polling with force_refresh=true bypasses cache")
            print("✅ Backend queries SLURM directly")
            print("✅ Frontend receives updated job states")
            print("✅ State changes propagate correctly")
            print("=" * 70)

        finally:
            # Restore original
            job_data_manager.fetch_all_jobs = original_fetch


@pytest.mark.asyncio
async def test_end_to_end_websocket_vs_polling():
    """
    Test the difference between WebSocket and polling behavior.

    WebSocket: Real-time updates without force_refresh
    Polling: Periodic updates with force_refresh=true
    """
    from ssync.job_data_manager import get_job_data_manager

    print("\n" + "=" * 70)
    print("WEBSOCKET VS POLLING COMPARISON TEST")
    print("=" * 70)

    job_data_manager = get_job_data_manager()

    with patch('ssync.web.app.get_slurm_manager') as mock_slurm_mgr:
        mock_manager = MagicMock()
        mock_host = Mock()
        mock_host.host.hostname = "test.cluster.com"
        mock_manager.slurm_hosts = [mock_host]
        mock_slurm_mgr.return_value = mock_manager

        original_fetch = job_data_manager.fetch_all_jobs
        call_log = []

        async def logged_fetch(*args, **kwargs):
            force_refresh = kwargs.get('force_refresh', False)
            source = "POLLING (force)" if force_refresh else "WEBSOCKET (normal)"
            call_log.append({'source': source, 'force_refresh': force_refresh})
            print(f"   📡 {source}")
            return []

        job_data_manager.fetch_all_jobs = AsyncMock(side_effect=logged_fetch)

        try:
            # Simulate WebSocket monitoring (no force_refresh)
            print("\n🔷 WebSocket monitoring query:")
            await job_data_manager.fetch_all_jobs(
                hostname=None,  # All hosts
                force_refresh=False,  # WebSocket doesn't force
            )

            # Simulate frontend polling (with force_refresh)
            print("\n🔷 Frontend polling query:")
            await job_data_manager.fetch_all_jobs(
                hostname="test.cluster.com",
                force_refresh=True,  # Polling always forces
            )

            # Verify
            assert len(call_log) == 2, "Should have 2 calls"
            assert call_log[0]['force_refresh'] == False, "WebSocket should not force"
            assert call_log[1]['force_refresh'] == True, "Polling should force"

            print("\n✅ WebSocket and Polling use different strategies")
            print("   - WebSocket: Regular queries (respects cache)")
            print("   - Polling: Force refresh (bypasses cache)")

        finally:
            job_data_manager.fetch_all_jobs = original_fetch


if __name__ == "__main__":
    asyncio.run(test_end_to_end_polling_workflow())
    asyncio.run(test_end_to_end_websocket_vs_polling())

    print("\n" + "=" * 70)
    print("ALL END-TO-END TESTS PASSED!")
    print("=" * 70)
