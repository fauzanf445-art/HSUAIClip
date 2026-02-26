import logging

from pipeline import ProcessingStep, ProcessingContext
from modules.downloader import Downloader

class InitializationStep(ProcessingStep):
    def execute(self, context: ProcessingContext):
        Downloader.check_and_setup_cookies(context.core.paths.COOKIE_FILE)
        
        # Find Deno once and store it in the context
        context.deno_path = context.core.find_executable('deno.exe') or context.core.find_executable('deno')
        
        downloader = Downloader(context.url, cookies_path=context.core.paths.COOKIE_FILE, deno_path=context.deno_path)
        
        folder_name = downloader.get_folder_name()
        context.video_info = downloader.get_info()
        work_dir = context.core.paths.TEMP_DIR / folder_name
        work_dir.mkdir(parents=True, exist_ok=True)
        context.work_dir = work_dir
        logging.info(f"📂 Working Directory: {work_dir}")