"""Hotkey parsing and polling helpers for Decypher."""

DEFAULT_HOTKEYS = {
    "hide_show": "F2",
    "click_through": "F3",
    "mute_on_death": "F4",
    "manual_mute": "F5",
}

HOTKEY_ACTIONS = (
    ("hide_show", "Hide/Show"),
    ("click_through", "Click-through"),
    ("mute_on_death", "Auto-Mute"),
    ("manual_mute", "Manual Mute"),
)

MODIFIER_ORDER = ("CTRL", "ALT", "SHIFT")
MODIFIER_VK = {
    "CTRL": 0x11,
    "ALT": 0x12,
    "SHIFT": 0x10,
}

KEY_ALIASES = {
    "CONTROL": "CTRL",
    "CONTROL_L": "CTRL",
    "CONTROL_R": "CTRL",
    "CTRL_L": "CTRL",
    "CTRL_R": "CTRL",
    "ALT_L": "ALT",
    "ALT_R": "ALT",
    "SHIFT_L": "SHIFT",
    "SHIFT_R": "SHIFT",
    "ESCAPE": "ESC",
    "RETURN": "ENTER",
    "PRIOR": "PAGEUP",
    "NEXT": "PAGEDOWN",
    "PGUP": "PAGEUP",
    "PGDN": "PAGEDOWN",
    "DEL": "DELETE",
    "INS": "INSERT",
    "EQUALS": "EQUAL",
    "QUOTE": "APOSTROPHE",
    "BRACKETLEFT": "LBRACKET",
    "BRACKETRIGHT": "RBRACKET",
    " ": "SPACE",
}

KEY_NAME_TO_VK = {
    **{f"F{index}": 0x70 + index - 1 for index in range(1, 25)},
    **{chr(code): code for code in range(ord("A"), ord("Z") + 1)},
    **{str(index): 0x30 + index for index in range(10)},
    "SPACE": 0x20,
    "TAB": 0x09,
    "ENTER": 0x0D,
    "BACKSPACE": 0x08,
    "INSERT": 0x2D,
    "DELETE": 0x2E,
    "HOME": 0x24,
    "END": 0x23,
    "PAGEUP": 0x21,
    "PAGEDOWN": 0x22,
    "LEFT": 0x25,
    "UP": 0x26,
    "RIGHT": 0x27,
    "DOWN": 0x28,
    "CAPSLOCK": 0x14,
    "NUMLOCK": 0x90,
    "SCROLLLOCK": 0x91,
    "PAUSE": 0x13,
    "PRINTSCREEN": 0x2C,
    "SEMICOLON": 0xBA,
    "EQUAL": 0xBB,
    "COMMA": 0xBC,
    "MINUS": 0xBD,
    "PERIOD": 0xBE,
    "SLASH": 0xBF,
    "GRAVE": 0xC0,
    "LBRACKET": 0xDB,
    "BACKSLASH": 0xDC,
    "RBRACKET": 0xDD,
    "APOSTROPHE": 0xDE,
    "NUMPAD0": 0x60,
    "NUMPAD1": 0x61,
    "NUMPAD2": 0x62,
    "NUMPAD3": 0x63,
    "NUMPAD4": 0x64,
    "NUMPAD5": 0x65,
    "NUMPAD6": 0x66,
    "NUMPAD7": 0x67,
    "NUMPAD8": 0x68,
    "NUMPAD9": 0x69,
}


def clean_key_name(key):
    key = str(key or "").strip().upper().replace("<", "").replace(">", "")
    key = key.replace("-", "+")
    return KEY_ALIASES.get(key, key)


def parse_hotkey(value):
    raw_parts = [part for part in str(value or "").replace(" ", "").split("+") if part]
    if not raw_parts:
        return None

    modifiers = []
    main_key = None
    for raw_part in raw_parts:
        key = clean_key_name(raw_part)
        if key in MODIFIER_VK:
            if key not in modifiers:
                modifiers.append(key)
            continue
        if key == "ESC" or key not in KEY_NAME_TO_VK or main_key is not None:
            return None
        main_key = key

    if main_key is None:
        return None

    ordered_modifiers = [modifier for modifier in MODIFIER_ORDER if modifier in modifiers]
    return ordered_modifiers, main_key


def format_hotkey(value):
    parsed = parse_hotkey(value)
    if not parsed:
        return None
    modifiers, main_key = parsed
    return "+".join([*modifiers, main_key])


def normalize_hotkey(value, fallback):
    return format_hotkey(value) or fallback


def event_to_hotkey(event):
    key = clean_key_name(event.keysym)
    if key == "ESC":
        return "ESC"
    if key in MODIFIER_VK:
        return None
    if key.startswith("KP_"):
        keypad_key = key[3:]
        if keypad_key.isdigit():
            key = f"NUMPAD{keypad_key}"
    if key not in KEY_NAME_TO_VK:
        char = clean_key_name(getattr(event, "char", ""))
        if len(char) == 1 and char.isalnum():
            key = char
        else:
            return None

    modifiers = []
    state = int(getattr(event, "state", 0))
    if state & 0x4:
        modifiers.append("CTRL")
    if state & 0x20000 or state & 0x8:
        modifiers.append("ALT")
    if state & 0x1:
        modifiers.append("SHIFT")
    return "+".join([*modifiers, key])


def hotkey_is_pressed(hotkey, user32_local):
    parsed = parse_hotkey(hotkey)
    if not parsed:
        return False
    modifiers, main_key = parsed
    for modifier in modifiers:
        if not user32_local.GetAsyncKeyState(MODIFIER_VK[modifier]) & 0x8000:
            return False
    return bool(user32_local.GetAsyncKeyState(KEY_NAME_TO_VK[main_key]) & 0x8000)
