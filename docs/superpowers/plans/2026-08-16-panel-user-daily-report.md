# Panel User Daily Report Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Change the Telegram daily traffic report from one global Top 10 list to a per-panel Top 10 user breakdown.

**Architecture:** Keep database queries unchanged. The report generator will query `get_top_users` once per panel and pass a panel-keyed result to a pure formatter; both the scheduled job and `/report` command continue using the same generator.

**Tech Stack:** Python 3.9, python-telegram-bot, SQLite query helpers, unittest.

## Global Constraints

- Do not include configuration, tokens, panel credentials, database files, or backups in the commit.
- Keep the existing Markdown message style and total/panel summary fields.
- Show at most 10 users per panel.

---

### Task 1: Add a failing regression test

**Files:**
- Create: `tests/test_daily_report.py`

**Interfaces:**
- Consumes: `_format_daily_report_text(report_date, stats, panel_stats, top_users_by_panel)` from `main.py`.
- Produces: assertions covering per-panel grouping, independent same-name users, and the 10-user cap.

- [ ] **Step 1: Write the failing test**

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker cp tests/test_daily_report.py xui-tgbot:/tmp/test_daily_report.py && docker exec xui-tgbot python -m unittest /tmp/test_daily_report.py`

Expected: FAIL because `_format_daily_report_text` does not exist yet.

### Task 2: Implement grouped report formatting

**Files:**
- Modify: `main.py:457-489`
- Test: `tests/test_daily_report.py`

**Interfaces:**
- Consumes: `get_panel_daily_stats`, `get_top_users`, and existing byte formatter.
- Produces: `_format_daily_report_text(...)` and a report generator that queries each panel separately.

- [ ] **Step 1: Add `_format_daily_report_text` and call it from `_generate_daily_report_text`**

The formatter must emit the existing summary, each panel total, then for every panel emit up to 10 entries from `top_users_by_panel[panel_name]`. The generator must call `get_top_users(yesterday, yesterday, panel_name=panel_name, limit=10)` for every panel in `panel_stats` and pass the result to the formatter.

- [ ] **Step 2: Run the focused test**

Run: `docker cp tests/test_daily_report.py xui-tgbot:/tmp/test_daily_report.py && docker exec xui-tgbot python -m unittest /tmp/test_daily_report.py`

Expected: PASS.

- [ ] **Step 3: Run syntax and service checks**

Run: `python3 -m py_compile main.py` and `docker logs --tail 30 xui-tgbot`.

Expected: compilation succeeds and the application starts without traceback.

### Task 3: Deploy and send a live example

**Files:**
- Deploy: `main.py`

- [ ] **Step 1: Back up the current remote file**

Run: `cp /data/TgXUIMgr/main.py /data/TgXUIMgr/main.py.bak.panel-report`

- [ ] **Step 2: Rebuild and restart**

Run: `cd /data/TgXUIMgr && docker compose up -d --build`

- [ ] **Step 3: Generate and send an example**

Use `_generate_daily_report_text()` inside the container, prepend `🧪 测试示例（按面板拆分用户用量）`, and send through the configured Bot API to all configured admins. Verify Telegram returns HTTP 200 with `ok: true`.
