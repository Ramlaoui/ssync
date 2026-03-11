"""Helpers for Slurm array-job handling."""

from __future__ import annotations

import re
from typing import Optional

_ARRAY_SUBMISSION_RE = re.compile(
    r"(^|\s)(#SBATCH\s+--array(?:=|\s)|sbatch\b[^\n]*\s--array(?:=|\s))",
    re.MULTILINE,
)


def looks_like_array_submission(
    script_content: Optional[str] = None, submit_line: Optional[str] = None
) -> bool:
    """Return True when the submission appears to define a Slurm array job."""
    for text in (script_content, submit_line):
        if text and _ARRAY_SUBMISSION_RE.search(text):
            return True
    return False
