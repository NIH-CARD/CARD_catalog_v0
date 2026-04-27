"""
Base class for all CARD Catalog pipeline stages.
"""
from abc import ABC, abstractmethod
from pathlib import Path


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
