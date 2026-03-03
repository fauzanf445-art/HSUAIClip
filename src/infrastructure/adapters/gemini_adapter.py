import json
import logging
import time
import re
import uuid
from pathlib import Path
from typing import Optional, List, Any, Union

from google import genai
from google.genai import types

from src.domain.interfaces import IContentAnalyzer
from src.domain.models import VideoSummary, Clip

class GeminiAdapter(IContentAnalyzer):
    def __init__(self, api_key: str, model_name: str):
        self.api_key = api_key
        self.model_name = f"models/{model_name}"
        self.client = genai.Client(api_key=self.api_key)

    @staticmethod
    def check_key_validity(key: str) -> bool:
        """Memeriksa apakah API Key valid dengan request ringan."""
        try:
            client = genai.Client(api_key=key)
            next(iter(client.models.list(config={'page_size': 1})), None)
            return True
        except Exception:
            return False

    def _clean_json_text(self, text: str) -> str:
        """Membersihkan markdown code blocks dari string JSON."""
        pattern = r"```(?:json)?\s*(.*?)\s*```"
        match = re.search(pattern, text.strip(), re.DOTALL)
        if match:
            return match.group(1)
        return text.strip()

    def analyze_content(self, transcript: str, audio_path: str, prompt: str) -> VideoSummary:
        """
        Menganalisis konten menggunakan Gemini dan mengembalikan objek domain VideoSummary.
        Menggantikan logika generate_summary lama + from_dict.
        """
        audio_file_path = Path(audio_path)
        uploaded_file: Optional[Any] = None

        try:
            # 1. Siapkan konten untuk API
            content_parts: List[Union[str, Any]] = [prompt]
            if transcript:
                content_parts.append(transcript)

            # 2. Upload Audio jika ada
            if audio_file_path.exists():
                logging.info(f"Mengunggah file audio ke Gemini: {audio_file_path.name}...")
                with audio_file_path.open('rb') as audio_data:
                    uploaded_file = self.client.files.upload(
                        file=audio_data,
                        config={'mime_type': 'audio/wav'}
                    )
                
                # Tunggu proses indexing
                start_wait = time.time()
                while uploaded_file.state.name == "PROCESSING":
                    if time.time() - start_wait > 600:
                        raise TimeoutError("Timeout: Proses indexing audio di server Google terlalu lama.")
                    time.sleep(2)
                    uploaded_file = self.client.files.get(name=uploaded_file.name)
                
                if uploaded_file.state.name != "ACTIVE":
                    raise ValueError("Gagal mengunggah file audio ke server AI.")
                
                content_parts.append(uploaded_file)

            # 3. Definisi Schema (Structured Output)
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

            # 4. Request ke Gemini
            logging.debug("Mengirim permintaan multimodal ke Gemini...")
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=content_parts,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=summary_schema
                )
            )

            # 5. Parse JSON dan Mapping ke Domain Models
            clean_text = self._clean_json_text(str(response.text))
            data = json.loads(clean_text)

            clips_list = []
            for c_data in data.get('clips', []):
                clips_list.append(Clip.from_dict(c_data))

            return VideoSummary(
                video_title=data.get('video_title', 'Unknown Video'),
                audio_energy_profile=data.get('audio_energy_profile', ''),
                clips=clips_list
            )

        except Exception as e:
            logging.error(f"Gemini Adapter Error: {e}")
            raise

        finally:
            if uploaded_file:
                try:
                    self.client.files.delete(name=uploaded_file.name)
                    logging.info(f"🗑️ File {uploaded_file.name} dibersihkan dari server.")
                except Exception:
                    pass