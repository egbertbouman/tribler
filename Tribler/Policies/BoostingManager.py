# Written by Egbert Bouman

import os
import sys
import urllib
import random

from hashlib import sha1
from collections import defaultdict

from Tribler.Core.Libtorrent.LibtorrentMgr import LibtorrentMgr
from Tribler.community.allchannel.community import AllChannelCommunity
from Tribler.community.channel.community import ChannelCommunity
from Tribler.Core.simpledefs import NTFY_TORRENTS, NTFY_UPDATE, NTFY_INSERT
from Tribler.Core.TorrentDef import TorrentDef, TorrentDefNoMetainfo
from Tribler.Core.DownloadConfig import DownloadStartupConfig
from Tribler.Main.globals import DefaultDownloadStartupConfig
from Tribler.TrackerChecking.TrackerChecking import singleTrackerStatus

CREDIT_MINING_PATH = os.path.join(DefaultDownloadStartupConfig.getInstance().get_dest_dir(), "credit_mining")

DEBUG = False


class BoostingManager:

    def __init__(self, session, policy=None, db_interval=20, sw_interval=20, max_per_source=100, max_active=5):
        self.session = session
        self.lt_mgr = LibtorrentMgr.getInstance()

        self.boosting_sources = {}

        self.torrents = {}

        self.max_torrents_per_source = max_per_source
        self.max_torrents_active = max_active

        self.database_interval = db_interval
        self.swarm_interval = sw_interval

        # SeederRatioPolicy is the default policy
        self.set_policy((policy or SeederRatioPolicy)(self.session))

        self.session.lm.rawserver.add_task(self._select_torrent, self.swarm_interval)
        self.session.lm.rawserver.add_task(self.scrape_trackers, 60)

    def set_policy(self, policy):
        self.policy = policy

    def set_share_mode_params(self, share_mode_target=None, share_mode_bandwidth=None, share_mode_download=None, share_mode_seeders=None):
        settings = self.ltmgr.ltsession.settings()
        if share_mode_target != None:
            settings.share_mode_target = share_mode_target
        if share_mode_bandwidth != None:
            settings.share_mode_bandwidth = share_mode_bandwidth
        if share_mode_download != None:
            settings.share_mode_download = share_mode_download
        if share_mode_seeders != None:
            settings.share_mode_seeders = share_mode_seeders
        self.ltmgr.ltsession.set_settings(settings)

    def add_source(self, source):
        if source not in self.boosting_sources:
            if source.startswith('http://'):
                self.boosting_sources[source] = RSSFeedSource(self.session, source, self.database_interval, self.max_torrents_per_source, self.on_torrent_insert)
            elif len(source) == 20:
                self.boosting_sources[source] = ChannelSource(self.session, source, self.database_interval, self.max_torrents_per_source, self.on_torrent_insert)
            else:
                print >> sys.stderr, 'BoostingManager: got unknown source', source
        else:
            print >> sys.stderr, 'BoostingManager: already have source', source

    def remove_source(self, source_key):
        if source_key in self.boosting_sources:
            source = self.boosting_sources.pop(source_key)
            source.kill_tasks()

    def on_torrent_insert(self, source, infohash, torrent):
        self.torrents[infohash] = torrent

        if source.startswith('http://'):
            source_str = source
        elif len(source) == 20:
            source_str = source.encode('hex')
        else:
            source_str = 'unknown source'
        self.torrents[infohash]['source'] = source_str

        print >> sys.stderr, 'BoostingManager: got new torrent', infohash.encode('hex'), 'from', source_str

    def scrape_trackers(self):
        tracker_to_torrent = defaultdict(list)
        for infohash, torrent in self.torrents.iteritems():
            if isinstance(torrent['metainfo'], TorrentDef):
                for tracker in torrent['metainfo'].get_trackers_as_single_tuple():
                    tracker_to_torrent[tracker].append(infohash)

        results = defaultdict(lambda: [0, 0])
        for tracker, infohashes in tracker_to_torrent.iteritems():
            tracker_status = singleTrackerStatus({'infohash': infohashes[0]}, tracker, lambda t: tracker_to_torrent[t])
            for infohash, num_peers in tracker_status.iteritems():
                results[infohash][0] = max(results[infohash][0], num_peers[0])
                results[infohash][1] = max(results[infohash][1], num_peers[1])
            print >> sys.stderr, 'BoostingManager: got reply from tracker', tracker_status

        for infohash, num_peers in results.iteritems():
            self.torrents[infohash]['num_seeders'] = num_peers[0]
            self.torrents[infohash]['num_leechers'] = num_peers[1]

        self.session.lm.rawserver.add_task(self.scrape_trackers, 1800)

    def _select_torrent(self):
        if self.policy:

            print >> sys.stderr, 'BoostingManager: selecting from', len(self.torrents), 'torrents'

            # Determine which torrent to start and which to stop.
            infohash_start, infohash_stop = self.policy.apply(self.torrents, self.max_torrents_active)

            # Start a torrent.
            if infohash_start:
                torrent = self.torrents[infohash_start]

                # Load the TorrentDef.
                if torrent['metainfo']:
                    if isinstance(torrent['metainfo'], TorrentDef):
                        tdef = torrent['metainfo']
                    else:
                        tdef = TorrentDef.load(torrent['metainfo'])
                else:
                    tdef = TorrentDefNoMetainfo(infohash_start, torrent['name'])

                # Add the download to libtorrent.
                dscfg = DownloadStartupConfig()
                dscfg.set_dest_dir(CREDIT_MINING_PATH)
                torrent['download'] = self.session.lm.add(tdef, dscfg, pstate=torrent.get('pstate', None), hidden=True, share_mode=True)
                print >> sys.stderr, 'BoostingManager: downloading torrent', infohash_start.encode('hex')

            # Stop a torrent.
            if infohash_stop:
                torrent = self.torrents[infohash_stop]
                download = torrent.pop('download')
                torrent['pstate'] = {'engineresumedata': download.handle.write_resume_data()}
                self.session.remove_download(download)
                print >> sys.stderr, 'BoostingManager: removing torrent', infohash_stop.encode('hex')

        self.session.lm.rawserver.add_task(self._select_torrent, self.swarm_interval)


