from dataclasses import dataclass
from typing import List, Any, Dict


@dataclass
class Clip:
    title: str
    start_time: float
    end_time: float
    duration: float
    energy_score: int
    vocal_energy: str
    audio_justification: str
    description: str
    caption: str

    @classmethod
    def from_dict(cls, data: Dict[str, Any]):
        return cls(
            title=data.get('title', 'Untitled'),
            start_time=float(data.get('start_time', 0.0)),
            end_time=float(data.get('end_time', 0.0)),
            duration=float(data.get('duration', 0.0)),
            energy_score=int(data.get('energy_score', 0)),
            vocal_energy=data.get('vocal_energy', 'Unknown'),
            audio_justification=data.get('audio_justification', ''),
            description=data.get('description', ''),
            caption=data.get('caption', '')
        )

@dataclass
class VideoSummary:
    video_title: str
    audio_energy_profile: str
    clips: List[Clip]

    @classmethod
    def from_dict(cls, data: Dict[str, Any]):
        clips = [Clip.from_dict(c) for c in data.get('clips', [])]
        return cls(
            video_title=data.get('video_title', 'Unknown Video'),
            audio_energy_profile=data.get('audio_energy_profile', ''),
            clips=clips
        )