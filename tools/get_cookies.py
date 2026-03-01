import os
import sys
import logging
from pathlib import Path
from typing import Any

# Coba import yt_dlp, berikan pesan error yang jelas jika belum terinstall
try:
    import yt_dlp
except ImportError:
    print("❌ Error: Modul 'yt_dlp' tidak ditemukan.")
    print("   Harap install dependencies terlebih dahulu dengan: pip install -r requirements.txt")
    sys.exit(1)

# Konfigurasi Logging sederhana
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)

def main():
    print("=== HSU AI CLIPPER: Cookie Extractor Tool ===")
    print("Alat ini akan mencoba mengambil cookies dari browser lokal Anda")
    print("dan menyimpannya ke 'files/cookies.txt' untuk autentikasi YouTube.\n")

    # Tentukan path output relative terhadap lokasi script ini
    # Script ada di tools/, kita mau simpan di files/ (satu level di atas tools/)
    base_dir = Path(__file__).parent.parent
    cookies_file = base_dir / "files" / "cookies.txt"
    
    # Pastikan folder files ada
    cookies_file.parent.mkdir(parents=True, exist_ok=True)

    supported_browsers = ["opera","chrome", "firefox", "edge", "brave"]
    success = False

    print(f"📂 Target Output: {cookies_file}")
    print("⏳ Memulai ekstraksi...\n")

    for browser in supported_browsers:
        print(f"👉 Mencoba browser: {browser}...", end=" ")
        
        # Opsi yt-dlp untuk ekstrak cookies tanpa download
        opts : Any = {
            'cookiesfrombrowser': (browser,),
            'cookiefile': str(cookies_file),
            'quiet': False,
            'no_warnings': False,
            'verbose': False,
            'skip_download': True,
        }

        try:
            # Kita jalankan ekstraksi dummy ke YouTube untuk memicu pengambilan cookies
            with yt_dlp.YoutubeDL(opts) as ydl:
                ydl.extract_info("https://www.youtube.com", download=False)
            
            # Cek apakah file berhasil dibuat dan ada isinya
            if cookies_file.exists() and cookies_file.stat().st_size > 0:
                print("✅ BERHASIL!")
                success = True
                break
            else:
                print("❌ Gagal (File kosong/tidak terbuat)")
        
        except Exception as e:
            # Error biasanya terjadi jika browser tidak terinstall atau database terkunci
            msg = str(e).split('\n')[0]
            print(f"❌ Gagal ({msg})")

    print("-" * 50)
    if success:
        print(f"✨ Sukses! Cookies tersimpan di: {cookies_file}")
        print("   Sekarang Anda bisa menjalankan 'main.py' tanpa masalah login.")
    else:
        print("⚠️  Gagal mengekstrak cookies dari semua browser.")
        print("   Kemungkinan penyebab:")
        print("   1. Browser tidak terinstall atau profil pengguna tidak ditemukan.")
        print("   2. Browser sedang terbuka (TUTUP browser lalu coba lagi).")
        print("   3. Anda belum login YouTube di browser tersebut.")
        print("\n   👉 Solusi Alternatif: Gunakan ekstensi browser 'Get cookies.txt LOCALLY'")
        print("      dan simpan file manual ke folder 'files/'.")

if __name__ == "__main__":
    main()