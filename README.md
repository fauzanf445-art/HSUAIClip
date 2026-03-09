# HSUAIClip

Aplikasi berbasis terminal untuk mengotomatiskan pembuatan klip video pendek
(shorts) dari video YouTube yang lebih panjang. Aplikasi ini menggunakan AI
untuk menganalisis konten, memotong bagian paling menarik, melakukan _motion
tracking_ pada subjek, dan menambahkan subtitle dengan efek karaoke secara
otomatis.

## ✨ Fitur Utama

- **Analisis Konten Cerdas**: Menggunakan Google Gemini untuk menganalisis
  transkrip dan audio, lalu merekomendasikan klip potensial berdasarkan energi
  vokal dan relevansi konten.
- **Pemotongan Otomatis**: Memotong klip video secara presisi menggunakan FFmpeg
  dengan dukungan akselerasi perangkat keras (NVIDIA, Intel, AMD, Apple).
- **Motion Tracking (Auto-Cropping)**: Menggunakan MediaPipe untuk mendeteksi
  wajah/subjek dan secara otomatis mengubah video horizontal menjadi format
  vertikal (9:16) dengan subjek selalu di tengah.
- **Subtitle Karaoke**: Menghasilkan transkrip per kata menggunakan
  Faster-Whisper dan membuat file subtitle `.ass` dengan efek animasi karaoke.
- **Arsitektur Bersih (Clean Architecture)**: Kode diorganisir dengan baik,
  memisahkan logika bisnis dari detail implementasi, membuatnya mudah diuji dan
  dipelihara.

## 🏗️ Arsitektur

Proyek ini menerapkan prinsip **Clean Architecture** untuk memastikan kode yang
modular, dapat diuji, dan mudah dikelola.

- **`src/domain`**: Berisi model data murni (seperti `Clip`) dan _interfaces_
  (kontrak) yang mendefinisikan apa yang harus dilakukan sistem, tanpa peduli
  bagaimana caranya.
- **`src/application`**: Berisi _services_ yang mengorkestrasi logika bisnis
  (kasus penggunaan), seperti `VideoService` atau `AnalysisService`. Lapisan ini
  bergantung pada _interfaces_ dari domain.
- **`src/infrastructure`**: Berisi implementasi konkret dari _interfaces_. Di
  sinilah semua alat eksternal seperti `FFmpegAdapter`, `GeminiAdapter`, dan
  `WhisperAdapter` berada.
- **`main.py`**: Titik masuk aplikasi yang bertanggung jawab untuk "merakit"
  semua komponen (_Dependency Injection_).

## 📋 Prasyarat Sistem

Aplikasi ini membutuhkan beberapa perangkat lunak eksternal yang harus terinstal
secara global di sistem Anda dan tersedia di `PATH`.

1. **FFmpeg**: Diperlukan untuk semua operasi video dan audio.
2. **Node.js**: Diperlukan sebagai JavaScript runtime untuk `yt-dlp` agar dapat
   mengunduh beberapa video dari YouTube.

### Perintah Instalasi

Pastikan untuk membuka terminal/CMD baru setelah instalasi agar `PATH`
diperbarui.

- **Windows (via Winget):**
  ```powershell
  winget install Gyan.FFmpeg
  winget install OpenJS.NodeJS.LTS
  ```
- **Linux (Ubuntu/Debian):**
  ```bash
  sudo apt update && sudo apt install ffmpeg nodejs npm
  ```
- **macOS (via Homebrew):**
  ```bash
  brew install ffmpeg node
  ```

---

## ⚙️ Instalasi & Konfigurasi Proyek

1. **Clone Repositori**
   ```bash
   git clone https://github.com/username/HSUAIClip.git
   cd HSUAIClip
   ```

2. **Install Dependensi Python** Disarankan untuk menggunakan _virtual
   environment_.
   ```bash
   python -m venv .venv
   source .venv/bin/activate  # Linux/macOS
   .venv\Scripts\activate    # Windows

   pip install -r requirements.txt
   ```

3. **Konfigurasi API Key (Wajib)** Aplikasi ini memerlukan API Key dari Google
   Gemini.
   - Buat file baru bernama `.env` di dalam folder `files/`. Path lengkap:
     `files/.env`.
   - Isi file tersebut dengan format berikut:
     ```env
     GEMINI_API_KEY=AIzaSy...YOUR_API_KEY...
     ```
   Jika file ini tidak ada, aplikasi akan memintanya saat pertama kali
   dijalankan.

4. **Konfigurasi Cookies (Opsional, tapi Sangat Disarankan)** Untuk menghindari
   pemblokiran dari YouTube saat mengunduh, disarankan untuk menggunakan cookies
   dari browser Anda yang sudah login ke YouTube.
   - Jalankan skrip bantuan untuk mengekstrak cookies secara otomatis:
     ```bash
     python tools/get_cookies.py
     ```
   - Skrip ini akan mencoba mengambil cookies dari browser (Chrome, Firefox,
     Edge, dll.) dan menyimpannya ke `files/cookies.txt`. Pastikan browser Anda
     dalam keadaan tertutup saat menjalankan skrip ini.

## 🚀 Cara Menjalankan

Setelah semua konfigurasi selesai, jalankan aplikasi utama:

```bash
python main.py
```

Aplikasi akan meminta URL YouTube, lalu memulai proses pipeline. Anda juga dapat
memasukkan _timestamp_ manual jika tidak ingin menggunakan analisis AI.

## 🧪 Menjalankan Tes

Proyek ini dilengkapi dengan unit test dan integration test.

### 1. Unit Tests

Tes ini berjalan cepat dan tidak memerlukan koneksi internet atau API key.

```bash
python -m unittest discover tests
```

### 2. Integration Test

Tes ini akan menjalankan pipeline lengkap pada video YouTube sungguhan ("Me at
the zoo"), termasuk pemanggilan API Gemini dan pemrosesan FFmpeg.

**Peringatan:** Tes ini akan menggunakan kuota API Anda dan memerlukan koneksi
internet.

**Prasyarat:**

- Pastikan `GEMINI_API_KEY` sudah ada di `files/.env`.
- Jalankan aplikasi utama setidaknya sekali untuk memastikan model-model
  (Whisper, MediaPipe) sudah terunduh.

**Menjalankan tes:**

```bash
python -m unittest tests.test_integration
```