class BoostingSource:

    def __init__(self, session, source, db_interval, max_torrents, callback):
        self.session = session

        self.torrents = {}
        self.source = source
        self.database_interval = db_interval
        self.max_torrents = max_torrents
        self.callback = callback

    def kill_tasks(self):
        self.session.lm.rawserver.kill_tasks(self.source)

    def _set_source(self, source):
        pass

    def _update(self):
        pass


class ChannelSource(BoostingSource):

    def __init__(self, session, dispersy_cid, db_interval, max_torrents, callback):
        BoostingSource.__init__(self, session, dispersy_cid, db_interval, max_torrents, callback)

        self.channelcast_db = self.session.lm.channelcast_db

        self.community = None
        self.database_updated = True

        self.session.add_observer(self._on_database_updated, NTFY_TORRENTS, [NTFY_INSERT, NTFY_UPDATE])
        self.session.lm.rawserver.add_task(lambda cid=dispersy_cid: self._set_source(cid), 0, id=self.source)

    def kill_tasks(self):
        BoostingSource.kill_tasks(self)
        self.session.remove_observer(self._on_database_updated)

    def _set_source(self, dispersy_cid):
        dispersy = self.session.get_dispersy_instance()

        def join_community():
            try:
                self.community = dispersy.get_community(dispersy_cid, True)
                self.session.lm.rawserver.add_task(get_channel_id, 0, id=self.source)

            except KeyError:

                allchannelcommunity = None
                for community in dispersy.get_communities():
                    if isinstance(community, AllChannelCommunity):
                        allchannelcommunity = community
                        break

                if allchannelcommunity:
                    self.community = ChannelCommunity.join_community(dispersy, dispersy.get_temporary_member_from_id(dispersy_cid), allchannelcommunity._my_member, True)
                    print >> sys.stderr, 'ChannelSource: joined channel community', dispersy_cid.encode("HEX")
                    self.session.lm.rawserver.add_task(get_channel_id, 0, id=self.source)
                else:
                    print >> sys.stderr, 'ChannelSource: could not find AllChannelCommunity'

        def get_channel_id():
            if self.community and self.community._channel_id:
                self.channel_id = self.community._channel_id
                self.session.lm.rawserver.add_task(self._update, 0, id=self.source)
                print >> sys.stderr, 'ChannelSource: got channel id', self.channel_id
            else:
                print >> sys.stderr, 'ChannelSource: could not get channel id, retrying in 10s..'
                self.session.lm.rawserver.add_task(get_channel_id, 10, id=self.source)

        dispersy.callback.call(join_community)

    def _update(self):
        if len(self.torrents) < self.max_torrents:

            if self.database_updated:
                infohashes_old = set(self.torrents.keys())

                torrent_keys_db = ['infohash', 'Torrent.name', 'torrent_file_name', 'creation_date', 'length', 'num_files', 'num_seeders', 'num_leechers']
                torrent_keys_dict = ['infohash', 'name', 'metainfo', 'creation_date', 'length', 'num_files', 'num_seeders', 'num_leechers']
                torrent_values = self.channelcast_db.getTorrentsFromChannelId(self.channel_id, True, torrent_keys_db, self.max_torrents)
                self.torrents = dict((torrent[0], dict(zip(torrent_keys_dict[1:], torrent[1:]))) for torrent in torrent_values)

                infohashes_new = set(self.torrents.keys())
                for infohash in infohashes_new - infohashes_old:
                    if self.callback:
                        self.callback(self.source, infohash, self.torrents[infohash])

                self.database_updated = False

            self.session.lm.rawserver.add_task(self._update, self.database_interval, id=self.source)

    def _on_database_updated(self, subject, change_type, infohash):
        self.database_updated = True


