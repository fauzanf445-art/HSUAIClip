from __future__ import annotations
import logging
from typing import Any, List, Dict, Optional
from pathlib import Path

from .core import ProjectCore
from .utils.models import Clip

class ProcessingContext:
    """
    An object to hold and pass data between processing steps.
    This acts as a shared state for the pipeline.
    """
    def __init__(self, url: str, core: ProjectCore):
        self.url = url
        self.core = core
        self.downloader: Optional[Any] = None
        self.work_dir: Optional[Path] = None
        self.video_info: Optional[Dict[str, Any]] = None
        self.clips_data: List[Clip] = []
        self.created_clips: List[Path] = []
        self.tracking_results: List[Dict[str, Any]] = []
        self.subtitle_map: Dict[Path, Path] = {}
        self.final_clips: List[Path] = []
        self.deno_path: Optional[str] = None

class ProcessingStep:
    """
    Abstract base class for a step in the processing pipeline.
    """
    def __init__(self, core: ProjectCore):
        self.core = core

    def execute(self, context: ProcessingContext) -> None:
        """
        Executes the processing step.
        This method must be overridden by subclasses.
        """
        raise NotImplementedError

class ProcessingPipeline:
    """
    Manages a sequence of processing steps.
    """
    def __init__(self, context: ProcessingContext):
        self._steps: List[ProcessingStep] = []
        self.context = context

    def add(self, step: ProcessingStep) -> ProcessingPipeline:
        self._steps.append(step)
        return self

    def run(self) -> None:
        for step in self._steps:
            step_name = step.__class__.__name__
            logging.info(f"🚀 Executing Pipeline Step: {step_name}...")
            step.execute(self.context)
            logging.info(f"✅ Step {step_name} completed successfully.")