import datetime as dt
import importlib.util
import pathlib
import sys
import unittest


SCRIPT_PATH = pathlib.Path(__file__).resolve().parents[1] / "ops" / "scripts" / "github_hot_monitor.py"
SPEC = importlib.util.spec_from_file_location("github_hot_monitor", SCRIPT_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC is not None and SPEC.loader is not None
sys.modules["github_hot_monitor"] = MODULE
SPEC.loader.exec_module(MODULE)


class HotMonitorTests(unittest.TestCase):
    def test_days_between_positive(self):
        start = "2026-03-01T00:00:00+00:00"
        end = "2026-03-03T00:00:00+00:00"
        self.assertEqual(MODULE.days_between(start, end), 2.0)

    def test_velocity_with_previous_snapshot(self):
        current = MODULE.RepoSnapshot(
            full_name="a/b",
            html_url="https://github.com/a/b",
            description="",
            language="Python",
            stars=120,
            forks=10,
            open_issues=2,
            watchers=5,
            created_at="2026-02-01T00:00:00Z",
            updated_at="2026-03-03T00:00:00Z",
            pushed_at="2026-03-03T00:00:00Z",
            topics=[],
            archived=False,
        )
        previous = MODULE.RepoSnapshot(
            full_name="a/b",
            html_url="https://github.com/a/b",
            description="",
            language="Python",
            stars=100,
            forks=9,
            open_issues=1,
            watchers=4,
            created_at="2026-02-01T00:00:00Z",
            updated_at="2026-03-02T00:00:00Z",
            pushed_at="2026-03-02T00:00:00Z",
            topics=[],
            archived=False,
        )
        self.assertEqual(MODULE.velocity_stars_per_day(current, previous, 2.0), 10.0)

    def test_weighted_total_range(self):
        score = MODULE.weighted_total(interesting=95.0, advanced=85.0, productive=90.0)
        self.assertGreaterEqual(score, 0.0)
        self.assertLessEqual(score, 100.0)

    def test_productivity_score_recent_repo_higher(self):
        now = dt.datetime(2026, 3, 4, tzinfo=dt.timezone.utc)
        active = MODULE.RepoSnapshot(
            full_name="x/active",
            html_url="https://github.com/x/active",
            description="",
            language="Go",
            stars=1000,
            forks=120,
            open_issues=25,
            watchers=30,
            created_at="2025-12-01T00:00:00Z",
            updated_at="2026-03-03T00:00:00Z",
            pushed_at="2026-03-03T00:00:00Z",
            topics=[],
            archived=False,
        )
        stale = MODULE.RepoSnapshot(
            full_name="x/stale",
            html_url="https://github.com/x/stale",
            description="",
            language="Go",
            stars=1000,
            forks=120,
            open_issues=25,
            watchers=30,
            created_at="2025-12-01T00:00:00Z",
            updated_at="2025-12-03T00:00:00Z",
            pushed_at="2025-12-03T00:00:00Z",
            topics=[],
            archived=False,
        )
        self.assertGreater(MODULE.productivity_score(active, now), MODULE.productivity_score(stale, now))

if __name__ == "__main__":
    unittest.main()
