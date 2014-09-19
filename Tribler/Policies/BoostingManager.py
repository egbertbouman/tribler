# Written by Egbert Bouman

import os
import sys
import glob
import json
import urllib
import random
import HTMLParser
import libtorrent as lt

from hashlib import sha1
from traceback import print_exc
from collections import defaultdict

from Tribler.Core.Libtorrent.LibtorrentMgr import LibtorrentMgr
from Tribler.community.allchannel.community import AllChannelCommunity
from Tribler.community.channel.community import ChannelCommunity
from Tribler.Core.simpledefs import NTFY_TORRENTS, NTFY_UPDATE, NTFY_INSERT, DLSTATUS_SEEDING, NTFY_SCRAPE
from Tribler.Core.TorrentDef import TorrentDef, TorrentDefNoMetainfo
from Tribler.Core.DownloadConfig import DownloadStartupConfig
from Tribler.Main.globals import DefaultDownloadStartupConfig
from Tribler.Utilities.TimedTaskQueue import TimedTaskQueue
from Tribler.dispersy.util import call_on_reactor_thread
from Tribler.Utilities.scraper import scrape
from Tribler.Core.CacheDB.Notifier import Notifier

number_types = (int, long, float)


class BoostingManager:

    __single = None

    def __init__(self, session, utility=None, policy=None, src_interval=20, sw_interval=20, max_per_source=100, max_active=5):
        BoostingManager.__single = self

        self.session = session
        self.utility = utility
        self.notifier = Notifier.getInstance()
        self.ltmgr = LibtorrentMgr.getInstance()
        self.tqueue = TimedTaskQueue("BoostingManager")
        self.credit_mining_path = os.path.join(DefaultDownloadStartupConfig.getInstance().get_dest_dir(), "credit_mining")

        self.boosting_sources = {}

        self.torrents = {}

        self.max_torrents_per_source = max_per_source
        self.max_torrents_active = max_active

        self.source_interval = src_interval
        self.swarm_interval = sw_interval

        self.set_share_mode_params(share_mode_target=1)

        # SeederRatioPolicy is the default policy
        self.set_policy((policy or SeederRatioPolicy)(self.session))

        self.load()

        self.tqueue.add_task(self._select_torrent, self.swarm_interval)
        self.tqueue.add_task(self.scrape_trackers, 60)

    def get_instance(*args, **kw):
        if BoostingManager.__single is None:
            BoostingManager(*args, **kw)
        return BoostingManager.__single
    get_instance = staticmethod(get_instance)

    def del_instance(*args, **kw):
        BoostingManager.__single = None
    del_instance = staticmethod(del_instance)

    def shutdown(self):
        self.tqueue.shutdown(True)

    def load(self):
        if self.utility:
            try:
                string_to_source = lambda s: s.decode('hex') if len(s) == 40 and not (os.path.isdir(s) or s.startswith('http://')) else s
                for source in json.loads(self.utility.config.Read('boosting_sources')):
                    self.add_source(string_to_source(source))
                print >> sys.stderr, "BoostingManager: initial boosting sources", self.boosting_sources.keys()
            except:
                print >> sys.stderr, "BoostingManager: no initial boosting sources"

    def save(self):
        if self.utility:
            try:
                source_to_string = lambda s: s.encode('hex') if len(s) == 20 and not (os.path.isdir(s) or s.startswith('http://')) else s
                self.utility.write_config('boosting_sources', json.dumps([source_to_string(source) for source in self.boosting_sources.keys()]))
                print >> sys.stderr, "BoostingManager: saved sources", self.boosting_sources.keys()
            except:
                print >> sys.stderr, "BoostingManager: could not save state"
                print_exc()

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
            error = False
            args = (self.session, self.tqueue, source, self.source_interval, self.max_torrents_per_source, self.on_torrent_insert)
            if os.path.isdir(source):
                self.boosting_sources[source] = DirectorySource(*args)
            elif source.startswith('http://'):
                self.boosting_sources[source] = RSSFeedSource(*args)
            elif len(source) == 20:
                self.boosting_sources[source] = ChannelSource(*args)
            else:
                print >> sys.stderr, 'BoostingManager: got unknown source', source
                error = True
            if not error:
                self.save()
        else:
            print >> sys.stderr, 'BoostingManager: already have source', source

    def remove_source(self, source_key):
        if source_key in self.boosting_sources:
            source = self.boosting_sources.pop(source_key)
            source.kill_tasks()
            self.save()

    def on_torrent_insert(self, source, infohash, torrent):
        # Remember where we got this torrent from
        if os.path.isdir(source) or source.startswith('http://'):
            source_str = source
        elif len(source) == 20:
            source_str = source.encode('hex')
        else:
            source_str = 'unknown source'
        torrent['source'] = source_str

        if self.boosting_sources[source].archive:
            torrent['preload'] = True
            torrent['prio'] = 100

        # Preload the TorrentDef.
        if torrent['metainfo']:
            if not isinstance(torrent['metainfo'], TorrentDef):
                torrent['metainfo'] = TorrentDef.load(torrent['metainfo'])
        else:
            torrent['metainfo'] = TorrentDefNoMetainfo(infohash, torrent['name'])

        self.torrents[infohash] = torrent
        print >> sys.stderr, 'BoostingManager: got new torrent', infohash.encode('hex'), 'from', source_str

    def scrape_trackers(self):
        num_requests = 0
        trackers = defaultdict(list)

        for infohash, torrent in self.torrents.iteritems():
            if isinstance(torrent['metainfo'], TorrentDef):
                tdef = torrent['metainfo']
                for tracker in tdef.get_trackers_as_single_tuple():
                    trackers[tracker].append(infohash)
                num_requests += 1

        results = defaultdict(lambda: [0, 0])
        for tracker, infohashes in trackers.iteritems():
            try:
                reply = scrape(tracker, infohashes)
                print >> sys.stderr, 'BoostingManager: got reply from tracker', reply
            except:
                print >> sys.stderr, 'BoostingManager: did not get reply from tracker'
            else:
                for infohash, info in reply.iteritems():
                    results[infohash][0] = max(results[infohash][0], info['seeds'])
                    results[infohash][1] = max(results[infohash][1], info['peers'])

        for infohash, num_peers in results.iteritems():
            self.torrents[infohash]['num_seeders'] = num_peers[0]
            self.torrents[infohash]['num_leechers'] = num_peers[1]
            self.notifier.notify(NTFY_TORRENTS, NTFY_SCRAPE, infohash)

        print >> sys.stderr, 'BoostingManager: finished tracker scraping for %d torrent(s)' % num_requests

        self.tqueue.add_task(self.scrape_trackers, 1800)

    def set_archive(self, source, enable):
        if source in self.boosting_sources:
            self.boosting_sources[source].archive = enable
            print >> sys.stderr, 'BoostingManager: set archive mode for', source, 'to', str(enable)
        else:
            print >> sys.stderr, 'BoostingManager: could not set archive mode for', source

    def start_download(self, infohash, torrent):
        dscfg = DownloadStartupConfig()
        dscfg.set_dest_dir(self.credit_mining_path)

        preload = torrent.get('preload', False)
        torrent['download'] = self.session.lm.add(torrent['metainfo'], dscfg, pstate=torrent.get('pstate', None), hidden=True, share_mode=not preload)
        # TODO: fix this
        # torrent['download'].handle.set_priority(torrent.get('prio', 1))
        print >> sys.stderr, 'BoostingManager: downloading torrent', infohash.encode('hex'), '(preload=%s)' % preload

    def stop_download(self, infohash, torrent):
        preload = torrent.pop('preload', False)
        download = torrent.pop('download')
        torrent['pstate'] = {'engineresumedata': download.handle.write_resume_data()}
        self.session.remove_download(download)
        print >> sys.stderr, 'BoostingManager: removing torrent', infohash.encode('hex'), '(preload=%s)' % preload

    def _select_torrent(self):
        torrents = {}
        for infohash, torrent in self.torrents.iteritems():
            if torrent.get('preload', False):
                if not torrent.has_key('download'):
                    self.start_download(infohash, torrent)
                elif torrent['download'].get_status() == DLSTATUS_SEEDING:
                    self.stop_download(infohash, torrent)
            else:
                torrents[infohash] = torrent

        if self.policy and torrents:

            print >> sys.stderr, 'BoostingManager: selecting from', len(torrents), 'torrents'

            # Determine which torrent to start and which to stop.
            infohash_start, infohash_stop = self.policy.apply(torrents, self.max_torrents_active)

            # Start a torrent.
            if infohash_start:
                torrent = torrents[infohash_start]

                # Add the download to libtorrent.
                self.start_download(infohash_start, torrent)

            # Stop a torrent.
            if infohash_stop:
                torrent = torrents[infohash_stop]

                self.stop_download(infohash_stop, torrent)

        self.tqueue.add_task(self._select_torrent, self.swarm_interval)


