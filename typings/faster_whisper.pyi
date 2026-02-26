from typing import Any, Iterable, List, NamedTuple, Optional, Tuple, Union
from numpy import ndarray

__version__: str

def available_models() -> List[str]: ...

def download_model(
    size_or_id: str,
    output_dir: Optional[str] = None,
    local_files_only: bool = False,
    cache_dir: Optional[str] = None,
) -> str: ...

def format_timestamp(
    seconds: float,
    always_include_hours: bool = False,
    decimal_marker: str = ".",
) -> str: ...

def decode_audio(
    audio: Union[str, bytes, ndarray],
    sampling_rate: int = 16000,
) -> ndarray: ...

# Mendefinisikan struktur data yang dikembalikan oleh model
class Word(NamedTuple):
    start: float
    end: float
    word: str
    probability: float

class Segment(NamedTuple):
    start: float
    end: float
    text: str
    words: Optional[List[Word]]

class TranscriptionInfo(NamedTuple):
    language: str
    language_probability: float
    duration: float
    # Tambahkan atribut lain jika ada

class WhisperModel:
    """
    Stub untuk faster_whisper.WhisperModel.
    Ini hanya berisi definisi tipe, bukan implementasi.
    """
    def __init__(
        self,
        model_size_or_path: str,
        device: str = "auto",
        device_index: Union[int, List[int]] = 0,
        compute_type: str = "default",
        cpu_threads: int = 0,
        num_workers: int = 1,
        download_root: Optional[str] = None,
        local_files_only: bool = False,
    ) -> None: ...

    def transcribe(
        self,
        audio: Union[str, ndarray],
        language: Optional[str] = None,
        task: str = "transcribe",
        beam_size: int = 5,
        word_timestamps: bool = False,
        # Tambahkan parameter lain yang sering Anda gunakan
        **kwargs: Any,
    ) -> Tuple[Iterable[Segment], TranscriptionInfo]: ...

class BatchedInferencePipeline:
    """Stub untuk BatchedInferencePipeline."""
    def __init__(self, *args: Any, **kwargs: Any) -> None: ...
    def __call__(self, *args: Any, **kwargs: Any) -> Any: ...
