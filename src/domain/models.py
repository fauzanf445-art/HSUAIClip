from dataclasses import dataclass, field
from typing import List, Optional
import uuid
from typing import Dict, Any

@dataclass
class Clip:
    """
    Mewakili satu klip video. Ini adalah entitas domain murni,
    hanya berisi data tanpa logika bisnis atau ketergantungan eksternal.
    """
    id: str
    title: str
    start_time: float
    end_time: float
    duration: float
    energy_score: int
    vocal_energy: str
    audio_justification: str
    description: str
    caption: str
    # Path file fisik (opsional, diisi oleh Application/Infrastructure layer saat proses berjalan)
    raw_path: Optional[str] = None
    tracked_path: Optional[str] = None
    final_path: Optional[str] = None
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Clip':
        """Factory method untuk membuat instance Clip dari dictionary."""
        return cls(
            id=data.get('id') or str(uuid.uuid4()),
            title=data.get('title', 'Untitled'),
            start_time=float(data.get('start_time', 0.0)),
            end_time=float(data.get('end_time', 0.0)),
            duration=float(data.get('duration', 0.0)),
            energy_score=int(data.get('energy_score', 0)),
            vocal_energy=data.get('vocal_energy', 'Unknown'),
            audio_justification=data.get('audio_justification', ''),
            description=data.get('description', ''),
            caption=data.get('caption', ''),
            # Path fisik bisa jadi None saat di-load
            raw_path=data.get('raw_path'),
            tracked_path=data.get('tracked_path'),
            final_path=data.get('final_path')
        )

@dataclass
class VideoSummary:
    video_title: str
    audio_energy_profile: str
    clips: List[Clip] = field(default_factory=list)