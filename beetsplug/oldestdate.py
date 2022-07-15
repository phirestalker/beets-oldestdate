from __future__ import division, absolute_import, print_function

import datetime

import mediafile
import musicbrainzngs
from beets import ui, config
from beets.autotag import hooks
from beets.importer import action
from beets.plugins import BeetsPlugin
from dateutil import parser

musicbrainzngs.set_useragent(
    "Beets oldestdate plugin",
    "1.1.2",
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


# Returns whether this recording contains at least one of the specified artists
def _contains_artist(recording, artist_ids):
    artist_found = False
    if 'artist-credit' in recording:
        for artist in recording['artist-credit']:
            if 'artist' in artist:
                artist = artist['artist']
                if 'id' in artist and artist['id'] in artist_ids:  # Contains at least one of the identified artists
                    artist_found = True
                    break
    return artist_found


# Extract artist ids from a recording
def _get_artist_ids_from_recording(recording):
    ids = []

    if 'artist-credit' in recording:
        for artist in recording['artist-credit']:
            if 'artist' in artist:
                artist = artist['artist']
                if 'id' in artist:
                    ids.append(artist['id'])
    return ids


# Returns whether given recording is a cover of a work
def _is_cover(recording):
    if 'work-relation-list' in recording:
        for work in recording['work-relation-list']:
            if 'attribute-list' in work:
                if 'cover' in work['attribute-list']:
                    return True
    return False


def _date_from_file(year, month, day):
    file_date = None
    try:
        file_date_str = str(year) + str(month) + str(day)
        file_date = parser.isoparse(file_date_str).date()
    except (KeyError, ValueError):
        try:
            file_date_str = str(year) + "0101"  # First of January
            file_date = parser.isoparse(file_date_str).date()
        except (KeyError, ValueError):
            pass
    return file_date


class OldestDatePlugin(BeetsPlugin):
    _importing = False
    _recordings_cache = dict()

    def __init__(self):
        super(OldestDatePlugin, self).__init__()
        self.import_stages = [self._on_import]
        self.config.add({
            'auto': True,  # Run during import phase
            'ignore_track_id': False,  # During import, ignore existing track_id
            'filter_on_import': True,  # During import, weight down candidates with no work_id
            'prompt_missing_work_id': True,  # During import, prompt to fix work_id if missing
            'force': False,  # Run even if already processed
            'overwrite_year': False,  # Overwrite year field in tags
            'filter_recordings': True,  # Skip recordings with attributes before fetching them
            'approach': 'releases',  # recordings, releases, hybrid, both
            'release_types': None,  # Filter by release type, e.g. ['Official']
            'use_file_date': False  # Also use file's embedded date when looking for oldest date
        })

        if self.config['ignore_track_id']:
            self.register_listener('import_task_created', self._import_task_created)
        if self.config['prompt_missing_work_id']:
            self.register_listener('import_task_choice', self._import_task_choice)
        if self.config['filter_on_import']:
            self.register_listener('trackinfo_received', self._import_trackinfo)
            # Add heavy weight for missing work_id from a track
            config['match']['distance_weights'].add({'work_id': 4})

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

    # Fetch the recording associated with each candidate
    def _import_trackinfo(self, info):
        if 'track_id' in info:
            self._fetch_recording(info.track_id)

    def track_distance(self, session, info):
        dist = hooks.Distance()
        if self.config['filter_on_import'] and not self._has_work_id(info.track_id):
            dist.add('work_id', 1)

        return dist

    def _import_task_created(self, task, session):
        task.item.mb_trackid = None

    def _import_task_choice(self, task, session):
        match = task.match
        if not match:
            return
        match = match.info

        recording_id = match.track_id
        search_link = "https://musicbrainz.org/search?query=" + match.title.replace(' ', '+') \
                      + "+artist%3A%22" + match.artist.replace(' ', '+') \
                      + "%22&type=recording&limit=100&method=advanced"

        while not self._has_work_id(recording_id):
            recording_year = self._get_oldest_date(recording_id,
                                                   _date_from_file(task.item.year, task.item.month, task.item.day))
            recording_year_string = None if recording_year is None else str(recording_year['year'])

            self._log.error("{0.artist} - {0.title} ({1}) has no associated work! Please fix "
                            "and try again!", match,
                            recording_year_string)
            print("Search link: " + search_link)
            sel = ui.input_options(('Use this recording', 'Try again', 'Skip track'))

            if sel == "t":  # Fetch data again
                self._fetch_recording(recording_id)
            elif sel == "u":
                return
            else:
                task.choice_flag = action.SKIP
                return

    # Return whether the recording has a work id
    def _has_work_id(self, recording_id):
        recording = self._get_recording(recording_id)
        work_id = _get_work_id_from_recording(recording)
        return work_id is not None

    # This queries the local database, not the files.
    def _command_func(self, lib, session, args):
        for item in lib.items(args):
            self._process_file(item)

    def _on_import(self, session, task):
        if self.config['auto']:
            self._importing = True
            for item in task.imported_items():
                self._process_file(item)

    def _process_file(self, item):
        if not item.mb_trackid:
            self._log.info('Skipping track with no mb_trackid: {0.artist} - {0.title}', item)
            return

        # Check for the recording_year and if it exists and not empty skips the track (if force is not True)
        if 'recording_year' in item and item.recording_year and not self.config['force']:
            self._log.info('Skipping already processed track: {0.artist} - {0.title}', item)
            return

        # Get oldest date from MusicBrainz
        oldest_date = self._get_oldest_date(item.mb_trackid, _date_from_file(item.year, item.month, item.day))

        if not oldest_date:
            self._log.error('No date found for {0.artist} - {0.title}', item)
            return

        write = False
        for recording_field in ('year', 'month', 'day'):
            if recording_field in oldest_date.keys():
                item['recording_' + recording_field] = oldest_date[recording_field]

                # Write over the year tag if configured
                if self.config['overwrite_year'] and recording_field == 'year':
                    self._log.warning('Overwriting year field for: {0.artist} - {0.title} from {1} to {2}', item,
                                      item[recording_field], oldest_date[recording_field])
                    item[recording_field] = oldest_date[recording_field]
                write = True

        if write:
            self._log.info('Applying changes to {0.artist} - {0.title}', item)
            # prevent changing file on disk before it reaches final destination
            # item.write()
            item.store()
            if not self._importing:
                item.write()
        else:
            self._log.info('Error: {0}', oldest_date)

    # Fetch and cache recording from MusicBrainz, including releases and work relations
    def _fetch_recording(self, recording_id):
        recording = musicbrainzngs.get_recording_by_id(recording_id, ['artists', 'releases', 'work-rels'])['recording']
        self._recordings_cache[recording_id] = recording
        return recording

    # Get recording from cache or MusicBrainz
    def _get_recording(self, recording_id):
        return self._recordings_cache[
            recording_id] if recording_id in self._recordings_cache else self._fetch_recording(recording_id)

    # Get oldest date from a recording
    def _extract_oldest_recording_date(self, recordings, starting_date, is_cover, approach):
        oldest_date = starting_date

        for rec in recordings:
            if 'recording' not in rec:
                continue
            rec_id = rec['recording']
            if 'id' not in rec_id:
                continue
            rec_id = rec_id['id']

            # If a cover, filter recordings to only keep covers. Otherwise, remove covers
            if is_cover != ('attribute-list' in rec and 'cover' in rec['attribute-list']):
                # We can't filter by author here without fetching each individual recording.
                self._recordings_cache.pop(rec_id, None)  # Remove recording from cache
                continue

            if 'begin' in rec:
                date = rec['begin']
                if date:
                    try:
                        date = parser.isoparse(date).date()
                        if date < oldest_date:
                            oldest_date = date
                    except ValueError:
                        self._log.error("Could not parse date {0} for recording {1}", date, rec)

            # Remove recording from cache if no longer needed
            if approach == 'recordings' or (approach == 'hybrid' and oldest_date != starting_date):
                self._recordings_cache.pop(rec_id, None)

        return oldest_date

    # Get oldest date from a release
    def _extract_oldest_release_date(self, recordings, starting_date, is_cover):
        oldest_date = starting_date
        release_types = self.config['release_types'].get()

        for rec in recordings:
            rec_id = rec['recording'] if 'recording' in rec else rec
            if 'id' not in rec_id:
                continue
            rec_id = rec_id['id']

            fetched_recording = None

            # Shorten recordings list, but if song is a cover, only keep covers
            if is_cover:
                if 'attribute-list' not in rec or 'cover' not in rec['attribute-list']:
                    self._recordings_cache.pop(rec_id, None)  # Remove recording from cache
                    continue
                else:
                    # Filter by artist, but only if cover, to avoid a group splitting up into solos not matching
                    fetched_recording = self._get_recording(rec_id)
                    if not _contains_artist(fetched_recording, artist_ids):
                        self._recordings_cache.pop(rec_id, None)  # Remove recording from cache
                        continue
            elif self.config['filter_recordings'] and 'attribute-list' in rec:  # If live, cover etc.
                self._recordings_cache.pop(rec_id, None)  # Remove recording from cache
                continue

            if not fetched_recording:
                fetched_recording = self._get_recording(rec_id)

            if 'release-list' in fetched_recording:
                for release in fetched_recording['release-list']:
                    if release_types is None or (  # Filter by recording type, i.e. Official
                            'status' in release and release['status'] in release_types):
                        if 'date' in release:
                            release_date = release['date']
                            if release_date:
                                try:
                                    date = parser.isoparse(release_date).date()
                                    if date < oldest_date:
                                        oldest_date = date
                                except ValueError:
                                    self._log.error("Could not parse date {0} for recording {1}", release_date, rec)

            self._recordings_cache.pop(rec_id, None)  # Remove recording from cache

        return oldest_date

    # Iterates through a list of recordings and returns oldest date
    def _iterate_dates(self, recordings, starting_date, is_cover, artist_ids):
        approach = self.config['approach'].get()
        oldest_date = starting_date

        # Look for oldest recording date
        if approach in ('recordings', 'hybrid', 'both'):
            oldest_date = self._extract_oldest_recording_date(recordings, starting_date, is_cover, approach)

        # Look for oldest release date for each recording
        if approach in ('releases', 'both') or (approach == 'hybrid' and oldest_date == starting_date):
            oldest_date = self._extract_oldest_release_date(recordings, starting_date, is_cover)

        return None if oldest_date == datetime.date.today() else \
            {'year': oldest_date.year, 'month': oldest_date.month, 'day': oldest_date.day}

    def _get_oldest_date(self, recording_id, item_date):
        recording = self._get_recording(recording_id)
        is_cover = _is_cover(recording)
        work_id = _get_work_id_from_recording(recording)
        artist_ids = _get_artist_ids_from_recording(recording)

        # If no work id, check this recording against embedded date
        starting_date = item_date if item_date is not None and (
                self.config['use_file_date'] or not work_id) else datetime.date.today()

        if not work_id:  # Only look through this recording
            return self._iterate_dates([recording], starting_date, is_cover, artist_ids)

        # Fetch work, including associated recordings
        work = musicbrainzngs.get_work_by_id(work_id, ['recording-rels'])['work']

        if 'recording-relation-list' not in work:
            self._log.error(
                'Work {0} has no valid associated recordings! Please choose another recording or amend the data!',
                work_id)
            return None

        return self._iterate_dates(work['recording-relation-list'], starting_date, is_cover, artist_ids)