class BoostingSource:

    def __init__(self, session, tqueue, source, interval, max_torrents, callback):
        self.session = session
        self.tqueue = tqueue

        self.torrents = {}
        self.source = source
        self.interval = interval
        self.max_torrents = max_torrents
        self.callback = callback
        self.archive = False

    def kill_tasks(self):
        self.tqueue.remove_task(self.source)

    def _load(self, source):
        pass

    def _update(self):
        pass


class ChannelSource(BoostingSource):

    def __init__(self, session, tqueue, dispersy_cid, interval, max_torrents, callback):
        BoostingSource.__init__(self, session, tqueue, dispersy_cid, interval, max_torrents, callback)

        self.channelcast_db = self.session.lm.channelcast_db

        self.community = None
        self.database_updated = True

        self.session.add_observer(self._on_database_updated, NTFY_TORRENTS, [NTFY_INSERT, NTFY_UPDATE])
        self.tqueue.add_task(lambda cid=dispersy_cid: self._load(cid), 0, id=self.source)

    def kill_tasks(self):
        BoostingSource.kill_tasks(self)
        self.session.remove_observer(self._on_database_updated)

    def _load(self, dispersy_cid):
        dispersy = self.session.get_dispersy_instance()

        @call_on_reactor_thread
        def join_community():
            try:
                self.community = dispersy.get_community(dispersy_cid, True)
                self.tqueue.add_task(get_channel_id, 0, id=self.source)

            except KeyError:

                allchannelcommunity = None
                for community in dispersy.get_communities():
                    if isinstance(community, AllChannelCommunity):
                        allchannelcommunity = community
                        break

                if allchannelcommunity:
                    self.community = ChannelCommunity.init_community(dispersy, dispersy.get_member(mid=dispersy_cid), allchannelcommunity._my_member, True)
                    print >> sys.stderr, 'ChannelSource: joined channel community', dispersy_cid.encode("HEX")
                    self.tqueue.add_task(get_channel_id, 0, id=self.source)
                else:
                    print >> sys.stderr, 'ChannelSource: could not find AllChannelCommunity'

        def get_channel_id():
            if self.community and self.community._channel_id:
                self.channel_id = self.community._channel_id
                self.tqueue.add_task(self._update, 0, id=self.source)
                print >> sys.stderr, 'ChannelSource: got channel id', self.channel_id
            else:
                print >> sys.stderr, 'ChannelSource: could not get channel id, retrying in 10s..'
                self.tqueue.add_task(get_channel_id, 10, id=self.source)

        join_community()

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

            self.tqueue.add_task(self._update, self.interval, id=self.source)

    def _on_database_updated(self, subject, change_type, infohash):
        self.database_updated = True


