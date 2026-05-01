"""키 코드 표시 매핑 테스트."""
from key_display import scancode_to_name, name_to_scancode


class TestScancodeMapping:
    def test_digit_keys_map_to_digits(self):
        assert scancode_to_name(0x02) == "1"
        assert scancode_to_name(0x0B) == "0"

    def test_function_keys(self):
        assert scancode_to_name(0x3B) == "F1"
        assert scancode_to_name(0x3F) == "F5"
        assert scancode_to_name(0x40) == "F6"

    def test_space_key(self):
        assert scancode_to_name(0x39) == "Space"

    def test_unknown_scancode_falls_back_to_hex(self):
        assert scancode_to_name(0xFF) == "0xFF"

    def test_name_to_scancode_basic(self):
        assert name_to_scancode("1") == 0x02
        assert name_to_scancode("F5") == 0x3F
        assert name_to_scancode("Space") == 0x39

    def test_name_to_scancode_case_insensitive(self):
        assert name_to_scancode("f5") == 0x3F
        assert name_to_scancode("space") == 0x39
        assert name_to_scancode("SPACE") == 0x39

    def test_name_to_scancode_unknown(self):
        assert name_to_scancode("xyz") == 0
        assert name_to_scancode("") == 0
