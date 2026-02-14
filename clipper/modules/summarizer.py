import json
import logging
import time
import os
from pathlib import Path
from typing import Optional, List, Any, Union

from google import genai
from google.genai import types, errors

from dotenv import load_dotenv, set_key

class GeminiSetup:
    """
    Kelas utilitas untuk persiapan awal sebelum proses berat dimulai.
    Menangani validasi API Key dan Prompt.
    """
    @staticmethod
    def validate_api_key(env_path: Path) -> str:
        """
        Memastikan API Key valid dari file .env.
        Raises: ValueError jika key tidak ditemukan atau tidak valid.
        """
        
        # Pastikan file .env ada
        if not env_path.exists():
            env_path.touch()

        load_dotenv(dotenv_path=env_path)
        api_key = os.getenv("GEMINI_API_KEY")

        if not api_key:
            raise ValueError("API Key tidak ditemukan di konfigurasi.")

        if not GeminiSetup.check_key_validity(api_key):
            raise ValueError("API Key yang tersimpan tidak valid.")

        logging.info("✅ API Key terverifikasi valid.")
        return api_key

    @staticmethod
    def check_key_validity(key: str) -> bool:
        """Memeriksa apakah API Key valid dengan melakukan request ringan."""
        try:
            client = genai.Client(api_key=key)
            next(iter(client.models.list(config={'page_size': 1})), None)
            return True
        except Exception as e:
            logging.error(f"Validasi API Key gagal: {e}")
            return False

    @staticmethod
    def save_api_key(env_path: Path, key: str) -> None:
        """Menyimpan API Key ke file .env."""
        set_key(str(env_path), "GEMINI_API_KEY", key)

    @staticmethod
    def load_prompt(prompt_path: Path) -> str:
        if not prompt_path.exists():
            raise FileNotFoundError(f"❌ File prompt tidak ditemukan di: {prompt_path}")
            
        return prompt_path.read_text(encoding='utf-8')

class GeminiSummarizer:
    """
    Membuat ringkasan dari transkrip, dan audio dengan gemini.
    """
    
    def __init__(self, api_key: str, model_name: str = "gemini-flash-latest", output_path: Optional[Path] = None):
        self.api_key = api_key
        self.model_name = model_name
        self.output_path = output_path
        self.client = genai.Client(api_key=self.api_key)

    def generate_summary_from_multimodal_inputs(self, prompt_template: str, transcript_text: str, audio_file_path: Path) -> Any:
        """
        Memproses prompt, transkrip, dan file audio untuk menghasilkan ringkasan.
        """
        uploaded_file: Optional[Any] = None

        try:
            # 1. Siapkan konten untuk API
            content_parts: List[Union[str, Any]] = [prompt_template]

            # 2. Jika ada transkrip, tambahkan ke konten
            if transcript_text:
                content_parts.append(transcript_text)

            # 2. Jika ada file audio, unggah dan tambahkan ke konten
            if audio_file_path and audio_file_path.exists():
                logging.info(f"Mengunggah file audio: {audio_file_path.name}...")

                with audio_file_path.open('rb') as audio_data:
                    uploaded_file = self.client.files.upload(
                        file=audio_data,
                        config={'mime_type': 'audio/mp3'}
                    )
                
                # Tunggu proses indexing di server Google
                start_wait = time.time()
                while uploaded_file.state.name == "PROCESSING":
                    if time.time() - start_wait > 600:  # Timeout ditingkatkan ke 10 menit
                        raise TimeoutError("Timeout: Proses indexing audio di server Google memakan waktu terlalu lama (>10 menit).")
                    time.sleep(2)
                    uploaded_file = self.client.files.get(name=uploaded_file.name)
                
                if uploaded_file.state.name != "ACTIVE":
                    raise ValueError("Gagal mengunggah file audio ke server AI.")

                content_parts.append(uploaded_file)

            # Definisi Schema untuk Structured Output
            # Ini menjamin output JSON valid tanpa perlu parsing string manual
            summary_schema = types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "video_title": types.Schema(type=types.Type.STRING),
                    "audio_energy_profile": types.Schema(type=types.Type.STRING),
                    "clips": types.Schema(
                        type=types.Type.ARRAY,
                        items=types.Schema(
                            type=types.Type.OBJECT,
                            properties={
                                "title": types.Schema(type=types.Type.STRING),
                                "start_time": types.Schema(type=types.Type.NUMBER),
                                "end_time": types.Schema(type=types.Type.NUMBER),
                                "duration": types.Schema(type=types.Type.STRING),
                                "energy_score": types.Schema(type=types.Type.INTEGER),
                                "vocal_energy": types.Schema(type=types.Type.STRING),
                                "audio_justification": types.Schema(type=types.Type.STRING),
                                "description": types.Schema(type=types.Type.STRING),
                                "caption": types.Schema(type=types.Type.STRING)
                            },
                            required=["title", "start_time", "end_time", "duration", "energy_score", "vocal_energy", "audio_justification", "description", "caption"]
                        )
                    )
                },
                required=["video_title", "audio_energy_profile", "clips"]
            )

            # 3. Kirim permintaan ke model AI dan minta output JSON
            logging.info("Mengirim permintaan multimodal ke Gemini...")
            response = self.client.models.generate_content( # type: ignore
                model=self.model_name,
                contents=content_parts,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=summary_schema
                )
            )
            summary = response.text

            if self.output_path and summary:
                json_output_path = self.output_path / "summary.json"
                try:
                    # Parsing langsung (dijamin valid oleh schema)
                    parsed_json = json.loads(summary)
                    
                    # Simpan dengan format rapi
                    json_output_path.write_text(
                        json.dumps(parsed_json, indent=2, ensure_ascii=False), 
                        encoding='utf-8'
                    )
                    logging.info(f"💾 File JSON disimpan di: {json_output_path}")
                except Exception as e:
                    logging.error(f"❌ Gagal menyimpan summary.json: {e}")
                    (self.output_path / "summary_raw_error.txt").write_text(summary, encoding='utf-8')
            return summary

        except errors.APIError as e:
            logging.error(f"API Error: {e}")
            error_msg = f'{{"error": "Gagal interaksi Gemini API", "detail": "{e}"}}'
            return error_msg

        finally:
            if uploaded_file:
                try:
                    self.client.files.delete(name=uploaded_file.name)
                    logging.info(f"🗑️ File {uploaded_file.name} dibersihkan dari server.")
                except Exception as e:
                    logging.warning(f"⚠️ Gagal menghapus file sementara di server: {e}")