# HSUAIClip

Aplikasi otomatisasi pembuatan klip video viral menggunakan AI.

## 📋 Prasyarat Sistem (Wajib Diinstall Manual)

Aplikasi ini membutuhkan dua alat eksternal agar dapat berjalan: **FFmpeg** (untuk pemrosesan video) dan **Deno** (untuk ekstraksi data YouTube). Harap install keduanya dan pastikan mereka terdaftar di `PATH` sistem Anda.

### 1. Instalasi FFmpeg

**Windows:**
1.  Unduh *build* terbaru (pilih "full" build) dari situs resmi: gyan.dev atau BtbN GitHub.
2.  Ekstrak file ZIP yang diunduh.
3.  Masuk ke folder hasil ekstrak, lalu buka folder `bin`. Salin alamat folder tersebut (contoh: `C:\ffmpeg\bin`).
4.  Tambahkan alamat tersebut ke **Environment Variables** -> **Path**.

**Linux (Ubuntu/Debian):**
```bash
sudo apt update && sudo apt install ffmpeg
```

**macOS:**
```bash
brew install ffmpeg
```

### 2. Instalasi Deno

**Windows:**
Buka PowerShell sebagai Administrator dan jalankan:
```powershell
winget install Deno.Deno
```

**Linux / macOS:**
```bash
curl -fsSL https://deno.land/install.sh | sh
```

### 3. Verifikasi Instalasi

Jalankan perintah berikut di terminal untuk memastikan instalasi berhasil:
```bash
ffmpeg -version
deno --version
```

## 🚀 Cara Menjalankan

1.  Install dependensi Python: `pip install -r requirements.txt`
2.  Jalankan aplikasi: `python main.py`
3.  Masukkan URL YouTube dan API Key Gemini saat diminta.