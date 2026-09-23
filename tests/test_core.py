import unittest

from ak820_core import parse_device_line, parse_info


class ParseInfoTests(unittest.TestCase):
    def test_parses_bluez_info(self):
        info = parse_info("""
Device 12:E8:06:24:02:5D (public)
    Name: AK820 MAX5.0
    Paired: yes
    Trusted: yes
    Connected: yes
""")
        self.assertEqual(info["Name"], "AK820 MAX5.0")
        self.assertEqual(info["Paired"], "yes")
        self.assertEqual(info["Trusted"], "yes")
        self.assertEqual(info["Connected"], "yes")

    def test_values_may_contain_colons(self):
        info = parse_info("Alias: keyboard:desk")
        self.assertEqual(info["Alias"], "keyboard:desk")


class DeviceLineTests(unittest.TestCase):
    def test_valid_device(self):
        self.assertEqual(
            parse_device_line("Device 12:e8:06:24:02:5d AK820 MAX5.0"),
            ("12:E8:06:24:02:5D", "AK820 MAX5.0"),
        )

    def test_invalid_device(self):
        self.assertIsNone(parse_device_line("not a bluetooth device"))


if __name__ == "__main__":
    unittest.main()