class RSSFeedSource(BoostingSource):

    def __init__(self, session, tqueue, rss_feed, interval, max_torrents, callback):
        BoostingSource.__init__(self, session, tqueue, rss_feed, interval, max_torrents, callback)

        self.ltmgr = LibtorrentMgr.getInstance()
        self.unescape = HTMLParser.HTMLParser().unescape

        self.feed_handle = None

        self.tqueue.add_task(lambda feed=rss_feed: self._load(feed), 0, id=self.source)

    def _load(self, rss_feed):
        self.feed_handle = self.ltmgr.ltsession.add_feed({'url': rss_feed, 'auto_download': False, 'auto_map_handles': False})

        def wait_for_feed():
            # Wait until the RSS feed is longer updating.
            feed_status = self.feed_handle.get_feed_status()
            if feed_status['updating']:
                self.tqueue.add_task(wait_for_feed, 1, id=self.source)
            elif len(feed_status['error']) > 0:
                print >> sys.stderr, 'RSSFeedSource: got error for RSS feed', feed_status['url'], '(', feed_status['error'], ')'
            else:
                # The feed is done updating. Now periodically start retrieving torrents.
                self.tqueue.add_task(self._update, 0, id=self.source)
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
                    torrent_filename = os.path.join(BoostingManager.get_instance().credit_mining_path, 'rss-%s.torrent' % infohash.encode('hex'))
                    if not os.path.exists(torrent_filename):
                        try:
                            # Download the torrent and create a TorrentDef.
                            f = urllib.urlopen(self.unescape(item['url']))
                            metainfo = lt.bdecode(f.read())
                            tdef = TorrentDef.load_from_dict(metainfo)
                            tdef.save(torrent_filename)
                        except:
                            print >> sys.stderr, 'RSSFeedSource: could not get torrent, skipping', item['url']
                            continue
                    else:
                        tdef = TorrentDef.load(torrent_filename)
                    # Create a torrent dict.
                    torrent_values = [item['title'], tdef, tdef.get_creation_date(), tdef.get_length(), len(tdef.get_files()), -1, -1]
                    self.torrents[infohash] = dict(zip(torrent_keys, torrent_values))
                    # Notify the BoostingManager and provide the real infohash.
                    if self.callback:
                        self.callback(self.source, tdef.get_infohash(), self.torrents[infohash])

            self.tqueue.add_task(self._update, self.interval, id=self.source)


