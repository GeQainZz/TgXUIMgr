import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

import webapp


class AdminStatsDateRangeTests(unittest.TestCase):
    def test_date_range_uses_selected_day(self):
        self.assertEqual(
            webapp._date_range_for("day", date(2026, 8, 14)),
            ("2026-08-14", "2026-08-14"),
        )

    def test_date_range_uses_calendar_week_containing_selected_day(self):
        self.assertEqual(
            webapp._date_range_for("week", date(2026, 8, 14)),
            ("2026-08-10", "2026-08-16"),
        )

    def test_date_range_uses_calendar_month_containing_selected_day(self):
        self.assertEqual(
            webapp._date_range_for("month", date(2026, 8, 14)),
            ("2026-08-01", "2026-08-31"),
        )


class AdminStatsEndpointTests(unittest.TestCase):
    def setUp(self):
        webapp.app.config.update(TESTING=True, SECRET_KEY="test-secret")
        self.client = webapp.app.test_client()
        with self.client.session_transaction() as session:
            session["is_admin"] = True

    @patch("webapp.get_top_users", return_value=[])
    @patch("webapp.get_panel_daily_stats", return_value=[])
    @patch("webapp.get_daily_stats", return_value=[])
    @patch("webapp.get_date_range", return_value=("2026-08-11", "2026-08-14"))
    def test_defaults_to_latest_available_date(self, *_mocks):
        response = self.client.get("/api/admin/stats/day")

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(payload["selected_date"], "2026-08-14")
        self.assertEqual((payload["start"], payload["end"]), ("2026-08-14", "2026-08-14"))
        self.assertEqual(
            payload["available_range"],
            {"start": "2026-08-11", "end": "2026-08-14"},
        )

    @patch("webapp.get_top_users", return_value=[])
    @patch("webapp.get_panel_daily_stats", return_value=[])
    @patch("webapp.get_daily_stats", return_value=[])
    @patch("webapp.get_date_range", return_value=("2026-08-11", "2026-08-14"))
    def test_accepts_selected_date_for_week(self, _range, daily, panel_daily, top):
        response = self.client.get("/api/admin/stats/week?date=2026-08-12")

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual((payload["start"], payload["end"]), ("2026-08-10", "2026-08-16"))
        daily.assert_called_once_with("2026-08-10", "2026-08-16")
        panel_daily.assert_called_once_with("2026-08-10", "2026-08-16")
        top.assert_called_once_with("2026-08-10", "2026-08-16", limit=20)

    @patch("webapp.get_top_users", return_value=[])
    @patch("webapp.get_panel_daily_stats", return_value=[])
    @patch("webapp.get_daily_stats", return_value=[])
    @patch("webapp.get_date_range", return_value=("2026-08-11", "2026-08-14"))
    def test_filters_top_users_by_selected_panel(self, _range, daily, panel_daily, top):
        response = self.client.get(
            "/api/admin/stats/day?date=2026-08-14&panel=BIGGERBOX-PRO"
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["selected_panel"], "BIGGERBOX-PRO")
        top.assert_called_once_with(
            "2026-08-14", "2026-08-14", panel_name="BIGGERBOX-PRO", limit=20
        )

    def test_rejects_malformed_date(self):
        response = self.client.get("/api/admin/stats/month?date=2026-13-40")

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.get_json()["error"], "日期格式无效，请使用 YYYY-MM-DD")

    def test_rejects_unknown_period(self):
        response = self.client.get("/api/admin/stats/year?date=2026-08-14")

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.get_json()["error"], "统计周期无效")


class AdminStatsTemplateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = (
            Path(__file__).resolve().parents[1] / "templates" / "admin.html"
        ).read_text(encoding="utf-8")

    def test_stats_toolbar_has_date_and_period_navigation(self):
        self.assertIn('id="stats-date"', self.html)
        self.assertIn('id="stats-prev"', self.html)
        self.assertIn('id="stats-next"', self.html)
        self.assertIn('id="stats-range-label"', self.html)

    def test_stats_request_includes_selected_date(self):
        self.assertIn("params.set('date', statsSelectedDate)", self.html)

    def test_stats_view_has_empty_state(self):
        self.assertIn('id="stats-empty"', self.html)

    def test_stats_view_removes_daily_trend_and_clicks_panel_chart(self):
        self.assertNotIn('id="chart-stats-trend"', self.html)
        self.assertIn("params.set('panel', selectedStatsPanel)", self.html)
        self.assertIn("onClick: (event, elements)", self.html)

    def test_admin_layout_has_responsive_operations_shell(self):
        for marker in (
            'class="logo-mark"',
            'class="sidebar-foot"',
            'class="page-heading"',
            'class="system-status"',
            'class="section-intro"',
            'table-card',
            'prefers-reduced-motion',
        ):
            self.assertIn(marker, self.html)


if __name__ == "__main__":
    unittest.main()
