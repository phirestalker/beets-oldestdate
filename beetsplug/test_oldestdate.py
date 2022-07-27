import datetime
import unittest
import oldestdate


class DateWrapperTest(unittest.TestCase):
    def test_creating_date(self):
        result = oldestdate.DateWrapper(2022, 12, 10)
        self.assertEqual(2022, result.y)
        self.assertEqual(12, result.m)
        self.assertEqual(10, result.d)

    def test_invalid_date(self):
        result = oldestdate.DateWrapper(2022, 0, 10)
        self.assertEqual(2022, result.y)
        self.assertEqual(1, result.m)
        self.assertEqual(10, result.d)
        result = oldestdate.DateWrapper(2022, 10, 0)
        self.assertEqual(2022, result.y)
        self.assertEqual(10, result.m)
        self.assertEqual(1, result.d)

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

    def test_isostring(self):
        first_date = oldestdate.DateWrapper(iso_string="2022-12-10")
        second_date = oldestdate.DateWrapper(2022, 12, 10)
        self.assertTrue(first_date == second_date)

    def test_isostring_year_month(self):
        first_date = oldestdate.DateWrapper(iso_string="2022-12")
        second_date = oldestdate.DateWrapper(2022, 12)
        self.assertTrue(first_date == second_date)

    def test_isostring_year(self):
        first_date = oldestdate.DateWrapper(iso_string="2022")
        second_date = oldestdate.DateWrapper(2022)
        self.assertTrue(first_date == second_date)

    def test_isostring_empty(self):
        with self.assertRaises(ValueError):
            oldestdate.DateWrapper(iso_string="")

    def test_no_year_no_isostring(self):
        with self.assertRaises(TypeError):
            oldestdate.DateWrapper()

    def test_today(self):
        first_date = oldestdate.DateWrapper.today()
        today = datetime.datetime.today()
        second_date = oldestdate.DateWrapper(today.year, today.month, today.day)

        self.assertEqual(first_date, second_date)


class OldestDatePluginTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.oldestdateplugin = oldestdate.OldestDatePlugin()

    def setUp(self):
        self.recording_id = 20
        self.recording = {"recording": {"id": self.recording_id}, "begin": "1978", "release-list": [{"date": "1977"}]}
        self.recordings = [self.recording]
        self.is_cover = False
        self.approach = "recordings"

    # Test recordings approach

    def test_get_work_id_from_recording(self):
        test_recording = {"work-relation-list": [{"work": {"id": 20}}]}
        result = oldestdate._get_work_id_from_recording(test_recording)
        self.assertEqual(20, result)

    def test_extract_oldest_recording_date(self):
        recordings = [{"recording": {"id": 20}, "begin": "2020-12-12"}]
        starting_date = oldestdate.DateWrapper(iso_string="20221010")
        expected_date = oldestdate.DateWrapper(iso_string="20201212")
        result = self.oldestdateplugin._extract_oldest_recording_date(recordings, starting_date, self.is_cover,
                                                                      self.approach)
        self.assertEqual(expected_date, result)

    def test_extract_oldest_recording_date_with_only_year(self):
        recordings = [{"recording": {"id": 20}, "begin": "1978"}]
        starting_date = oldestdate.DateWrapper(2022, 10, 10)
        expected_date = oldestdate.DateWrapper(1978)
        result = self.oldestdateplugin._extract_oldest_recording_date(recordings, starting_date, self.is_cover,
                                                                      self.approach)
        self.assertEqual(expected_date, result)

    def test_extract_oldest_recording_date_cover(self):
        recordings = [{"recording": {"id": 20}, "begin": "1978", "attribute-list": ["cover"]},
                      {"recording": {"id": 20}, "begin": "1976"}]  # non-cover should be filtered out
        starting_date = oldestdate.DateWrapper(2022, 10, 10)
        expected_date = oldestdate.DateWrapper(1978)
        result = self.oldestdateplugin._extract_oldest_recording_date(recordings, starting_date, True, self.approach)
        self.assertEqual(expected_date, result)

    def test_extract_oldest_recording_date_non_cover(self):
        # cover should be filtered out
        recordings = [{"recording": {"id": 20}, "begin": "1976", "attribute-list": ["cover"]},
                      {"recording": {"id": 20}, "begin": "1978"}]
        starting_date = oldestdate.DateWrapper(2022, 10, 10)
        expected_date = oldestdate.DateWrapper(1978)
        result = self.oldestdateplugin._extract_oldest_recording_date(recordings, starting_date, False, self.approach)
        self.assertEqual(expected_date, result)

    # Test releases approach

    def test_extract_oldest_release_date(self):
        starting_date = oldestdate.DateWrapper(2022, 10, 10)
        expected_date = oldestdate.DateWrapper(1977)
        # Put recording into cache to avoid calling the API
        self.oldestdateplugin._recordings_cache[self.recording_id] = self.recording
        result = self.oldestdateplugin._extract_oldest_release_date([self.recording], starting_date, self.is_cover,
                                                                    "releases")
        self.assertEqual(expected_date, result)

    def test_extract_oldest_release_date_cover(self):
        recordings = [
            {"recording": {"id": self.recording_id}, "begin": "1978", "release-list": [{"date": "1976"}]},
            {"recording": {"id": self.recording_id + 1}, "begin": "1978", "attribute-list": ["cover"],
             "release-list": [{"date": "1977"}], "artist-credit": [{"artist": {"id": "artist-id"}}]}
        ]
        starting_date = oldestdate.DateWrapper(2022, 10, 10)
        expected_date = oldestdate.DateWrapper(1977)

        # Put recordings into cache to avoid calling the API
        for i in range(len(recordings)):
            self.oldestdateplugin._recordings_cache[self.recording_id + i] = recordings[i]

        result = self.oldestdateplugin._extract_oldest_release_date(recordings, starting_date, True, ["artist-id"])
        self.assertEqual(expected_date, result)

    def test_extract_oldest_release_date_non_cover(self):
        recordings = [
            {"recording": {"id": self.recording_id}, "begin": "1978", "release-list": [{"date": "1976"}]},
            {"recording": {"id": self.recording_id + 1}, "begin": "1978", "attribute-list": ["cover"],
             "release-list": [{"date": "1977"}], "artist-credit": [{"artist": {"id": "artist-id"}}]},
            {"recording": {"id": self.recording_id + 2}, "begin": "1978", "attribute-list": ["cover"],
             "release-list": [{"date": "1975"}], "artist-credit": [{"artist": {"id": "another-id"}}]}
        ]
        starting_date = oldestdate.DateWrapper(2022, 10, 10)
        expected_date = oldestdate.DateWrapper(1976)

        # Put recordings into cache to avoid calling the API
        for i in range(len(recordings)):
            self.oldestdateplugin._recordings_cache[self.recording_id + i] = recordings[i]

        result = self.oldestdateplugin._extract_oldest_release_date(recordings, starting_date, False, ["artist-id"])
        self.assertEqual(expected_date, result)

    def test_extract_oldest_release_date_filter_recordings(self):
        self.oldestdateplugin.config['filter_recordings'] = True
        recordings = [
            {"recording": {"id": self.recording_id}, "begin": "1978", "release-list": [{"date": "1976"}]},
            {"recording": {"id": self.recording_id + 1}, "begin": "1978", "attribute-list": ["live"],
             "release-list": [{"date": "1977"}], "artist-credit": [{"artist": {"id": "artist-id"}}]},
            {"recording": {"id": self.recording_id + 2}, "begin": "1978", "attribute-list": ["cover"],
             "release-list": [{"date": "1975"}], "artist-credit": [{"artist": {"id": "another-id"}}]}
        ]
        starting_date = oldestdate.DateWrapper(2022, 10, 10)
        expected_date = oldestdate.DateWrapper(1976)

        # Put recordings into cache to avoid calling the API
        for i in range(len(recordings)):
            self.oldestdateplugin._recordings_cache[self.recording_id + i] = recordings[i]

        result = self.oldestdateplugin._extract_oldest_release_date(recordings, starting_date, False, ["artist-id"])
        self.assertEqual(expected_date, result)
        self.oldestdateplugin.config['filter_recordings'] = False

    def test_extract_oldest_release_date_release_type(self):
        self.oldestdateplugin.config['release_types'] = ["Official"]
        recordings = [
            {"recording": {"id": self.recording_id}, "begin": "1978",
             "release-list": [{"date": "1976", "status": "Bootleg"}]},
            {"recording": {"id": self.recording_id + 1}, "begin": "1978", "attribute-list": ["live"],
             "release-list": [{"date": "1977", "status": "Official"}]},
            {"recording": {"id": self.recording_id + 2}, "begin": "1978", "attribute-list": ["cover"],
             "release-list": [{"date": "1975"}], "artist-credit": [{"artist": {"id": "another-id"}}]}
        ]
        starting_date = oldestdate.DateWrapper(2022, 10, 10)
        expected_date = oldestdate.DateWrapper(1977)

        # Put recordings into cache to avoid calling the API
        for i in range(len(recordings)):
            self.oldestdateplugin._recordings_cache[self.recording_id + i] = recordings[i]

        result = self.oldestdateplugin._extract_oldest_release_date(recordings, starting_date, False, ["artist-id"])
        self.assertEqual(expected_date, result)
        self.oldestdateplugin.config['release_types'] = None

    def test_iterate_dates_recordings(self):
        self.oldestdateplugin.config['approach'] = "recordings"
        recordings = [
            {"recording": {"id": self.recording_id}, "begin": "1978",
             "release-list": [{"date": "1976", "status": "Bootleg"}]},
            {"recording": {"id": self.recording_id + 1}, "begin": "1978", "attribute-list": ["live"],
             "release-list": [{"date": "1977", "status": "Official"}]},
            {"recording": {"id": self.recording_id + 2}, "begin": "1978", "attribute-list": ["cover"],
             "release-list": [{"date": "1975"}]}
        ]
        starting_date = oldestdate.DateWrapper(2022, 10, 10)
        expected_date = oldestdate.DateWrapper(1978)

        # Put recordings into cache to avoid calling the API
        for i in range(len(recordings)):
            self.oldestdateplugin._recordings_cache[self.recording_id + i] = recordings[i]

        result = self.oldestdateplugin._iterate_dates(recordings, starting_date, False, [])
        self.assertEqual(expected_date, result)
        self.oldestdateplugin.config['approach'] = "releases"

    def test_iterate_dates_releases(self):
        self.oldestdateplugin.config['approach'] = "releases"
        recordings = [
            {"recording": {"id": self.recording_id}, "begin": "1978",
             "release-list": [{"date": "1976", "status": "Bootleg"}]},
            {"recording": {"id": self.recording_id + 1}, "begin": "1978", "attribute-list": ["live"],
             "release-list": [{"date": "1975", "status": "Official"}]},
            {"recording": {"id": self.recording_id + 2}, "begin": "1974", "attribute-list": ["cover"],
             "release-list": [{"date": "1975"}]}  # cover gets filtered out
        ]
        starting_date = oldestdate.DateWrapper(2022, 10, 10)
        expected_date = oldestdate.DateWrapper(1975)

        # Put recordings into cache to avoid calling the API
        for i in range(len(recordings)):
            self.oldestdateplugin._recordings_cache[self.recording_id + i] = recordings[i]

        result = self.oldestdateplugin._iterate_dates(recordings, starting_date, False, [])
        self.assertEqual(expected_date, result)

    def test_iterate_dates_hybrid_found(self):
        self.oldestdateplugin.config['approach'] = "hybrid"
        recordings = [
            {"recording": {"id": self.recording_id}, "begin": "1978",
             "release-list": [{"date": "1976", "status": "Bootleg"}]},
            {"recording": {"id": self.recording_id + 1}, "begin": "1978", "attribute-list": ["live"],
             "release-list": [{"date": "1975", "status": "Official"}]},
            {"recording": {"id": self.recording_id + 2}, "begin": "1974", "attribute-list": ["cover"],
             "release-list": [{"date": "1975"}]}  # cover gets filtered out
        ]
        starting_date = oldestdate.DateWrapper(2022, 10, 10)
        expected_date = oldestdate.DateWrapper(1978)

        # Put recordings into cache to avoid calling the API
        for i in range(len(recordings)):
            self.oldestdateplugin._recordings_cache[self.recording_id + i] = recordings[i]

        result = self.oldestdateplugin._iterate_dates(recordings, starting_date, False, [])
        self.assertEqual(expected_date, result)
        self.oldestdateplugin.config['approach'] = "releases"

    def test_iterate_dates_hybrid_not_found(self):
        self.oldestdateplugin.config['approach'] = "hybrid"
        recordings = [
            {"recording": {"id": self.recording_id}, "begin": "",
             "release-list": [{"date": "1976", "status": "Bootleg"}]},
            {"recording": {"id": self.recording_id + 1}, "begin": "", "attribute-list": ["live"],
             "release-list": [{"date": "1975", "status": "Official"}]},
            {"recording": {"id": self.recording_id + 2}, "begin": "", "attribute-list": ["cover"],
             "release-list": [{"date": "1975"}]}  # cover gets filtered out
        ]
        starting_date = oldestdate.DateWrapper(2022, 10, 10)
        expected_date = oldestdate.DateWrapper(1975)

        # Put recordings into cache to avoid calling the API
        for i in range(len(recordings)):
            self.oldestdateplugin._recordings_cache[self.recording_id + i] = recordings[i]

        result = self.oldestdateplugin._iterate_dates(recordings, starting_date, False, [])
        self.assertEqual(expected_date, result)
        self.oldestdateplugin.config['approach'] = "releases"

    def test_iterate_dates_both(self):
        self.oldestdateplugin.config['approach'] = "both"
        recordings = [
            {"recording": {"id": self.recording_id}, "begin": "",
             "release-list": [{"date": "1976", "status": "Bootleg"}]},
            {"recording": {"id": self.recording_id + 1}, "begin": "1974", "attribute-list": ["live"],
             "release-list": [{"date": "1975", "status": "Official"}]},
            {"recording": {"id": self.recording_id + 2}, "begin": "1973", "attribute-list": ["cover"],
             "release-list": [{"date": "1975"}]}  # cover gets filtered out
        ]
        starting_date = oldestdate.DateWrapper(2022, 10, 10)
        expected_date = oldestdate.DateWrapper(1974)

        # Put recordings into cache to avoid calling the API
        for i in range(len(recordings)):
            self.oldestdateplugin._recordings_cache[self.recording_id + i] = recordings[i]

        result = self.oldestdateplugin._iterate_dates(recordings, starting_date, False, [])
        self.assertEqual(expected_date, result)
        self.oldestdateplugin.config['approach'] = "releases"


if __name__ == '__main__':
    unittest.main()
