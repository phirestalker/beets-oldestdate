# -- coding: utf-8 --
from __future__ import division, absolute_import, print_function

from beets.plugins import BeetsPlugin
from beets import autotag, library, ui, util, config, mediafile
from beets.autotag import hooks
from dateutil import parser
import datetime

import musicbrainzngs
musicbrainzngs.set_useragent(
        "Beets recording date plugin",
        "0.2",
        "http://github.com/tweitzel"
        )


class RecordingDatePlugin(BeetsPlugin):
    def __init__(self):
        super(RecordingDatePlugin, self).__init__()
        self.import_stages = [self.on_import]
        self.config.add({
            'auto': True,
            'force': False,
            'write_over': False,
            'relations': {'edit', 'first track release', 'remaster'},
            })
        #grab global MusicBrainz host setting
        musicbrainzngs.set_hostname(config['musicbrainz']['host'].get())
        musicbrainzngs.set_rate_limit(1, config['musicbrainz']['ratelimit'].get())
        for recording_field in (
                u'recording_year',
                u'recording_month',
                u'recording_day',
                u'recording_disambiguation'):
            field = mediafile.MediaField(
                    mediafile.MP3DescStorageStyle(recording_field),
                    mediafile.MP4StorageStyle('----:com.apple.iTunes:{}'.format(
                        recording_field)),
                    mediafile.StorageStyle(recording_field))
            self.add_media_field(recording_field, field)

    def commands(self):
        recording_date_command = ui.Subcommand(
                'recordingdate',
                help="Retrieve the date of the first known recording of a track.",
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
            for item in task.imported_items():
                self.process_file(item)

    def process_file(self, item):
        item_formatted = format(item)

        if not item.mb_trackid:
            self._log.info(u'Skipping track with no mb_trackid: {0}',
                    item_formatted)
            return
        # check for the recording_year and if it exists and not empty
        # skips the track if force is not configured
        if u'recording_year' in item and item.recording_year and not self.config['force']:
            self._log.info(u'Skipping already processed track: {0}', item_formatted)
            return
        # Get the MusicBrainz recording info.
        (recording_date, disambig) = self.get_first_recording_year(
                item.mb_trackid)
        if not recording_date:
            self._log.info(u'Recording ID not found: {0} for track {0}',
                    item.mb_trackid,
                    item_formatted)
            return
        # Apply.
        write = False
        for recording_field in ('year', 'month', 'day'):
            if recording_field in recording_date.keys():
                item[u'recording_' +
                        recording_field] = recording_date[recording_field]
                # writes over the year tag if configured
                if self.config['write_over'] and recording_field == u'year':
                    item[recording_field] = recording_date[recording_field]
                    self._log.info(u'overwriting year field for: {0} to {1}', item_formatted, recording_date[recording_field])
                write = True
        if disambig is not None:
            item[u'recording_disambiguation'] = str(disambig)
            write = True
        if write:
            self._log.info(u'Applying changes to {0}', item_formatted)
            item.write()
            item.store()
        else:
            self._log.info(u'Error: {0}', recording_date)

    def _make_date_values(self, date_str):
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

    def _recurse_relations(self, mb_track_id, oldest_release, relation_type):
        x = musicbrainzngs.get_recording_by_id(
                mb_track_id,
                includes=["releases", "recording-rels"]
                )

        for key in x['recording'].keys():
            self._log.info(u'Key {0} Value {1}', key, x['recording'][key])

        if not x['recording']['recording-relation-list']:
            self._log.info(u'No Recording relations list!')


        if 'recording-relation-list' in x['recording'].keys():
            # recurse down into edits and remasters.
            # Note remasters are deprecated in musicbrainz, but some entries
            # may still exist.
            for subrecording in x['recording']['recording-relation-list']:
                if ('direction' in subrecording.keys() and
                        subrecording['direction'] == 'backward'):
                    self._log.info(u'Ignoring backwards relationship')
                    continue
                # skip new relationship category samples
                if subrecording['type'] not in self.config['relations'].as_str_seq():
                    self._log.info(u'Skipping unwanted subrecording type {0}', subrecording['type'])
                    continue
                if 'artist' in x['recording'].keys() and x['recording']['artist'] != subrecording['artist']:
                    self._log.info(
                            u'Skipping relation with artist {0} that does not match {1}',
                            subrecording['artist'], x['recording']['artist'])
                    continue
                (oldest_release, relation_type) = self._recurse_relations(
                        subrecording['target'],
                        oldest_release,
                        subrecording['type'])
        for release in x['recording']['release-list']:
            if 'date' not in release.keys():
                # A release without a date. Skip over it.
                self._log.info(u'Release without date: {0}, skipping it', release['date'])
                continue
            release_date = self._make_date_values(release['date'])
            self._log.info(u'Is {0} > {1}?', oldest_release['year'], release_date['year'])
            if (oldest_release['year'] is None or
                    oldest_release['year'] > release_date['year']):
                oldest_release = release_date
            elif oldest_release['year'] == release_date['year']:
                if ('month' in release_date.keys() and
                        'month' in oldest_release.keys() and
                        oldest_release['month'] > release_date['month']):
                    oldest_release = release_date
        return (oldest_release, relation_type)

    def get_first_recording_year(self, mb_track_id):
        oldest_release = {'year': None, 'month': None, 'day': None}
        relation_type = None

        # Get recording by Id
        x = musicbrainzngs.get_recording_by_id(
                mb_track_id,
                includes=["artists","work-rels"]
                )
        originalArtist = x['recording']['artist-credit']

        if 'work-relation-list' not in x['recording']:
            self._log.info('No work relations! Please add them on MusicBrainz for {0}', x['recording'])
            return

        # Get all works that are songs
        songs = [work['work'] for work in x['recording']['work-relation-list'] if work['work']['type'] == 'Song']
        self._log.info(u'Songs: {0}', len(songs))

        for work in songs:
            self._log.info(u'Song: {0}', work)

        # Get Id of first song found
        songId = songs[0]['id']
        self._log.info(u'Song Id: {0}', songId)

        # Get all recordings for this song
        work = musicbrainzngs.get_work_by_id(songId, includes=["release-rels","recording-rels"])

        # Filter out recordings with a different author
        # To get the author it seems we have to fetch each recording individually...
        recordings = []
        for recordingRelation in work['work']['recording-relation-list']:
            recordingId = recordingRelation['recording']['id']
            recording = musicbrainzngs.get_recording_by_id(recordingId, includes=["artists","releases"])['recording']
            if(originalArtist == recording['artist-credit']):
                recordings.append(recording)
                break


        self._log.info('Filtered: ')
        for recording in recordings:
            self._log.info(u'Recording: {0}', recording)

        # If there's no recordings use already found one
        if(len(recordings) <= 0): recordings.append(x)

        # Assume first recording is the oldest
        oldestRecordingId = recordings[0]

        # Get releases for this recording
        releases = oldestRecordingId['release-list']

        oldestReleaseDate = datetime.date.today()

        for release in releases:
            releaseDate = parser.isoparse(release['date']).date()
            self._log.info(u'Release: {0}', releaseDate)
            if(releaseDate < oldestReleaseDate):
                oldestReleaseDate = releaseDate


        oldest_release = {'year': oldestReleaseDate.year, 'month': oldestReleaseDate.month, 'day': oldestReleaseDate.day}
        if(oldestReleaseDate == datetime.date.today()):
            self._log.error('Could not find date information for {0}',recording)
            oldest_release = {'year': None, 'month': None, 'day': None}
        return (oldest_release, relation_type)
