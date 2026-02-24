import sys
import time

class ConsoleProgressBar:
    """
    Menangani tampilan progress bar ke terminal.
    """
    def __init__(self):
        self._last_printed_percent = -1.0
        self._last_update_time = 0.0

    def update(self, percent: float, task_name: str, extra_info: str = ""):
        """
        Menampilkan atau memperbarui progress bar.
        Dilengkapi dengan throttling agar tidak flickering.
        """
        current_time = time.time()
        
        # Optimization: Update hanya jika persentase berubah signifikan, atau sudah 100%,
        # atau sudah berlalu 0.1 detik sejak update terakhir.
        if (percent - self._last_printed_percent < 1.0 and percent < 100 and
            current_time - self._last_update_time < 0.1 and self._last_printed_percent != -1.0):
            return

        self._last_printed_percent = percent
        self._last_update_time = current_time
        
        bar_length = 25
        filled_length = int(bar_length * percent // 100)
        bar = '█' * filled_length + '░' * (bar_length - filled_length)
        
        if len(extra_info) > 30:
            extra_info = extra_info[:27] + "..."
            
        try:
            sys.stdout.write(f"\r⏳ {task_name}: {bar} {int(percent)}% {extra_info}\033[K")
            sys.stdout.flush()
        
        except UnicodeEncodeError:
            # Fallback jika terminal tidak mendukung emoji (misal cmd.exe legacy)
            sys.stdout.write(f"\r[Progress] {task_name}: {bar} {int(percent)}% {extra_info}\033[K")
            sys.stdout.flush()

    def finish(self):
        """Membersihkan baris atau membuat baris baru setelah selesai."""
        sys.stdout.write("\n")
        sys.stdout.flush()