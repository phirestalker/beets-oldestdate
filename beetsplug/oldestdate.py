import time
from typing import Optional, Any, List, Dict, Callable, TypeVar
import mediafile
import musicbrainzngs
from beets import ui, config
from beets.autotag import hooks, TrackInfo
from beets.importer import action, ImportTask, ImportSession
from beets.library import Item, Library
from beets.plugins import BeetsPlugin
from musicbrainzngs import NetworkError

from .date_wrapper import DateWrapper

musicbrainzngs.set_useragent(
    "Beets oldestdate plugin",
    '1.1.4',  # Also change in pyproject.toml
    "https://github.com/kernitus/beets-oldestdate"
)

# Type alias
Recording = Dict[str, Any]
Work = Dict[str, Any]



class OldestDatePlugin(BeetsPlugin):  # type: ignore
    _importing: bool = False
    _recordings_cache: Dict[str, Recording] = dict()

    def __init__(self) -> None:
        super(OldestDatePlugin, self).__init__()
        self.import_stages = [self._on_import]
        self.config.add({
            'auto': True,  # Run during import phase
            'ignore_track_id': False,  # During import, ignore existing track_id
            'filter_on_import': True,  # During import, weight down candidates with no work_id
            'prompt_missing_work_id': True,  # During import, prompt to fix work_id if missing
            'force': False,  # Run even if already processed
            'overwrite_date': False,  # Overwrite date field in tags
            'overwrite_month': True,  # If overwriting date, also overwrite month field
            'overwrite_day': True,  # If overwriting date and month, also overwrite day
            'filter_recordings': True,  # Skip recordings with attributes before fetching them
            'approach': 'releases',  # recordings, releases, hybrid, both
            'release_types': None,  # Filter by release type, e.g. ['Official']
            'use_file_date': False,  # Also use file's embedded date when looking for oldest date
            'max_network_retries': 3  # Maximum amount of times a given network call will be retried
        })

        if self.config['auto']:
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
                'recording_day'):
            field = mediafile.MediaField(
                mediafile.MP3DescStorageStyle(recording_field),
                mediafile.MP4StorageStyle('----:com.apple.iTunes:{}'.format(
                    recording_field)),
                mediafile.StorageStyle(recording_field))
            self.add_media_field(recording_field, field)

    def commands(self) -> List[ui.Subcommand]:
        recording_date_command = ui.Subcommand(
            'oldestdate',
            help="Retrieve the date of the oldest known recording or release of a track.",
            aliases=['olddate'])
        recording_date_command.func = self._command_func
        return [recording_date_command]

    def _import_trackinfo(self, info: TrackInfo) -> None:
        """Fetch the recording associated with each candidate"""
        if 'track_id' in info:
            self._fetch_recording(info.track_id)

    def track_distance(self, _: Item, info: TrackInfo) -> hooks.Distance:
        dist = hooks.Distance()
        if info.data_source != 'MusicBrainz':
            self._log.debug('Skipping track with non MusicBrainz data source {0.artist} - {0.title}', info)
            return dist
        if self.config['filter_on_import'] and not self._has_work_id(info.track_id):
            dist.add('work_id', 1)

        return dist

    def _import_task_created(self, task: ImportTask, session: ImportSession) -> None:
        task.item.mb_trackid = None

    def _import_task_choice(self, task: ImportTask, session: ImportSession) -> None:
        match = task.match
        if not match:
            return
        match = match.info

        recording_id = match.track_id
        search_link = "https://musicbrainz.org/search?query=" + match.title.replace(' ', '+') \
                      + "+artist%3A%22" + match.artist.replace(' ', '+') \
                      + "%22&type=recording&limit=100&method=advanced"

        while not self._has_work_id(recording_id):
            recording_date = self._get_oldest_date(recording_id,
                                                   DateWrapper(task.item.year, task.item.month, task.item.day))
            recording_year_string = None if recording_date is None else recording_date.strftime('%Y-%m-%d')

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

    T = TypeVar('T')
    def _retry_on_network_error(self, func: Callable[..., T], *args: Any, **kwargs: Any) -> T:
        max_retries: int = self.config['max_network_retries'].get()
        for attempt in range(max_retries):
            try:
                return func(*args, **kwargs)
            except NetworkError:
                if attempt < max_retries - 1:  # No need to wait after the last attempt
                    delay: int = 2 ** attempt
                    self._log.info(f'Network call failed, attempt {attempt}/{max_retries}. Trying again in {delay}')
                    time.sleep(delay)  # Exponential backoff each attempt
                else:
                    raise
        assert False, "Unreachable code"  # To satisfy mypy; this will never actually be reached

    def _get_work_id_from_recording(self, recording: Recording) -> Optional[str]:
        """Extract first valid work_id from recording"""
        work_id = None

        if 'work-relation-list' in recording:
            for work_rel in recording['work-relation-list']:
                if 'work' in work_rel:
                    current_work = work_rel['work']
                    if 'id' in current_work:
                        work_id = current_work['id']
                        break

        return work_id

    def _contains_artist(self, recording: Recording, artist_ids: List[str]) -> bool:
        """Returns whether this recording contains at least one of the specified artists"""
        artist_found = False
        if 'artist-credit' in recording:
            for artist in recording['artist-credit']:
                if 'artist' in artist:
                    artist = artist['artist']
                    if 'id' in artist and artist['id'] in artist_ids:  # Contains at least one of the identified artists
                        artist_found = True
                        break
        return artist_found

    def _get_artist_ids_from_recording(self, recording: Recording) -> List[str]:
        """Extract artist ids from a recording"""
        ids = []

        if 'artist-credit' in recording:
            for artist in recording['artist-credit']:
                if 'artist' in artist:
                    artist = artist['artist']
                    if 'id' in artist:
                        ids.append(artist['id'])
        return ids

    def _is_cover(self, recording: Recording) -> bool:
        """Returns whether given fetched recording is a cover of a work"""
        if 'work-relation-list' in recording:
            for work in recording['work-relation-list']:
                if 'attribute-list' in work:
                    if 'cover' in work['attribute-list']:
                        return True
        return False

    def _fetch_work(self, work_id: str) -> Work:
        """Fetch work, including recording relations"""
        work: Work = self._retry_on_network_error(
            musicbrainzngs.get_work_by_id,
            work_id,
            includes=['recording-rels']
        )['work']
        return work

    def _has_work_id(self, recording_id: str) -> bool:
        """Return whether the recording has a work id"""
        recording = self._get_recording(recording_id)
        work_id = self._get_work_id_from_recording(recording)
        return work_id is not None

    def _command_func(self, lib: Library, _: ImportSession, args: List[str]) -> None:
        """This queries the local database, not the files."""
        for item in lib.items(args):
            self._process_file(item)

    def _on_import(self, _: ImportSession, task: ImportTask) -> None:
        if self.config['auto']:
            self._importing = True
            for item in task.imported_items():
                self._process_file(item)

    def _process_file(self, item: Item) -> None:
        if not item.mb_trackid or item.data_source != 'MusicBrainz':
            self._log.info('Skipping track with no mb_trackid: {0.artist} - {0.title}', item)
            return

        # Check for the recording_year and if it exists and not empty skips the track (if force is not True)
        if 'recording_year' in item and item.recording_year and not self.config['force']:
            self._log.info('Skipping already processed track: {0.artist} - {0.title}', item)
            return

        # Get oldest date from MusicBrainz
        oldest_date = self._get_oldest_date(item.mb_trackid, DateWrapper(item.year, item.month, item.day))

        if not oldest_date:
            self._log.error('No date found for {0.artist} - {0.title}', item)
            return

        if oldest_date.y is not None:
            item['recording_year'] = oldest_date.y
        if oldest_date.m is not None:
            item['recording_month'] = oldest_date.m
        if oldest_date.d is not None:
            item['recording_day'] = oldest_date.d

        # Write over the date tag if configured as YYYYMMDD
        year_string = str(oldest_date.y).zfill(4)
        month_string = str(oldest_date.m).zfill(2)
        day_string = str(oldest_date.d).zfill(2)

        if self.config['overwrite_date']:
            self._log.warning(
                'Overwriting date field for: {0.artist} - {0.title} from {0.year}-{0.month}-{0.day} to {1}-{2}-{3}',
                item, year_string, month_string, day_string)
            item.year = "" if oldest_date.y is None else year_string
            item.month = "" if (oldest_date.m is None or not self.config['overwrite_month']) else month_string
            item.day = "" if (oldest_date.d is None or not self.config['overwrite_day']) else day_string

        self._log.info('Applying changes to {0.artist} - {0.title}', item)
        item.store()
        # Prevent changing file on disk before it reaches final destination
        if not self._importing:
            item.write()

    def _fetch_recording(self, recording_id: str) -> Recording:
        """Fetch and cache recording from MusicBrainz, including releases and work relations"""
        recording: Recording = self._retry_on_network_error(
            musicbrainzngs.get_recording_by_id,
            recording_id,
            includes=['artists', 'releases', 'work-rels']
        )['recording']

        self._recordings_cache[recording_id] = recording
        return recording

    def _get_recording(self, recording_id: str) -> Recording:
        """Get recording from cache or MusicBrainz"""
        return self._recordings_cache[
            recording_id] if recording_id in self._recordings_cache else self._fetch_recording(recording_id)

    def _extract_oldest_recording_date(self, recordings: List[Recording], starting_date: DateWrapper,
                                       is_cover: bool, approach: str) -> DateWrapper:
        """Get oldest date from a recording"""
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
                        date = DateWrapper(iso_string=date)
                        if date < oldest_date:
                            oldest_date = date
                    except ValueError:
                        self._log.error("Could not parse date {0} for recording {1}", date, rec)

            # Remove recording from cache if no longer needed
            if approach == 'recordings' or (approach == 'hybrid' and oldest_date != starting_date):
                self._recordings_cache.pop(rec_id, None)

        return oldest_date

    def _extract_oldest_release_date(self, recordings: List[Recording], starting_date: DateWrapper,
                                     is_cover: bool, artist_ids: List[str]) -> DateWrapper:
        """Get oldest date from a release"""
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
                    # Filter by artist, but only if cover (to avoid not matching solo careers of former groups)
                    fetched_recording = self._get_recording(rec_id)
                    if not self._contains_artist(fetched_recording, artist_ids):
                        self._recordings_cache.pop(rec_id, None)  # Remove recording from cache
                        continue
            elif 'attribute-list' in rec and (self.config['filter_recordings'] or 'cover' in rec['attribute-list']):
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
                                    date = DateWrapper(iso_string=release_date)
                                    if date < oldest_date:
                                        oldest_date = date
                                except ValueError:
                                    self._log.error("Could not parse date {0} for recording {1}", release_date, rec)

            self._recordings_cache.pop(rec_id, None)  # Remove recording from cache

        return oldest_date

    def _iterate_dates(self, recordings: List[Recording], starting_date: DateWrapper,
                       is_cover: bool, artist_ids: List[str]) -> Optional[DateWrapper]:
        """Iterates through a list of recordings and returns oldest date"""
        approach = self.config['approach'].get()
        oldest_date = starting_date

        # Look for oldest recording date
        if approach in ('recordings', 'hybrid', 'both'):
            oldest_date = self._extract_oldest_recording_date(recordings, starting_date, is_cover, approach)

        # Look for oldest release date for each recording
        if approach in ('releases', 'both') or (approach == 'hybrid' and oldest_date == starting_date):
            oldest_date = self._extract_oldest_release_date(recordings, oldest_date, is_cover, artist_ids)

        return None if oldest_date == DateWrapper.today() else oldest_date

    def _get_oldest_date(self, recording_id: str, item_date: Optional[DateWrapper]) -> Optional[DateWrapper]:
        recording = self._get_recording(recording_id)
        is_cover = self._is_cover(recording)
        work_id = self._get_work_id_from_recording(recording)
        artist_ids = self._get_artist_ids_from_recording(recording)

        today = DateWrapper.today()

        # If no work id, check this recording against embedded date
        starting_date = item_date if item_date is not None and (
                self.config['use_file_date'] or not work_id) else today

        if not work_id:  # Only look through this recording
            return self._iterate_dates([recording], starting_date, is_cover, artist_ids)

        # Fetch work, including associated recordings
        work = self._fetch_work(work_id)

        if 'recording-relation-list' not in work:
            self._log.error(
                'Work {0} has no valid associated recordings! Please choose another recording or amend the data!',
                work_id)
            return None

        return self._iterate_dates(work['recording-relation-list'], starting_date, is_cover, artist_ids)
