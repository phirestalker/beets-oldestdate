import unittest
from dateutil import parser

import oldestdate


class OldestDatePluginTest(unittest.TestCase):
    def test_something(self):
        test_recording = {"work-relation-list": [{"work": {"id": 20}}]}
        result = oldestdate._get_work_id_from_recording(test_recording)
        self.assertEqual(20, result)

    def test_extract_oldest_recording_date(self):
        recordings = [{"recording": {"id": 20}, "begin": "2020-12-12"}]
        starting_date = parser.isoparse("20221010").date()
        expected_date = parser.isoparse("20201212").date()
        is_cover = False
        approach = "recordings"
        oldestdateplugin = oldestdate.OldestDatePlugin()
        result = oldestdateplugin._extract_oldest_recording_date(recordings, starting_date, is_cover, approach)
        self.assertEqual(expected_date, result)


if __name__ == '__main__':
    unittest.main()
