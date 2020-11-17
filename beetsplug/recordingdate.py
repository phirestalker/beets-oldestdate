# -- coding: utf-8 --
from __future__ import division, absolute_import, print_function

import datetime
import musicbrainzngs
import mediafile
from beets import ui, config
from beets.plugins import BeetsPlugin
from dateutil import parser

musicbrainzngs.set_useragent(
    "Beets recording date plugin",
    "0.2",
    "http://github.com/tweitzel"
)


def _get_dict(dictionary, *attributes):
    try:
        for key in attributes:
            dictionary = dictionary[key]
        return dictionary
    except(TypeError, KeyError):
        return None


def _make_date_values(date_str):
    date_parts = date_str.split('-')
    date_values = {'year': 0, 'month': 0, 'day': 0}
    for key in ('year', 'month', 'day'):
        if date_parts:
            date_part = date_parts.pop(0)
            try:
                date_num = int(date_part)
            except ValueError:
                continue
            date_values[key] = date_num
    return date_values


class RecordingDatePlugin(BeetsPlugin):
    importing = False

    def __init__(self):
        super(RecordingDatePlugin, self).__init__()
        self.import_stages = [self.on_import]
        self.config.add({
            'auto': True,
            'force': False,
            'write_over': False,
        })

        # Get global MusicBrainz host setting
        # TODO fallback values for musicbrainz settings
        musicbrainzngs.set_hostname(config['musicbrainz']['host'].get())
        musicbrainzngs.set_rate_limit(1, config['musicbrainz']['ratelimit'].get())
        for recording_field in (
                'recording_year',
                'recording_month',
                'recording_day',
                'recording_disambiguation'):
            field = mediafile.MediaField(
                mediafile.MP3DescStorageStyle(recording_field),
                mediafile.MP4StorageStyle('----:com.apple.iTunes:{}'.format(
                    recording_field)),
                mediafile.StorageStyle(recording_field))
            self.add_media_field(recording_field, field)

    def commands(self):
        recording_date_command = ui.Subcommand(
            'recordingdate',
            help="Retrieve the date of the first known release of a track.",
            aliases=['rdate'])
        recording_date_command.func = self.func
        return [recording_date_command]

    def func(self, lib, opts, args):
        query = ui.decargs(args)
        self.recording_date(lib, query)

    def recording_date(self, lib, query):
        for item in lib.items(query):
            self.process_file(item)

    def on_import(self, session, task):
        if self.config['auto']:
            self.importing = True
            for item in task.imported_items():
                self.process_file(item)

    def process_file(self, item):
        item_formatted = format(item)

        if not item.mb_trackid:
            self._log.info('Skipping track with no mb_trackid: {0}',
                           item_formatted)
            return

        # Check for the recording_year and if it exists and not empty skips the track (if force is not True)
        if 'recording_year' in item and item.recording_year and not self.config['force']:
            self._log.info('Skipping already processed track: {0}', item_formatted)
            return

        # Get the MusicBrainz recording info.
        recording_date = self._get_oldest_release_date(item.mb_trackid, item.mb_artistid)

        if not recording_date:
            self._log.info('Recording ID not found: {0} for track {0}',
                           item.mb_trackid,
                           item_formatted)
            return

        # Apply.
        write = False
        for recording_field in ('year', 'month', 'day'):
            if recording_field in recording_date.keys():
                item['recording_' + recording_field] = recording_date[recording_field]

                # Write over the year tag if configured
                if self.config['write_over'] and recording_field == 'year':
                    item[recording_field] = recording_date[recording_field]
                    self._log.warning('Overwriting year field for: {0} from {1} to {2}', item_formatted,
                                      item.recording_year, recording_date[recording_field])
                write = True
        if write:
            self._log.info('Applying changes to {0}', item_formatted)
            item.write()
            item.store()
            if not self.importing:
                item.write()
        else:
            self._log.info('Error: {0}', recording_date)

    def _get_oldest_release_date(self, recording_id, artist_id):

        # Fetch recording from recording_id
        recording = musicbrainzngs.get_recording_by_id(recording_id, ['releases', 'work-rels'])['recording']
        self._log.debug('Recording fetched: {0}', recording)

        releases = list()
        releases.append(recording['release-list'])

        # TODO don't just take first work
        work_id = recording['work-relation-list'][0]['work']['id']
        work = musicbrainzngs.get_work_by_id(work_id, ['recording-rels'])['work']

        oldest_release_date = datetime.date.today()

        for rec in work['recording-relation-list']:
            if 'begin' in rec:
                self._log.debug('Rec begin date: {0}', rec['begin'])
                date = rec['begin']
                if date:
                    date = parser.isoparse(date).date()
                    if date < oldest_release_date:
                        oldest_release_date = date

        oldest_release = {'year': oldest_release_date.year, 'month': oldest_release_date.month,
                          'day': oldest_release_date.day}

        # TODO if no recording had a date, we might want to go through the releases for each recording

        if oldest_release_date == datetime.date.today():
            self._log.error('Could not find date information for {0} - {1}', artist_id, recording_id)
            oldest_release = {'year': None, 'month': None, 'day': None}
        return oldest_release
