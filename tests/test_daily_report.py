import asyncio
import unittest
from zoneinfo import ZoneInfo
from unittest.mock import patch

import main
from main import _format_daily_report_text, _generate_daily_report_text, _scheduled_time


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

    def test_scheduled_jobs_use_hong_kong_timezone(self):
        scheduled = _scheduled_time(8)

        self.assertEqual(scheduled.hour, 8)
        self.assertEqual(scheduled.tzinfo, ZoneInfo("Asia/Hong_Kong"))

    def test_missing_snapshot_is_not_reported_as_zero_usage(self):
        text = _format_daily_report_text("2026-08-15", [], [], {})

        self.assertIn("当日数据暂不可用", text)
        self.assertIn("前一日流量快照缺失", text)
        self.assertNotIn("总用量", text)

    @patch("main.has_traffic_snapshot", side_effect=[True, False])
    @patch("main.get_daily_stats")
    def test_report_requires_a_snapshot_for_the_prior_day(self, daily_stats, _snapshots):
        text = asyncio.run(_generate_daily_report_text())

        self.assertIn("当日数据暂不可用", text)
        daily_stats.assert_not_called()


if __name__ == "__main__":
    unittest.main()