class RSSFeedSource(BoostingSource):

    def __init__(self, session, rss_feed, db_interval, max_torrents, callback):
        BoostingSource.__init__(self, session, rss_feed, db_interval, max_torrents, callback)

        self.ltmgr = LibtorrentMgr.getInstance()

        self.feed_handle = None

        self.session.lm.rawserver.add_task(lambda feed=rss_feed: self._set_source(feed), 0, id=self.source)

    def _set_source(self, rss_feed):
        self.feed_handle = self.ltmgr.ltsession.add_feed({'url': rss_feed, 'auto_download': False, 'auto_map_handles': False})

        def wait_for_feed():
            # Wait until the RSS feed is longer updating.
            feed_status = self.feed_handle.get_feed_status()
            if feed_status['updating']:
                self.session.lm.rawserver.add_task(wait_for_feed, 1, id=self.source)
            elif len(feed_status['error']) > 0:
                print >> sys.stderr, 'RSSFeedSource: got error for RSS feed', feed_status['url'], '(', feed_status['error'], ')'
            else:
                # The feed is done updating. Now periodically start retrieving torrents.
                self.session.lm.rawserver.add_task(self._update, 0, id=self.source)
                print >> sys.stderr, 'RSSFeedSource: got RSS feed', feed_status['url']

        wait_for_feed()

    def _update(self):
        if len(self.torrents) < self.max_torrents:

            feed_status = self.feed_handle.get_feed_status()

            torrent_keys = ['name', 'metainfo', 'creation_date', 'length', 'num_files', 'num_seeders', 'num_leechers']

            for item in feed_status['items']:
                # Not all RSS feeds provide us with the infohash, so we use a fake infohash based on the URL to identify the torrents.
                infohash = sha1(item['url']).digest()
                if infohash not in self.torrents:
                    # Store the torrents as rss-infohash_as_hex.torrent.
                    torrent_filename = os.path.join(CREDIT_MINING_PATH, 'rss-%s.torrent' % infohash.encode('hex'))
                    if not os.path.exists(torrent_filename):
                        urllib.urlretrieve(item['url'], torrent_filename)
                    # Load the torrent from disk and create a torrent dict.
                    tdef = TorrentDef.load(torrent_filename)
                    torrent_values = [item['title'], tdef, tdef.get_creation_date(), tdef.get_length(), len(tdef.get_files()), -1, -1]
                    self.torrents[infohash] = dict(zip(torrent_keys, torrent_values))
                    # Notify the BoostingManager and provide the real infohash.
                    if self.callback:
                        self.callback(self.source, tdef.get_infohash(), self.torrents[infohash])

            self.session.lm.rawserver.add_task(self._update, self.database_interval, id=self.source)


class BoostingPolicy:

    def __init__(self, session):
        self.session = session

    def apply(self, torrents, max_active, key, key_check):
        eligible_and_active = {}
        eligible_not_active = {}
        for k, v in torrents.iteritems():
            download = self.session.get_download(k)
            if download and download.get_share_mode():
                eligible_and_active[k] = v
            elif not download:
                eligible_not_active[k] = v

        # Determine which download to start.
        sorted_list = sorted([(key(v), k) for k, v in eligible_not_active.iteritems() if key_check(v)])
        infohash_start = sorted_list[0][1] if sorted_list else None

        # Determine which download to stop.
        if infohash_start:
            eligible_and_active[infohash_start] = torrents[infohash_start]
        sorted_list = sorted([(key(v), k) for k, v in eligible_and_active.iteritems() if key_check(v)])
        infohash_stop = sorted_list[-1][1] if sorted_list and len(eligible_and_active) > max_active else None

        return (infohash_start, infohash_stop) if infohash_start != infohash_stop else (None, None)


class RandomPolicy(BoostingPolicy):

    def apply(self, torrents_eligible, torrents_active):
        key = lambda v: random.random()
        key_check = lambda v: True
        return BoostingPolicy.apply(self, torrents_eligible, torrents_active, key, key_check)


class CreationDatePolicy(BoostingPolicy):

    def apply(self, torrents_eligible, torrents_active):
        key = lambda v: v['creation_date']
        key_check = lambda v: v['creation_date'] > 0
        return BoostingPolicy.apply(self, torrents_eligible, torrents_active, key, key_check)


class SeederRatioPolicy(BoostingPolicy):

    def apply(self, torrents_eligible, torrents_active):
        key = lambda v: v['num_seeders'] / float(v['num_seeders'] + v['num_leechers'])
        key_check = lambda v: isinstance(v['num_seeders'], int) and isinstance(v['num_leechers'], int) and v['num_seeders'] + v['num_leechers'] > 0
        return BoostingPolicy.apply(self, torrents_eligible, torrents_active, key, key_check)
