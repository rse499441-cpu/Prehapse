import unittest

from game.formatting import format_number


class NumberFormattingTests(unittest.TestCase):
    def test_visible_numbers_never_exceed_two_decimal_places(self):
        self.assertEqual(format_number(305.70000000000005), "305.7")
        self.assertEqual(format_number(12.3456), "12.35")
        self.assertEqual(format_number(900), "900")
        self.assertEqual(format_number(-0.126), "-0.13")


if __name__ == "__main__":
    unittest.main()
