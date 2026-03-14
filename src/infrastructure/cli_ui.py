import logging
import getpass
import os
import re
from pathlib import Path
from typing import Optional, List, Dict, Tuple

class ConsoleUI:
    """Antarmuka Pengguna berbasis Terminal."""

    def print_banner(self):
        print("\n" + "="*40)
        print("   🎬 HSU AI CLIPPER - CLEAN ARCH   ")
        print("="*40 + "\n")

    def get_api_key(self) -> str:
        print("\n🔑 Konfigurasi API Key Diperlukan")
        while True:
            key = getpass.getpass("👉 Masukkan Gemini API Key: ").strip()
            if key: return key
            print("❌ API Key tidak boleh kosong.")

    def get_video_url(self) -> str:
        while True:
            url = input("\n👉 Masukkan URL YouTube: ").strip()
            if not url:
                print("❌ URL wajib diisi.")
                continue
            
            if not re.match(r'^(https?://)?(www\.)?(youtube\.com|youtu\.be)/.+$', url):
                print("❌ Format URL tidak valid.")
                continue
            return url

    def get_manual_clips(self) -> Optional[List[Dict[str, float]]]:
        """
        Meminta input timestamp manual (opsional).
        Mengembalikan list of dictionaries, bukan objek domain.
        """
        print("\n👉 (Opsional) Mode Manual: Masukkan timestamp (detik).")
        print("   Format: start-end, start-end (Contoh: 60-90, 120-150)")
        user_input = input("   [Tekan Enter untuk Analisis AI Otomatis]: ").strip()
        
        if not user_input:
            return None
            
        timestamps = []
        try:
            for part in user_input.split(','):
                if '-' not in part: continue
                s, e = map(float, part.split('-'))
                if s >= e: continue
                
                timestamps.append({'start_time': s, 'end_time': e})
            return timestamps if timestamps else None
        except ValueError:
            print("❌ Format salah. Menggunakan mode AI.")
            return None

    def show_step(self, step_name: str):
        logging.info(f"🚀 [STEP] {step_name}...")

    def show_error(self, msg: str):
        logging.error(f"❌ ERROR: {msg}")

    def show_success(self, output_dir: Path, clips: List[Path]):
        logging.info("="*40)
        logging.info("✨ PROSES SELESAI!")
        logging.info("="*40)
        logging.info(f"📂 Folder Output: {output_dir}")
        if clips:
            logging.info(f"🎬 {len(clips)} Klip Berhasil Dibuat:")
            for c in clips:
                logging.info(f"   - {c.name}")
        else:
            logging.warning("⚠️ Tidak ada klip yang dihasilkan.")

    def log(self, msg: str):
        """Wrapper untuk print biasa agar user melihat progress."""
        logging.info(f"   -> {msg}")

    def _get_files_to_prune(
        self, 
        video_files: List[Tuple[Path, float, int]], 
        max_files: int, 
        max_size_mb: int
    ) -> List[Path]:
        """
        """
        # Urutkan file dari yang paling tua ke yang paling baru
        video_files.sort(key=lambda x: x[1])

        to_delete_by_count = set()
        to_delete_by_size = set()

        # Aturan 1: Hapus file tertua jika jumlah file melebihi batas
        if len(video_files) > max_files:
            for i in range(len(video_files) - max_files):
                to_delete_by_count.add(video_files[i][0])

        # Aturan 2: Hapus file tertua jika total ukuran melebihi batas
        # Aturan ini dihitung secara independen, dan hasilnya digabungkan.
        # Test case `test_get_files_to_prune_combined_rules` mengasumsikan
        # bahwa kita harus berada di BAWAH (<) batas ukuran, bukan <=.
        current_total_size = sum(f[2] for f in video_files)
        max_size_bytes = max_size_mb * 1024 * 1024

        for file_path, _, file_size in video_files:
            if current_total_size < max_size_bytes:
                break
            to_delete_by_size.add(file_path)
            current_total_size -= file_size

        to_delete_paths = to_delete_by_count.union(to_delete_by_size)

        # Kembalikan sebagai list yang diurutkan berdasarkan waktu modifikasi (paling tua dulu)
        return sorted(list(to_delete_paths), key=lambda p: p.stat().st_mtime)

    def prune_output_directory(self, output_dir: Path, max_files: int = 10, max_size_mb: int = 500):
        """
        Memangkas folder output jika melebihi batas ukuran atau jumlah file.
        Menghapus file video tertua (berdasarkan waktu modifikasi) terlebih dahulu.
        """
        self.log(f"Memeriksa folder output untuk pemangkasan: {output_dir}")
        
        try:
            # 1. Kumpulkan semua file video final dan statistiknya
            video_files = []
            for root, _, files in os.walk(output_dir):
                for file in files:
                    if file.lower().startswith('final_') and file.lower().endswith(('.mp4', '.mov')):
                        file_path = Path(root) / file
                        try:
                            stat = file_path.stat()
                            video_files.append((file_path, stat.st_mtime, stat.st_size))
                        except FileNotFoundError:
                            continue # File mungkin sudah dihapus oleh proses lain
            
            num_files = len(video_files)
            total_size_mb = sum(f[2] for f in video_files) / (1024 * 1024)
            self.log(f"Status saat ini: {num_files} file, {total_size_mb:.2f} MB")

            # 2. Dapatkan daftar file untuk dihapus dari logika terpisah yang bisa diuji
            files_to_delete = self._get_files_to_prune(video_files, max_files, max_size_mb)

            if not files_to_delete:
                self.log("Tidak ada pemangkasan yang diperlukan.")
                return

            # 3. Lakukan penghapusan file
            self.log(f"Akan menghapus {len(files_to_delete)} file...")
            for file_path in files_to_delete:
                try:
                    self.log(f"   -> Menghapus {file_path.name}")
                    file_path.unlink()
                except OSError as e:
                    self.show_error(f"Gagal menghapus file {file_path}: {e}")
        
        except Exception as e:
            self.show_error(f"Terjadi error saat memangkas folder output: {e}")