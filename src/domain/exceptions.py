class HSUAIClipError(Exception):
    """Base exception class for HSUAIClip application."""
    pass

class MediaDownloadError(HSUAIClipError):
    """Raised when media download or metadata extraction fails."""
    pass

class VideoProcessingError(HSUAIClipError):
    """Raised when video processing (FFmpeg/OpenCV) fails."""
    pass

class AnalysisError(HSUAIClipError):
    """Raised when AI content analysis fails."""
    pass

class TranscriptionError(HSUAIClipError):
    """Raised when audio transcription fails."""
    pass