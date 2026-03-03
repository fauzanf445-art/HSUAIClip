import logging
import getpass
import re
from typing import Optional, List, Dict
from pathlib import Path

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
            
            # Validasi Regex sederhana
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