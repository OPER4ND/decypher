"""Windows audio session control for VALORANT."""

from __future__ import annotations

try:
    from pycaw.pycaw import AudioUtilities, ISimpleAudioVolume
    AUDIO_AVAILABLE = True
except ImportError:
    AUDIO_AVAILABLE = False


_cached_volume = None


def _is_valorant_audio_process(session) -> bool:
    process = getattr(session, "Process", None)
    if not process:
        return False

    try:
        name = process.name().lower()
    except Exception:
        return False

    return name == "valorant-win64-shipping.exe"


def _get_valorant_volume():
    global _cached_volume
    if _cached_volume is not None:
        return _cached_volume

    try:
        for session in AudioUtilities.GetAllSessions():
            if _is_valorant_audio_process(session):
                _cached_volume = session._ctl.QueryInterface(ISimpleAudioVolume)
                return _cached_volume
    except Exception:
        pass
    return None


def reset_audio_session_cache():
    global _cached_volume
    _cached_volume = None


def mute_valorant(mute: bool = True) -> bool:
    """Mute or unmute the VALORANT audio session in the Windows volume mixer."""
    global _cached_volume
    if not AUDIO_AVAILABLE:
        return False

    try:
        volume = _get_valorant_volume()
        if volume:
            volume.SetMute(1 if mute else 0, None)
            return True
    except Exception:
        _cached_volume = None
    return False
