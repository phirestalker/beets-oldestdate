from __future__ import division, absolute_import, print_function

import datetime
import musicbrainzngs
import mediafile
from beets import ui, config
from beets.plugins import BeetsPlugin
from dateutil import parser

musicbrainzngs.set_useragent(
    "Beets oldestdate plugin",
    "0.1",
    "https://github.com/kernitus/beets-oldestdate"
)


class OldestDatePlugin(BeetsPlugin):
    importing = False

    def __init__(self):
        super(OldestDatePlugin, self).__init__()
        self.import_stages = [self.on_import]
        self.config.add({
            'auto': True,  # Run during import phase
            'force': False,  # Run even if already processed
            'overwrite_year': False,  # Overwrite year field in tags
            'filter_recordings': True,  # Skip recordings with attributes before fetching them
            'approach': 'hybrid'  # recordings, releases, hybrid, both
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
            'oldestdate',
            help="Retrieve the date of the oldest known recording or release of a track.",
            aliases=['olddate'])
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
        if not item.mb_trackid:
            self._log.info('Skipping track with no mb_trackid: {0.artist} - {0.title}',
                           item)
            return

        # Check for the recording_year and if it exists and not empty skips the track (if force is not True)
        if 'recording_year' in item and item.recording_year and not self.config['force']:
            self._log.info('Skipping already processed track: {0.artist} - {0.title}', item)
            return

        # Get oldest date from MusicBrainz
        oldest_date = self._get_oldest_release_date(item.mb_trackid)

        if not oldest_date:
            self._log.info('No data not found for {0.artist} - {0.title}', item)
            return

        write = False
        for recording_field in ('year', 'month', 'day'):
            if recording_field in oldest_date.keys():
                item['recording_' + recording_field] = oldest_date[recording_field]

                # Write over the year tag if configured
                if self.config['overwrite_year'] and recording_field == 'year':
                    item[recording_field] = oldest_date[recording_field]
                    self._log.warning('Overwriting year field for: {0.artist} - {0.title} from {1} to {2}', item,
                                      item.recording_year, oldest_date[recording_field])
                write = True
        if write:
            self._log.info('Applying changes to {0.artist} - {0.title}', item)
            item.write()
            item.store()
            if not self.importing:
                item.write()
        else:
            self._log.info('Error: {0}', oldest_date)

    def _get_oldest_release_date(self, recording_id):

        # Fetch recording from recording_id
        recording = musicbrainzngs.get_recording_by_id(recording_id, ['releases', 'work-rels'])['recording']

        if 'work-relation-list' not in recording:
            self._log.error('Recording {0} has no associated works! Please choose another recording or amend the data!',
                            recording_id)
            return None

        # TODO don't just take first work
        work_id = recording['work-relation-list'][0]['work']['id']
        work = musicbrainzngs.get_work_by_id(work_id, ['recording-rels'])['work']

        today_date = datetime.date.today()
        oldest_date = today_date

        approach = self.config['approach'].get()

        # Look through recording dates
        if approach in ('recordings', 'hybrid', 'both'):
            for rec in work['recording-relation-list']:
                if 'begin' in rec:
                    date = rec['begin']
                    if date:
                        date = parser.isoparse(date).date()
                        if date < oldest_date:
                            oldest_date = date

        # Looks through release dates for each recording found
        if approach in ('releases', 'both') or (approach == 'hybrid' and oldest_date == today_date):
            for rec in work['recording-relation-list']:

                # Filter the recordings list, sometimes it can be very long. This skips covers, lives etc.
                if self.config['filter_recordings'] and 'attribute-list' in rec:
                    continue

                rec_id = rec['recording']['id']

                # Avoid extra API call for already fetched recording
                fetched_recording = recording if rec_id == recording_id else \
                    musicbrainzngs.get_recording_by_id(rec_id, ['releases'], ['official'])[
                        'recording']

                for release in fetched_recording['release-list']:
                    if 'date' in release:
                        release_date = release['date']
                        if release_date:
                            date = parser.isoparse(release_date).date()
                            if date < oldest_date:
                                oldest_date = date

        return None if oldest_date == today_date else {'year': oldest_date.year,
                                                       'month': oldest_date.month,
                                                       'day': oldest_date.day}
