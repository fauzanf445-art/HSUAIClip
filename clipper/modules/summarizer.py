import json
import re
import logging
import time
from pathlib import Path
from typing import Optional, List, Any, Union, Dict

from google import genai
from google.genai import types, errors

class Summarizer:
    """
    Membuat ringkasan dari transkrip, dan audio dengan gemini.
    """
    
    def __init__(self, api_key: str, model_name: str = "gemini-flash-latest"):
        self.api_key = api_key
        self.model_name = model_name
        self.client = genai.Client(api_key=self.api_key)

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

    def _clean_json_text(self, text: str) -> str:
        """Membersihkan markdown code blocks dari string JSON."""
        # Regex untuk menangkap konten di dalam ```json ... ``` atau ``` ... ```
        pattern = r"^```(?:json)?\s*(.*?)\s*```$"
        match = re.search(pattern, text.strip(), re.DOTALL)
        if match:
            return match.group(1)
        return text.strip()

    def generate_summary_from_multimodal_inputs(self, prompt_template: str, transcript_text: str, audio_file_path: Path) -> Dict[str, Any]:
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
                        config={'mime_type': 'audio/mpeg'}
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
                                "duration": types.Schema(type=types.Type.NUMBER),
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
            logging.debug("Mengirim permintaan multimodal ke Gemini...")
            response = self.client.models.generate_content( # type: ignore
                model=self.model_name,
                contents=content_parts,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=summary_schema
                )
            )
            
            # Return parsed JSON object directly
            clean_text = self._clean_json_text(str(response.text))
            return json.loads(clean_text)

        except errors.APIError as e:
            logging.error(f"API Error: {e}")
            raise

        finally:
            if uploaded_file:
                try:
                    self.client.files.delete(name=uploaded_file.name)
                    logging.info(f"🗑️ File {uploaded_file.name} dibersihkan dari server.")
                except Exception as e:
                    logging.warning(f"⚠️ Gagal menghapus file sementara di server: {e}")