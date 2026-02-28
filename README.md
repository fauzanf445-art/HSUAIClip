# HSUAIClip

Aplikasi otomatisasi pembuatan klip video viral menggunakan AI.

## 📋 Prasyarat Sistem (Wajib Diinstall Manual)

Aplikasi ini membutuhkan dua alat eksternal agar dapat berjalan: **FFmpeg** (untuk pemrosesan video) dan **Deno** (untuk ekstraksi data YouTube).

Anda dapat memilih salah satu dari dua metode instalasi berikut:

### Opsi A: Metode Portable (Disarankan / Paling Mudah)
Cukup letakkan file aplikasi di dalam folder `bin` di dalam folder proyek ini. Aplikasi akan otomatis mendeteksinya tanpa perlu pengaturan sistem.

1.  Buat folder bernama `bin` di dalam folder utama `HSUAICLIP`.
2.  **FFmpeg:**
    *   Unduh dari gyan.dev (Windows) atau sumber lain.
    *   Ambil file `ffmpeg.exe` dan `ffprobe.exe`.
    *   Masukkan ke folder `HSUAICLIP/bin/`.
3.  **Deno:**
    *   Unduh Deno (file zip) dari github.com/denoland/deno/releases.
    *   Ambil file `deno.exe` (Windows) atau binary `deno` (Linux/Mac).
    *   Masukkan ke folder `HSUAICLIP/bin/`.

**Struktur Folder:**
```text
HSUAICLIP/
├── bin/
│   ├── ffmpeg.exe
│   ├── ffprobe.exe
│   └── deno.exe
├── main.py
```

### Opsi B: Instalasi ke System PATH

#### 1. Instalasi FFmpeg

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