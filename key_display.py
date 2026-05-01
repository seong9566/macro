"""스캔코드 ↔ 사용자 친화적 키 이름 변환."""

# Windows scancode → 사용자 친화적 이름
_SCANCODE_TO_NAME = {
    0x01: "Esc",
    0x02: "1", 0x03: "2", 0x04: "3", 0x05: "4", 0x06: "5",
    0x07: "6", 0x08: "7", 0x09: "8", 0x0A: "9", 0x0B: "0",
    0x0C: "-", 0x0D: "=",
    0x0E: "Backspace", 0x0F: "Tab",
    0x10: "Q", 0x11: "W", 0x12: "E", 0x13: "R", 0x14: "T",
    0x15: "Y", 0x16: "U", 0x17: "I", 0x18: "O", 0x19: "P",
    0x1A: "[", 0x1B: "]",
    0x1C: "Enter", 0x1D: "Ctrl",
    0x1E: "A", 0x1F: "S", 0x20: "D", 0x21: "F", 0x22: "G",
    0x23: "H", 0x24: "J", 0x25: "K", 0x26: "L",
    0x27: ";", 0x28: "'", 0x29: "`", 0x2A: "Shift",
    0x2B: "\\",
    0x2C: "Z", 0x2D: "X", 0x2E: "C", 0x2F: "V", 0x30: "B",
    0x31: "N", 0x32: "M",
    0x33: ",", 0x34: ".", 0x35: "/", 0x36: "Shift(R)",
    0x37: "* (Numpad)", 0x38: "Alt", 0x39: "Space",
    0x3A: "CapsLock",
    0x3B: "F1", 0x3C: "F2", 0x3D: "F3", 0x3E: "F4",
    0x3F: "F5", 0x40: "F6", 0x41: "F7", 0x42: "F8",
    0x43: "F9", 0x44: "F10",
    0x57: "F11", 0x58: "F12",
}

# 역방향 (이름 → 스캔코드)
_NAME_TO_SCANCODE = {v: k for k, v in _SCANCODE_TO_NAME.items()}
# 대소문자 무관 입력 지원
_NAME_TO_SCANCODE_CI = {k.upper(): v for k, v in _NAME_TO_SCANCODE.items()}


def scancode_to_name(scan: int) -> str:
    """스캔코드를 사용자 친화적 이름으로. 알 수 없으면 hex 표시."""
    if scan in _SCANCODE_TO_NAME:
        return _SCANCODE_TO_NAME[scan]
    return f"0x{scan:02X}"


def name_to_scancode(name: str) -> int:
    """사용자 친화적 이름(예: '1', 'F5', 'Space')을 스캔코드로. 모르면 0."""
    if not name:
        return 0
    return _NAME_TO_SCANCODE_CI.get(name.strip().upper(), 0)
