"""Common delay units and fractions. Rules parse only. No account. No cloud."""

from __future__ import annotations

import unittest

from battlebuddy.reminders.parse import (
    is_clear_all,
    is_list_command,
    parse_clear,
    parse_reminder,
    parse_snooze,
)


class CommonDelayParseTest(unittest.TestCase):
    def test_existing_one_minute_line(self) -> None:
        spoken = parse_reminder("Remind me in one minute to check food stores")
        digit = parse_reminder("remind me in 1 minute to check food stores")
        assert spoken is not None
        assert digit is not None
        self.assertEqual(spoken.text, "check food stores")
        self.assertEqual(spoken.delay_seconds, 60)
        self.assertEqual(spoken.delay_seconds, digit.delay_seconds)
        self.assertEqual(spoken.amount, 1)

    def test_one_and_a_half_minutes(self) -> None:
        parsed = parse_reminder(
            "Remind me in one and a half minutes to check my food stores."
        )
        assert parsed is not None
        self.assertEqual(parsed.text, "check my food stores")
        self.assertEqual(parsed.delay_seconds, 90)
        self.assertEqual(parsed.amount, 1.5)

    def test_ninety_seconds(self) -> None:
        digit = parse_reminder("remind me in 90 seconds to check food stores")
        spoken = parse_reminder("remind me in ninety seconds to check food stores")
        assert digit is not None
        assert spoken is not None
        self.assertEqual(digit.text, "check food stores")
        self.assertEqual(digit.delay_seconds, 90)
        self.assertEqual(spoken.delay_seconds, 90)

    def test_half_a_minute(self) -> None:
        parsed = parse_reminder("remind me in half a minute to check food stores")
        assert parsed is not None
        self.assertEqual(parsed.text, "check food stores")
        self.assertEqual(parsed.delay_seconds, 30)

    def test_two_hours(self) -> None:
        parsed = parse_reminder("remind me in 2 hours to check food stores")
        spoken = parse_reminder("remind me in two hours to check food stores")
        assert parsed is not None
        assert spoken is not None
        self.assertEqual(parsed.delay_seconds, 7200)
        self.assertEqual(spoken.delay_seconds, 7200)

    def test_one_day(self) -> None:
        parsed = parse_reminder("remind me in 1 day to check food stores")
        assert parsed is not None
        self.assertEqual(parsed.text, "check food stores")
        self.assertEqual(parsed.delay_seconds, 86400)

    def test_hour_and_a_half_decimal_and_weeks(self) -> None:
        hour_half = parse_reminder("remind me in an hour and a half to scout north")
        decimal = parse_reminder("remind me in 1.5 minutes to check food stores")
        quarter = parse_reminder("in a quarter hour check the north gate")
        weeks = parse_reminder("check food stores in 2 weeks")
        assert hour_half is not None
        assert decimal is not None
        assert quarter is not None
        assert weeks is not None
        self.assertEqual(hour_half.delay_seconds, 5400)
        self.assertEqual(decimal.delay_seconds, 90)
        self.assertEqual(quarter.delay_seconds, 900)
        self.assertEqual(quarter.text, "check the north gate")
        self.assertEqual(weeks.delay_seconds, 14 * 86400)
        self.assertEqual(weeks.text, "check food stores")

    def test_task_plus_delay_and_wispr_still_work(self) -> None:
        task = parse_reminder("check my food stores in one and a half minutes")
        wispr = parse_reminder(
            "I need to check my food stores in one and a half minutes"
        )
        assert task is not None
        assert wispr is not None
        self.assertEqual(task.delay_seconds, 90)
        self.assertEqual(task.text, "check my food stores")
        self.assertEqual(wispr.text, "check my food stores")
        self.assertEqual(wispr.delay_seconds, 90)

    def test_snooze_uses_same_amount_parser(self) -> None:
        snooze = parse_snooze("Snooze food stores one and a half minutes")
        assert snooze is not None
        self.assertEqual(snooze.query, "food stores")
        self.assertEqual(snooze.delay_seconds, 90)
        half = parse_snooze("snooze food stores for 90 seconds")
        assert half is not None
        self.assertEqual(half.delay_seconds, 90)

    def test_list_snooze_clear_are_not_reminders(self) -> None:
        self.assertTrue(is_list_command("list my reminders"))
        self.assertTrue(is_clear_all("clear all"))
        self.assertIsNone(parse_reminder("list my reminders"))
        self.assertIsNone(parse_reminder("snooze food stores 5 minutes"))
        self.assertIsNone(parse_reminder("clear reminder about mines"))
        self.assertIsNone(parse_reminder("clear all"))
        self.assertEqual(parse_clear("clear reminder about mines"), "mines")

    def test_no_delay_stays_unparsed(self) -> None:
        self.assertIsNone(parse_reminder("check wood"))
        self.assertIsNone(parse_reminder("I need to check wood"))
        self.assertIsNone(parse_reminder("Remind me to check my food stores"))


if __name__ == "__main__":
    unittest.main()
