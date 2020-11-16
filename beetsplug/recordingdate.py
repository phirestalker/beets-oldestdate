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
        recording_date = self._get_oldest_release_date(item.mb_trackid, item.recording_year)

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
                    self._log.info('Overwriting year field for: {0} to {1}', item_formatted,
                                   recording_date[recording_field])
                write = True
        if write:
            self._log.info('Applying changes to {0}', item_formatted)
            item.write()
            item.store()
            if not self.importing:
                item.write()
        else:
            self._log.info('Error: {0}', recording_date)

    def _get_oldest_release_date(self, recording_id, recording_year):
        # Get recording by Id
        recording = musicbrainzngs.get_recording_by_id(recording_id, includes=["artists"])['recording']
        self._log.debug('Original Recording: {0}', recording)

        artist_names = []
        artist_id_set = set()
        for artist in recording['artist-credit']:
            artist_names.append(artist['artist']['name'])
            artist_id_set.add(artist['artist']['id'])

        self._log.debug("artist names: {0},; artist ids: {1}", artist_names, artist_id_set)

        # Search for this song by exact name and artist
        releases = musicbrainzngs.search_releases(query=recording['title'], strict=True, artistname=artist_names)[
            'release-list']

        oldest_release_date = datetime.date.today()

        for release in releases:
            if release['status'] != 'Official':
                releases.remove(release)
                continue

            missing_artist = False
            for artist in release['artist-credit']:
                self._log.debug('Artist: {0}', artist)
                current_artist_id = _get_dict(artist, 'artist', 'id')
                if current_artist_id not in artist_id_set:
                    missing_artist = True
                    break

            if missing_artist:
                releases.remove(release)
                continue

            self._log.debug('Title: {0}, Status: {1}, Date: {2}', release['title'],
                            release['status'], release['date'])

            release_date = parser.isoparse(release['date']).date()
            self._log.debug(u'Release date: {0}', release_date)
            if release_date < oldest_release_date:
                oldest_release_date = release_date

        oldest_release = {'year': oldest_release_date.year, 'month': oldest_release_date.month,
                          'day': oldest_release_date.day}

        self._log.debug('Original Year: {0}     Oldest Release Year: {1}', recording_year, oldest_release['year'])

        if oldest_release_date == datetime.date.today():
            self._log.error('Could not find date information for {0}', recording)
            oldest_release = {'year': None, 'month': None, 'day': None}
        return oldest_release