class DirectorySource(BoostingSource):

    def __init__(self, session, tqueue, directory, interval, max_torrents, callback):
        BoostingSource.__init__(self, session, tqueue, directory, interval, max_torrents, callback)

        self._load(directory)

    def _load(self, directory):
        if os.path.isdir(directory):
            self.tqueue.add_task(self._update, 0, id=self.source)
            print >> sys.stderr, 'DirectorySource: got directory', directory
        else:
            print >> sys.stderr, 'DirectorySource: could not find directory', directory

    def _update(self):
        if len(self.torrents) < self.max_torrents:

            torrent_keys = ['name', 'metainfo', 'creation_date', 'length', 'num_files', 'num_seeders', 'num_leechers']

            for torrent_filename in glob.glob(self.source + '/*.torrent'):
                if torrent_filename not in self.torrents:
                    try:
                        tdef = TorrentDef.load(torrent_filename)
                    except:
                        print >> sys.stderr, 'DirectorySource: could not load torrent, skipping', torrent_filename
                        continue
                    # Create a torrent dict.
                    torrent_values = [tdef.get_name_as_unicode(), tdef, tdef.get_creation_date(), tdef.get_length(), len(tdef.get_files()), -1, -1]
                    self.torrents[torrent_filename] = dict(zip(torrent_keys, torrent_values))
                    # Notify the BoostingManager.
                    if self.callback:
                        self.callback(self.source, tdef.get_infohash(), self.torrents[torrent_filename])

            self.tqueue.add_task(self._update, self.interval, id=self.source)


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
        key_check = lambda v: isinstance(v['num_seeders'], number_types) and isinstance(v['num_leechers'], number_types) and v['num_seeders'] + v['num_leechers'] > 0
        return BoostingPolicy.apply(self, torrents_eligible, torrents_active, key, key_check)
