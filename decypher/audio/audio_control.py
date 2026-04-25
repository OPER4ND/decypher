"""Windows audio session control for VALORANT."""

from __future__ import annotations

from dataclasses import dataclass

try:
    import comtypes
    from pycaw.api.audiopolicy import IAudioSessionControl2
    from pycaw.api.mmdeviceapi import IMMDeviceEnumerator
    from pycaw.constants import CLSID_MMDeviceEnumerator, EDataFlow, ERole
    from pycaw.pycaw import AudioSession, AudioUtilities, ISimpleAudioVolume

    AUDIO_AVAILABLE = True
except ImportError:
    AUDIO_AVAILABLE = False


MUTE_TARGET_DEFAULT = "default_output"
MUTE_TARGET_COMMS = "communications_output"
MUTE_TARGET_BOTH = "both"


@dataclass(frozen=True)
class _SessionBinding:
    key: str
    volume: object


_UNSET = object()
_cached_targets = {
    MUTE_TARGET_BOTH: _UNSET,
    MUTE_TARGET_DEFAULT: _UNSET,
    MUTE_TARGET_COMMS: _UNSET,
}


def _is_valorant_audio_process(session) -> bool:
    process = getattr(session, "Process", None)
    if not process:
        return False

    try:
        name = process.name().lower()
    except Exception:
        return False

    return name == "valorant-win64-shipping.exe"


def _binding_from_session(session) -> _SessionBinding | None:
    try:
        volume = session._ctl.QueryInterface(ISimpleAudioVolume)
        key = getattr(session, "InstanceIdentifier", None) or getattr(session, "Identifier", None)
        if not key:
            key = f"valorant:{getattr(session, 'ProcessId', 0)}:{id(volume)}"
        return _SessionBinding(key=key, volume=volume)
    except Exception:
        return None


def _get_sessions_for_role(role_value: int) -> list[AudioSession]:
    try:
        device_enumerator = comtypes.CoCreateInstance(
            CLSID_MMDeviceEnumerator,
            IMMDeviceEnumerator,
            comtypes.CLSCTX_INPROC_SERVER,
        )
        device = device_enumerator.GetDefaultAudioEndpoint(EDataFlow.eRender.value, role_value)
        audio_device = AudioUtilities.CreateDevice(device)
        enumerator = audio_device.AudioSessionManager.GetSessionEnumerator()
        sessions: list[AudioSession] = []
        for index in range(enumerator.GetCount()):
            ctl = enumerator.GetSession(index)
            if ctl is None:
                continue
            ctl2 = ctl.QueryInterface(IAudioSessionControl2)
            if ctl2 is not None:
                sessions.append(AudioSession(ctl2))
        return sessions
    except Exception:
        return []


def _get_cached_target(cache_key: str, resolver):
    cached = _cached_targets[cache_key]
    if cached is not _UNSET:
        return cached

    resolved = resolver()
    _cached_targets[cache_key] = resolved
    return resolved


def _get_valorant_volume_bindings() -> tuple[_SessionBinding, ...]:
    def _resolve():
        bindings: list[_SessionBinding] = []
        try:
            for session in AudioUtilities.GetAllSessions():
                if _is_valorant_audio_process(session):
                    binding = _binding_from_session(session)
                    if binding is not None:
                        bindings.append(binding)
        except Exception:
            return tuple()
        return tuple(bindings)

    return _get_cached_target(MUTE_TARGET_BOTH, _resolve)


def _get_valorant_role_binding(cache_key: str, role_value: int) -> _SessionBinding | None:
    def _resolve():
        for session in _get_sessions_for_role(role_value):
            if _is_valorant_audio_process(session):
                return _binding_from_session(session)
        return None

    return _get_cached_target(cache_key, _resolve)


def _get_bindings_for_target(target: str) -> tuple[_SessionBinding, ...]:
    if target == MUTE_TARGET_BOTH:
        return _get_valorant_volume_bindings()
    if target == MUTE_TARGET_DEFAULT:
        binding = _get_valorant_role_binding(MUTE_TARGET_DEFAULT, ERole.eMultimedia.value)
        return (binding,) if binding is not None else tuple()
    if target == MUTE_TARGET_COMMS:
        binding = _get_valorant_role_binding(MUTE_TARGET_COMMS, ERole.eCommunications.value)
        return (binding,) if binding is not None else tuple()
    return tuple()


def _apply_binding_plan(target: str, mute: bool) -> bool:
    desired_states: dict[str, tuple[object, bool]] = {}
    required_keys: set[str] = set()

    def _stage(binding_target: str, desired_mute: bool, required: bool):
        bindings = _get_bindings_for_target(binding_target)
        if not bindings:
            return not required
        for binding in bindings:
            if not required and binding.key in required_keys:
                continue
            desired_states[binding.key] = (binding.volume, desired_mute)
            if required:
                required_keys.add(binding.key)
        return True

    if target == MUTE_TARGET_BOTH:
        if not _stage(MUTE_TARGET_BOTH, mute, required=True):
            return False
        _stage(MUTE_TARGET_DEFAULT, False, required=False)
        _stage(MUTE_TARGET_COMMS, False, required=False)
    elif target == MUTE_TARGET_DEFAULT:
        if not _stage(MUTE_TARGET_DEFAULT, mute, required=True):
            return False
        _stage(MUTE_TARGET_BOTH, False, required=False)
        _stage(MUTE_TARGET_COMMS, False, required=False)
    elif target == MUTE_TARGET_COMMS:
        if not _stage(MUTE_TARGET_COMMS, mute, required=True):
            return False
        _stage(MUTE_TARGET_BOTH, False, required=False)
        _stage(MUTE_TARGET_DEFAULT, False, required=False)
    else:
        return False

    for key, (volume, desired_mute) in desired_states.items():
        try:
            volume.SetMute(1 if desired_mute else 0, None)
        except Exception:
            if key in required_keys:
                return False
    return True


def reset_audio_session_cache():
    for cache_key in _cached_targets:
        _cached_targets[cache_key] = _UNSET


def mute_valorant_target(target: str, mute: bool = True) -> bool:
    """Mute a specific VALORANT audio target and clear the other mute paths."""
    if not AUDIO_AVAILABLE:
        return False

    normalized_target = target if target in _cached_targets else MUTE_TARGET_BOTH
    if _apply_binding_plan(normalized_target, mute):
        return True

    reset_audio_session_cache()
    return _apply_binding_plan(normalized_target, mute)


def mute_valorant(mute: bool = True) -> bool:
    """Mute or unmute the VALORANT audio session in the Windows volume mixer."""
    return mute_valorant_target(MUTE_TARGET_BOTH, mute)
