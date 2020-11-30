from __future__ import division, absolute_import, print_function

import datetime

import mediafile
import musicbrainzngs
from beets import ui, config
from beets.plugins import BeetsPlugin
from dateutil import parser

musicbrainzngs.set_useragent(
    "Beets oldestdate plugin",
    "1.0.0",
    "https://github.com/kernitus/beets-oldestdate"
)


# Extract first valid work_id from recording
def _get_work_id_from_recording(recording):
    work_id = None

    if 'work-relation-list' in recording:
        for work_rel in recording['work-relation-list']:
            if 'work' in work_rel:
                current_work = work_rel['work']
                if 'id' in current_work:
                    work_id = current_work['id']
                    break

    return work_id


class OldestDatePlugin(BeetsPlugin):
    importing = False
    _recordings_cache = dict()

    def __init__(self):
        super(OldestDatePlugin, self).__init__()
        self.import_stages = [self._on_import]
        self.config.add({
            'auto': True,  # Run during import phase
            'filter_on_import': False,  # During import, ignore existing track_id and remove candidates with no work_id
            'force': False,  # Run even if already processed
            'overwrite_year': False,  # Overwrite year field in tags
            'filter_recordings': True,  # Skip recordings with attributes before fetching them
            'approach': 'hybrid',  # recordings, releases, hybrid, both
            'release_types': ['Official']  # Filter by release type
        })

        if self.config['filter_on_import']:
            self.register_listener('trackinfo_received', self._import_trackinfo)
            self.register_listener('before_choose_candidate', self._before_choice)
            self.register_listener('import_task_created', self._import_task_created)

        # Get global MusicBrainz host setting
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
        recording_date_command.func = self._command_func
        return [recording_date_command]

    def _import_trackinfo(self, info):
        # Fetch the recording associated with each candidate
        if 'track_id' in info:
            self._fetch_recording(info.track_id)

    def _import_task_created(self, task, session):
        self._log.debug("TASKA: {0}", task.item.mb_trackid)
        task.item.mb_trackid = None

    def _before_choice(self, task, session):
        # Remove candidates that do not have a work id
        task.candidates[:] = [can for can in task.candidates if self._has_work_id(can.info.track_id)]

    # Return whether the recording has a work id
    def _has_work_id(self, recording_id):
        recording = self._get_recording(recording_id)
        work_id = _get_work_id_from_recording(recording)
        return work_id is not None

    # This queries the actual database, not the files.
    def _command_func(self, lib, _, args):
        for item in lib.items(args):
            self._process_file(item)

    def _on_import(self, session, task):
        if self.config['auto']:
            self.importing = True
            for item in task.imported_items():
                self._process_file(item)

    def _process_file(self, item):
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

        self._log.debug('Getting oldest date')

        if not oldest_date:
            self._log.error('No date found for {0.artist} - {0.title}', item)
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

    # Fetch and cache recording from MusicBrainz, including releases and work relations
    def _fetch_recording(self, recording_id):
        recording = musicbrainzngs.get_recording_by_id(recording_id, ['releases', 'work-rels'])['recording']
        self._recordings_cache[recording_id] = recording
        return recording

    # Get recording from cache or MusicBrainz
    def _get_recording(self, recording_id):
        return self._recordings_cache[
            recording_id] if recording_id in self._recordings_cache else self._fetch_recording(recording_id)

    def _get_oldest_release_date(self, recording_id):
        release_types = self.config['release_types'].get()
        recording = self._get_recording(recording_id)
        work_id = _get_work_id_from_recording(recording)

        # Fetch work, including associated recordings
        work = musicbrainzngs.get_work_by_id(work_id, ['recording-rels'])['work']

        if 'recording-relation-list' not in work:
            self._log.error(
                'Work {0} has no valid associated recordings! Please choose another recording or amend the data!',
                work_id)
            return None

        today_date = datetime.date.today()
        oldest_date = today_date

        approach = self.config['approach'].get()

        # Look for oldest recording date
        if approach in ('recordings', 'hybrid', 'both'):
            for rec in work['recording-relation-list']:
                if 'begin' in rec:
                    date = rec['begin']
                    if date:
                        date = parser.isoparse(date).date()
                        if date < oldest_date:
                            oldest_date = date
                # Remove recording from cache if no longer needed
                if approach == 'recordings' or (approach == 'hybrid' and oldest_date != today_date):
                    self._recordings_cache.pop(rec['recording']['id'], None)  # Remove recording from cache

        # Looks for oldest release date for each recording found
        if approach in ('releases', 'both') or (approach == 'hybrid' and oldest_date == today_date):
            for rec in work['recording-relation-list']:

                rec_id = rec['recording']['id']

                # Filter the recordings list, sometimes it can be very long. This skips covers, lives etc.
                if self.config['filter_recordings'] and 'attribute-list' in rec:
                    self._recordings_cache.pop(rec_id, None)  # Remove recording from cache
                    continue

                fetched_recording = self._get_recording(rec_id)

                if 'release-list' in fetched_recording:
                    for release in fetched_recording['release-list']:
                        if release_types is None or (  # Filter by recording type, i.e. Official
                                'status' in release and release['status'] in release_types):
                            if 'date' in release:
                                release_date = release['date']
                                if release_date:
                                    date = parser.isoparse(release_date).date()
                                    if date < oldest_date:
                                        oldest_date = date

                self._recordings_cache.pop(rec_id, None)  # Remove recording from cache

        return None if oldest_date == today_date else {'year': oldest_date.year,
                                                       'month': oldest_date.month,
                                                       'day': oldest_date.day}
