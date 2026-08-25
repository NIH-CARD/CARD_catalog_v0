"""
Base class for all CARD Catalog pipeline stages.
"""
import re
from abc import ABC, abstractmethod
from pathlib import Path

_SECRET_NAME_PATTERN = re.compile(r"key|token", re.IGNORECASE)


def redact_secrets(args: dict) -> dict:
    """Redact any argument whose name looks like a credential (contains 'key' or
    'token') so API keys/tokens never land in log files. Recurses into a nested
    'kwargs' dict (stages that take **kwargs) so secrets passed through it are
    redacted too.
    """
    result = {}
    for k, v in args.items():
        if _SECRET_NAME_PATTERN.search(k):
            result[k] = "<redacted>"
        elif k == "kwargs" and isinstance(v, dict):
            result[k] = redact_secrets(v)
        else:
            result[k] = v
    return result


class PipelineStage(ABC):
    """
    A single transformation step in the pipeline.

    Subclasses must implement run().  The orchestrator calls run() only
    when there is no up-to-date output already present in tables/hits/.
    """

    @abstractmethod
    def run(self, input_path: Path, output_path: Path, **kwargs) -> Path:
        """
        Execute the stage.

        Args:
            input_path: Input file (inventory, or previous stage's hits file).
            output_path: Destination path in tables/hits/ (or tables/final/).
            **kwargs:    Stage-specific options (api keys, flags, etc.).

        Returns:
            Path to the output file that was written.
        """
        ...

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}()"
