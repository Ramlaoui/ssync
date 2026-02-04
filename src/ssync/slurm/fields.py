"""Slurm field definitions for squeue and sacct commands."""

# Slurm squeue command field definitions
SQUEUE_FIELDS = [
    "%i",  # JobID
    "%j",  # JobName
    "%T",  # State
    "%u",  # User
    "%P",  # Partition
    "%D",  # Nodes
    "%C",  # CPUs
    "%m",  # Memory
    "%l",  # TimeLimit
    "%M",  # Runtime
    "%r",  # Reason
    "%Z",  # WorkDir
    "%o",  # StdOut
    "%e",  # StdErr
    "%V",  # SubmitTime
    "%S",  # StartTime
    "%a",  # Account
    "%q",  # QoS
    "%Q",  # Priority
    "%R",  # NodeList
]

# Slurm sacct command field definitions - core fields for maximum compatibility
SACCT_FIELDS = [
    "JobID",  # 0
    "JobName",  # 1
    "State",  # 2
    "User",  # 3
    "Partition",  # 4
    "AllocNodes",  # 5
    "AllocCPUS",  # 6
    "ReqMem",  # 7
    "Timelimit",  # 8
    "Elapsed",  # 9
    "Submit",  # 10
    "Start",  # 11
    "End",  # 12
    "WorkDir",  # 13
    "NodeList",  # 14
    "Reason",  # 15
    "ExitCode",  # 16
    "Account",  # 17
    "QOS",  # 18
    "Priority",  # 19
]

# Extended fields for hosts that support them
SACCT_EXTENDED_FIELDS = [
    "JobID",
    "JobName",
    "State",
    "User",
    "Partition",
    "AllocNodes",
    "AllocCPUS",
    "AllocTRES",
    "ReqTRES",
    "ReqMem",
    "Timelimit",
    "Elapsed",
    "CPUTime",
    "TotalCPU",
    "UserCPU",
    "SystemCPU",
    "AveCPU",
    "AveCPUFreq",
    "ReqCPUFreqMin",
    "ReqCPUFreqMax",
    "MaxRSS",
    "AveRSS",
    "MaxVMSize",
    "AveVMSize",
    "MaxDiskRead",
    "MaxDiskWrite",
    "AveDiskRead",
    "AveDiskWrite",
    "ConsumedEnergy",
    "NodeList",
    "Reason",
    "Submit",
    "Start",
    "End",
    "WorkDir",
]
