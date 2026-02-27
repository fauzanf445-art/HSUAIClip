import logging
from pathlib import Path
from typing import List

from .core import ProjectCore
from .pipeline import ProcessingContext, ProcessingPipeline
from .pipeline_steps import (
    InitializationStep,
    SummarizationStep,
    ClipCreationStep,
    MotionTrackingStep,
    CaptioningStep,
    RenderingStep
)

def run_project(url: str) -> tuple[Path, List[Path]]:
    # 1. Setup Project Core & Verify Assets
    core = ProjectCore()
    logging.debug("✅ Inisialisasi sistem logging berhasil. Debug log aktif.")
    logging.info(f"📝 Debug Log: {core.paths.LOG_FILE}")
    
    logging.info("⚙️ Menjalankan pemeriksaan sistem...")
    core.verify_assets()

    # 2. Setup Pipeline
    context = ProcessingContext(url=url, core=core)
    pipeline = ProcessingPipeline(context)

    pipeline.add(InitializationStep(core))
    pipeline.add(SummarizationStep(core))
    pipeline.add(ClipCreationStep(core))
    pipeline.add(MotionTrackingStep(core))
    pipeline.add(CaptioningStep(core))
    pipeline.add(RenderingStep(core))

    # 3. Run Pipeline
    try:
        pipeline.run()
    except Exception:
        # The pipeline itself will log the detailed error.
        # We re-raise it to be caught by the main UI loop.
        raise

    # 4. Return results from context
    work_dir = context.work_dir if context.work_dir else Path.cwd()
    return work_dir, context.final_clips