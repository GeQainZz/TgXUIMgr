import unittest

from main import _format_daily_report_text


class DailyReportFormattingTests(unittest.TestCase):
    def test_users_are_grouped_and_limited_per_panel(self):
        panel_users = {
            "BIGGERBOX-PRO": [
                {"email": f"big-{i}", "total_usage": (20 - i) * 1024**3}
                for i in range(11)
            ],
            "DMIT-MALIBU": [
                {"email": "same-user", "total_usage": 7 * 1024**3},
            ],
        }
        text = _format_daily_report_text(
            "2026-08-15",
            [{"total_upload": 2 * 1024**3, "total_download": 8 * 1024**3}],
            [
                {"panel_name": "BIGGERBOX-PRO", "daily_total": 6 * 1024**3},
                {"panel_name": "DMIT-MALIBU", "daily_total": 4 * 1024**3},
            ],
            panel_users,
        )

        self.assertIn("BIGGERBOX-PRO 用户用量 Top 10", text)
        self.assertIn("DMIT-MALIBU 用户用量 Top 10", text)
        self.assertIn("1. big-0 (BIGGERBOX-PRO)", text)
        self.assertIn("1. same-user (DMIT-MALIBU)", text)
        self.assertNotIn("11. big-10", text)
        self.assertNotIn("**Top 10 用户:**", text)


if __name__ == "__main__":
    unittest.main()
