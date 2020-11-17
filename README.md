# beets-oldestdate
Beets plugin that fetches oldest recording or release date for each track. Originally based on `beets-recordingdate` by tweitzel.

# Installation
Clone repo and run `python setup.py install`

# Configuration
    auto:       Will run during an import operation if set to yes
    force:      Re-process songs that have already been run through the plugin
    overwrite_year: Also write to the year tag, erasing the original value 
    filter_recordings: Skip recordings with attributes before processing them. Reduces total API requests
    approach: What method to use to look through for dates. See below for details
              recordings: Only check through the recordings associated with the work.
                          Few API requests but often has missing or inaccurate data.
              releases: Go through releases for each recording.
                        Many API requests but a lot more accurate.
              hybrid: Go through releases only if no recordings have a date.
              both: Go through both recordings and releases.
              
## Default Configuration
    oldestdate:
        auto: True
        force: False
        overwrite_year: False
        filter_recordings: True
        approach: hybrid
