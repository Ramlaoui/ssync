# SSH Backend Migration and Rollback Guide

## Overview
This guide documents the native SSH backend implementation and provides clear rollback procedures if issues arise.

## Current Implementation Status

### New Components Added
1. **Native SSH Backend** (`src/ssync/ssh/`)
   - `native_connection.py` - Core SSH implementation with ControlMaster
   - `compatibility.py` - Fabric API compatibility wrapper
   - `pool_manager.py` - Connection pooling for concurrent operations
   - `config_parser.py` - Configuration conversion utilities

2. **Enhanced ConnectionManager** (`src/ssync/connection.py`)
   - Dual backend support (Fabric + Native)
   - Purpose-based connection routing
   - Backward compatibility maintained

3. **Watcher Updates** 
   - `src/ssync/watchers/actions.py` - Uses dedicated connections
   - `src/ssync/watchers/engine.py` - Non-blocking SSH operations

### Backend Selection
The backend is controlled via environment variable:
```bash
# Options:
export SSYNC_SSH_BACKEND=fabric  # Default, original implementation
export SSYNC_SSH_BACKEND=native  # New native SSH with ControlMaster
export SSYNC_SSH_BACKEND=auto    # Auto-select based on purpose
```

## Testing the New Backend

### Quick Test
```bash
# Test with native backend
export SSYNC_SSH_BACKEND=native
ssync status --host <your-host>

# Test with auto mode (recommended for gradual migration)
export SSYNC_SSH_BACKEND=auto
ssync status --host <your-host>
```

### Comprehensive Test
```bash
cd /home/aliramlaoui/slurm-manager
uv run python test_native_ssh.py
```

## Rollback Procedures

### Method 1: Environment Variable (Immediate, No Code Changes)
```bash
# Disable native SSH completely
export SSYNC_SSH_BACKEND=fabric

# Or simply unset it (defaults to fabric)
unset SSYNC_SSH_BACKEND

# Verify
echo $SSYNC_SSH_BACKEND  # Should be empty or "fabric"
```

### Method 2: Code Rollback (Complete Removal)
If you need to completely remove the native SSH implementation:

```bash
# 1. Restore original files from backups
cp src/ssync/connection.py.backup src/ssync/connection.py
cp src/ssync/manager.py.backup src/ssync/manager.py

# 2. Remove new SSH backend directory
rm -rf src/ssync/ssh/

# 3. Revert watcher changes
git checkout -- src/ssync/watchers/actions.py
git checkout -- src/ssync/watchers/engine.py

# 4. Clean up test files
rm -f test_native_ssh.py
rm -f SSH_BACKEND_ROLLBACK.md
```

### Method 3: Git Revert (Clean History)
```bash
# Find the commit before native SSH implementation
git log --oneline | grep -B1 "native SSH"

# Revert to that commit (replace COMMIT_HASH with actual hash)
git revert COMMIT_HASH

# Or reset if you haven't pushed
git reset --hard COMMIT_HASH
```

## Migration Strategy

### Phase 1: Testing (Current)
- Keep `SSYNC_SSH_BACKEND=fabric` (default)
- Test native backend manually as needed

### Phase 2: Gradual Rollout
```bash
# Use auto mode - native for watchers, fabric for everything else
export SSYNC_SSH_BACKEND=auto

# Or enable native only for watchers
export SSYNC_NATIVE_SSH_WATCHERS=true
```

### Phase 3: Full Migration
```bash
# Once confident, switch completely
export SSYNC_SSH_BACKEND=native
```

### Phase 4: Cleanup (Optional)
After successful migration, you can remove Fabric dependency:
```bash
# Remove fabric from dependencies
uv pip uninstall fabric paramiko

# Update pyproject.toml to remove fabric dependency
```

## Troubleshooting

### Issue: Connection Errors with Native Backend
```bash
# Check if ControlMaster is supported
ssh -o ControlMaster=auto -o ControlPath=/tmp/test.sock localhost exit
# If this fails, your SSH doesn't support ControlMaster

# Solution: Revert to Fabric
export SSYNC_SSH_BACKEND=fabric
```

### Issue: Watchers Blocking Other Operations
```bash
# This was the original issue - watchers should NOT block with native backend
# Verify backend is correct
export SSYNC_SSH_BACKEND=native  # or auto

# Check connection stats
ssync status --verbose  # Should show separate pools for watchers
```

### Issue: Performance Degradation
```bash
# Native SSH creates persistent connections, check if they're working
ls -la /tmp/ssync_ssh_*  # Should see control sockets

# If sockets are stale, clean them
rm -f /tmp/ssync_ssh_*

# Restart with fresh connections
export SSYNC_SSH_BACKEND=native
ssync status --host <your-host>
```

## Verification After Rollback

Run these commands to ensure rollback was successful:

```bash
# 1. Check backend setting
echo "Backend: ${SSYNC_SSH_BACKEND:-fabric}"

# 2. Test basic operations
ssync status --host <your-host>
ssync sync . --host <your-host> --dry-run

# 3. Test job submission (dry run)
echo '#!/bin/bash' > test.sh
echo 'echo "Test job"' >> test.sh
ssync submit test.sh --host <your-host> --dry-run
rm test.sh

# 4. Check for any import errors
uv run python -c "from ssync import SlurmManager; print('Import successful')"
```

## Benefits of Native SSH Backend

1. **Non-blocking Operations**: Watchers don't block other SSH operations
2. **Better Performance**: ControlMaster reuses connections
3. **Resource Efficiency**: Connection pooling reduces overhead
4. **Improved Concurrency**: Multiple operations can run simultaneously

## Risks and Mitigations

| Risk | Mitigation |
|------|------------|
| ControlMaster not supported | Auto-fallback to regular SSH |
| Connection pool exhaustion | Configurable pool sizes |
| Stale control sockets | Automatic cleanup after timeout |
| Compatibility issues | Fabric-compatible wrapper layer |

## Configuration Options

```bash
# Backend selection
export SSYNC_SSH_BACKEND=fabric|native|auto

# Native SSH specific
export SSYNC_NATIVE_SSH_WATCHERS=true|false  # Use native for watchers only

# Connection pool sizes (advanced)
export SSYNC_SSH_POOL_MAIN_SIZE=2
export SSYNC_SSH_POOL_WATCHER_SIZE=3
export SSYNC_SSH_POOL_DOWNLOAD_SIZE=2

# ControlMaster timeout (seconds)
export SSYNC_SSH_CONTROL_PERSIST=600  # Default: 10 minutes
```

## Support

If you encounter issues:
1. First try rollback Method 1 (environment variable)
2. Check troubleshooting section
3. If needed, perform full rollback with Method 2 or 3
4. Report issues with:
   - Error messages
   - `SSYNC_SSH_BACKEND` value
   - Output of `ssh -V`
   - Host configuration (anonymized)