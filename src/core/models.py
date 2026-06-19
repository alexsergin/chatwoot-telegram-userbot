from dataclasses import dataclass


@dataclass
class MediaAttachment:
    filename: str
    data: bytes
    mime_type: str
    is_voice: bool = False
