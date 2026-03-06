import json
import logging
import time
import re
import uuid
from pathlib import Path
from typing import Optional, List, Union

from google import genai
from google.genai import types

from src.domain.interfaces import IContentAnalyzer
from src.domain.models import VideoSummary, Clip

class GeminiAdapter(IContentAnalyzer):
    def __init__(self, api_key: str, model_name: str):
        self.api_key = api_key
        self.model_name = f"models/{model_name}"
        self.client: genai.Client = genai.Client(api_key=self.api_key)

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

    def _upload_and_process_audio(self, audio_path: Path) -> types.File:
        """
        Mengunggah file audio ke server Gemini dan menunggu hingga statusnya 'ACTIVE'.

        Raises:
            TimeoutError: Jika proses indexing melebihi batas waktu.
            ValueError: Jika file gagal diproses dan statusnya bukan 'ACTIVE'.
        """
        logging.debug(f"Mengunggah file audio ke Gemini: {audio_path.name}...")
        uploaded_file = self.client.files.upload(
            file=audio_path, # SDK terbaru mendukung argumen 'path' secara langsung
            config=types.UploadFileConfig(
                display_name=audio_path.name,
                mime_type='audio/wav'
            )
        )
        
        # Tunggu proses indexing
        start_wait = time.time()
        while uploaded_file.state == "PROCESSING":

            if time.time() - start_wait > 600: 
                raise TimeoutError("Timeout: Proses indexing audio terlalu lama.")
            time.sleep(2)
            if not uploaded_file.name:
                raise ValueError("File name is missing during processing")
            uploaded_file = self.client.files.get(name=uploaded_file.name)
        
        if uploaded_file.state != "ACTIVE":
            raise ValueError(f"Gagal memproses audio. Status: {uploaded_file.state}")
        
        logging.debug(f"✅ Audio {uploaded_file.name} berhasil diproses.")
        return uploaded_file

    def analyze_content(self, transcript: str, audio_path: str, prompt: str) -> VideoSummary:
        """
        Menganalisis konten menggunakan Gemini dan mengembalikan objek domain VideoSummary.
        """
        audio_file_path = Path(audio_path)
        uploaded_file: Optional[types.File] = None

        try:
            request_parts: List[types.Part] = []

            # 2. Upload Audio jika ada
            if audio_file_path.exists():
                uploaded_file = self._upload_and_process_audio(audio_file_path)
            if transcript:
                request_parts.append(types.Part.from_text(text=transcript))

            request_parts.append(types.Part.from_text(text=f"Instruction:\n{prompt}"))

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
            contents = types.Content(
                role="user",
                parts=request_parts)
            
            response: types.GenerateContentResponse = self.client.models.generate_content(
                model=self.model_name,
                contents=contents,
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
                    if not uploaded_file.name:
                        raise ValueError("File name is missing during processing")
                    self.client.files.delete(name=uploaded_file.name)
                    logging.info(f"🗑️ File {uploaded_file.name} dibersihkan dari server.")
                except Exception as e:
                    logging.warning(f"Gagal membersihkan file di server Gemini ({uploaded_file.name}): {e}")