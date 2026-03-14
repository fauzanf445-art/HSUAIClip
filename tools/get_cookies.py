import sys
import logging
from pathlib import Path

# Coba import yt_dlp, berikan pesan error yang jelas jika belum terinstall
try:
    import yt_dlp
except ImportError:
    print("❌ Error: Modul 'yt_dlp' tidak ditemukan.")
    print("   Harap install dependencies terlebih dahulu dengan: pip install -r requirements.txt")
    sys.exit(1)

try:
    sys.path.append(str(Path(__file__).parent.parent))
    from src.infrastructure.adapters.youtube_adapter import YouTubeAdapter
except ImportError:
    print("❌ Error Import: Tidak dapat menemukan modul 'src'.")
    print("👉 Harap jalankan script ini dari root folder project sebagai modul:")
    print("   python -m tools.get_cookies")
    print("\n👉 ATAU gunakan perintah utama yang baru:")
    print("   python app.py --extract-cookies")
    sys.exit(1)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)

def main():
    print("=== HSU AI CLIPPER: Cookie Extractor Tool ===")
    print("Alat ini akan mencoba mengambil cookies dari browser lokal Anda")
    print("dan menyimpannya ke 'files/cookies.txt' untuk autentikasi YouTube.\n")

    base_dir = Path(__file__).parent.parent
    cookies_file = base_dir / "files" / "cookies.txt"
    
    cookies_file.parent.mkdir(parents=True, exist_ok=True)

    print(f"📂 Target Output: {cookies_file}")
    print("⏳ Memulai ekstraksi...\n")

    success = YouTubeAdapter.extract_cookies_from_browser(cookies_file)

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