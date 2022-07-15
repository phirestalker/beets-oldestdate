import unittest
from dateutil import parser

import oldestdate


class DateWrapperTest(unittest.TestCase):
    def test_creating_date(self):
        result = oldestdate.DateWrapper(2022, 12, 10)
        self.assertEqual(2022, result.y)
        self.assertEqual(12, result.m)
        self.assertEqual(10, result.d)

    def test_less_than_year(self):
        first_date = oldestdate.DateWrapper(2021, 12, 10)
        second_date = oldestdate.DateWrapper(2022, 12, 10)
        self.assertTrue(first_date < second_date)

    def test_less_than_month(self):
        first_date = oldestdate.DateWrapper(2022, 11, 10)
        second_date = oldestdate.DateWrapper(2022, 12, 10)
        self.assertTrue(first_date < second_date)

    def test_less_than_day(self):
        first_date = oldestdate.DateWrapper(2022, 12, 9)
        second_date = oldestdate.DateWrapper(2022, 12, 10)
        self.assertTrue(first_date < second_date)

    # If a value is None, that date should be bigger
    # This means when testing for oldest (smallest) the one with values gets picked
    def test_less_than_none_month(self):
        first_date = oldestdate.DateWrapper(2022, None, 9)
        second_date = oldestdate.DateWrapper(2022, 12, 10)
        self.assertFalse(first_date < second_date)

    def test_less_than_none_day(self):
        first_date = oldestdate.DateWrapper(2022, 12, None)
        second_date = oldestdate.DateWrapper(2022, 12, 10)
        self.assertFalse(first_date < second_date)

    def test_less_than_none_month_day(self):
        first_date = oldestdate.DateWrapper(2022, None, None)
        second_date = oldestdate.DateWrapper(2022, 1, 1)
        self.assertFalse(first_date < second_date)

    def test_less_than_none_month_backwards(self):
        first_date = oldestdate.DateWrapper(2022, 12, 9)
        second_date = oldestdate.DateWrapper(2022, None, 10)
        self.assertTrue(first_date < second_date)

    def test_less_than_none_day_backwards(self):
        first_date = oldestdate.DateWrapper(2022, 12, 10)
        second_date = oldestdate.DateWrapper(2022, 12, None)
        self.assertTrue(first_date < second_date)

    def test_less_than_none_month_day_backwards(self):
        first_date = oldestdate.DateWrapper(2022, 1, 1)
        second_date = oldestdate.DateWrapper(2022, None, None)
        self.assertTrue(first_date < second_date)

    def test_equal(self):
        first_date = oldestdate.DateWrapper(2022, 12, 10)
        second_date = oldestdate.DateWrapper(2022, 12, 10)
        self.assertEqual(first_date, first_date)
        self.assertEqual(first_date, second_date)

    def test_equal_none_month(self):
        first_date = oldestdate.DateWrapper(2022, None, 10)
        second_date = oldestdate.DateWrapper(2022, 12, 10)
        self.assertNotEqual(first_date, second_date)

    def test_equal_none_month_backwards(self):
        first_date = oldestdate.DateWrapper(2022, 12, 10)
        second_date = oldestdate.DateWrapper(2022, None, 10)
        self.assertNotEqual(first_date, second_date)

    def test_equal_none_months(self):
        first_date = oldestdate.DateWrapper(2022, None, 10)
        second_date = oldestdate.DateWrapper(2022, None, 10)
        self.assertTrue(first_date == second_date)

    def test_equal_none_day(self):
        first_date = oldestdate.DateWrapper(2022, 12, None)
        second_date = oldestdate.DateWrapper(2022, 12, 10)
        self.assertNotEqual(first_date, second_date)

    def test_equal_none_day_backwards(self):
        first_date = oldestdate.DateWrapper(2022, 12, 10)
        second_date = oldestdate.DateWrapper(2022, 12, None)
        self.assertNotEqual(first_date, second_date)

    def test_equal_none_days(self):
        first_date = oldestdate.DateWrapper(2022, 12, None)
        second_date = oldestdate.DateWrapper(2022, 12, None)
        self.assertTrue(first_date == second_date)


class OldestDatePluginTest(unittest.TestCase):
    @classmethod
    def setUpClass(self):
        self.oldestdateplugin = oldestdate.OldestDatePlugin()

    def test_get_work_id_from_recording(self):
        test_recording = {"work-relation-list": [{"work": {"id": 20}}]}
        result = oldestdate._get_work_id_from_recording(test_recording)
        self.assertEqual(20, result)

    def test_extract_oldest_recording_date(self):
        recordings = [{"recording": {"id": 20}, "begin": "2020-12-12"}]
        starting_date = parser.isoparse("20221010").date()
        expected_date = parser.isoparse("20201212").date()
        is_cover = False
        approach = "recordings"
        result = self.oldestdateplugin._extract_oldest_recording_date(recordings, starting_date, is_cover, approach)
        self.assertEqual(expected_date, result)

    def test_extract_oldest_recording_date_with_only_year(self):
        recordings = [{"recording": {"id": 20}, "begin": "1978"}]
        starting_date = parser.isoparse("20221010").date()
        expected_date = parser.isoparse("19780101").date()
        is_cover = False
        approach = "recordings"
        result = self.oldestdateplugin._extract_oldest_recording_date(recordings, starting_date, is_cover, approach)
        self.assertEqual(expected_date, result)


if __name__ == '__main__':
    unittest.main()
