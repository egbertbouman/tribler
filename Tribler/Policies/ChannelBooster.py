# Written by Egbert Bouman

import os
import sys
import time

from Tribler.Core.Libtorrent.LibtorrentMgr import LibtorrentMgr
from Tribler.community.allchannel.community import AllChannelCommunity
from Tribler.community.channel.community import ChannelCommunity
from Tribler.TrackerChecking.TorrentChecking import TorrentChecking
from Tribler.Core.simpledefs import NTFY_TORRENTS, NTFY_UPDATE, NTFY_INSERT
from Tribler.Core.TorrentDef import TorrentDef, TorrentDefNoMetainfo
from Tribler.Core.DownloadConfig import DownloadStartupConfig
from Tribler.Main.globals import DefaultDownloadStartupConfig

MAX_TORRENTS_ELIGIBLE = 100
MAX_TORRENTS_ACTIVE = 5

ET_UPDATE_INTERVAL = 20
AT_UPDATE_INTERVAL = 20

DEBUG = False


class ChannelBooster:

    def __init__(self, session, dispersy_cid):
        self.session = session
        self.votecast_db = self.session.lm.votecast_db
        self.channelcast_db = self.session.lm.channelcast_db

        self.lt_mgr = LibtorrentMgr.getInstance()
        self.torrent_checking = TorrentChecking.getInstance()

        self.torrents_eligible = {}
        self.torrents_active = {}

        self.community = None

        self.SetPolicy(SeederRatioPolicy(self.session))

        self.session.add_observer(self.OnTorrentUpdate, NTFY_TORRENTS, [NTFY_UPDATE])
        self.session.add_observer(self.OnTorrentInsert, NTFY_TORRENTS, [NTFY_INSERT])

        self.session.lm.rawserver.add_task(lambda cid=dispersy_cid: self.SetChannel(cid), 0)

        self.session.lm.rawserver.add_task(self.UpdateActiveTorrents, AT_UPDATE_INTERVAL)

    def SetChannel(self, dispersy_cid):
        # TODO: when SetChannel has been called before we should kill old tasks on rawserver.

        dispersy = self.session.get_dispersy_instance()

        def join_community():
            try:
                self.community = dispersy.get_community(dispersy_cid, True)
                self.session.lm.rawserver.add_task(get_channel_id, 0)

            except KeyError:

                allchannelcommunity = None
                for community in dispersy.get_communities():
                    if isinstance(community, AllChannelCommunity):
                        allchannelcommunity = community
                        break

                if allchannelcommunity:
                    self.community = ChannelCommunity.join_community(dispersy, dispersy.get_temporary_member_from_id(dispersy_cid), allchannelcommunity._my_member, True)
                    print >> sys.stderr, 'ChannelBooster: joined channel community', dispersy_cid.encode("HEX")
                    self.session.lm.rawserver.add_task(get_channel_id, 0)
                else:
                    print >> sys.stderr, 'ChannelBooster: could not find AllChannelCommunity'

        def get_channel_id():
            if self.community and self.community._channel_id:
                self.channel_id = self.community._channel_id
                print >> sys.stderr, 'ChannelBooster: got channel id', self.channel_id
                self.session.lm.rawserver.add_task(self.UpdateEligibleTorrents, 10)
            else:
                print >> sys.stderr, 'ChannelBooster: could not get channel id, retrying in 10s..'
                self.session.lm.rawserver.add_task(get_channel_id, 10)

        dispersy.callback.call(join_community)

    def SetShareModeParams(self, share_mode_target=None, share_mode_bandwidth=None, share_mode_download=None, share_mode_seeders=None):
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

    def SetPolicy(self, policy):
        self.policy = policy

    def OnTorrentUpdate(self, subject, changeType, infohash):
        if infohash in self.torrents_eligible and len(self.torrents_eligible) == MAX_TORRENTS_ELIGIBLE:
            self.UpdateEligibleTorrents()

    def OnTorrentInsert(self, subject, changeType, infohash):
        # TODO: trigger UpdateEligibleTorrent from here, to avoid unneeded DB calls.
        pass

    def UpdateActiveTorrents(self):
        if self.policy and len(self.torrents_eligible) > len(self.torrents_active):

            # Determine which torrent to add and which to remove
            infohash_add, infohash_remove = self.policy.apply(self.torrents_eligible, self.torrents_active) if self.policy else (None, None)

            # Add a torrent
            if infohash_add:
                torrent = self.torrents_eligible[infohash_add]

                if torrent['torrent_file_name']:
                    tdef = TorrentDef.load(torrent['torrent_file_name'])
                else:
                    tdef = TorrentDefNoMetainfo(infohash_add, torrent['Torrent.name'])

                dscfg = DownloadStartupConfig()
                dscfg.set_dest_dir(os.path.join(DefaultDownloadStartupConfig.getInstance().get_dest_dir(), "credit_mining"))
                self.torrents_active[infohash_add] = self.session.start_download(tdef, dscfg, hidden=True, share_mode=True)
                print >> sys.stderr, 'ChannelBooster: downloading torrent', infohash_add.encode('hex')

            # Delete a torrent
            if infohash_remove and len(self.torrents_active) > MAX_TORRENTS_ACTIVE:
                download = self.torrents_active[infohash_remove]
                self.session.remove_download(download)
                self.torrents_active.pop(infohash_remove)
                print >> sys.stderr, 'ChannelBooster: removing torrent', infohash_remove.encode('hex')

        self.session.lm.rawserver.add_task(self.UpdateActiveTorrents, AT_UPDATE_INTERVAL)

    def UpdateEligibleTorrents(self):
        if len(self.torrents_eligible) < MAX_TORRENTS_ELIGIBLE:

            infohashes_old = set(self.torrents_eligible.keys())

            torrent_keys = ['infohash', 'Torrent.name', 'torrent_file_name', 'creation_date', 'length', 'num_files', 'num_seeders', 'num_leechers']
            torrent_values = self.channelcast_db.getTorrentsFromChannelId(self.channel_id, True, torrent_keys, MAX_TORRENTS_ELIGIBLE)
            self.torrents_eligible = dict((torrent[0], dict(zip(torrent_keys[1:], torrent[1:]))) for torrent in torrent_values)

            infohashes_new = set(self.torrents_eligible.keys())
            for infohash in infohashes_new - infohashes_old:
                print >> sys.stderr, 'ChannelBooster: got new torrent', infohash.encode('hex')
                self.torrent_checking.addToQueue(infohash)

            print >> sys.stderr, 'ChannelBooster: got', len(self.torrents_eligible), 'eligible torrents'
            self.session.lm.rawserver.add_task(self.UpdateEligibleTorrents, ET_UPDATE_INTERVAL)


class BoostingPolicy:

    def __init__(self, session):
        self.session = session

    def apply(self, torrents_eligible, torrents_active, key, key_check):
        eligible_and_active = {}
        eligible_not_active = {}
        for k, v in torrents_eligible.iteritems():
            if k in torrents_active:
                eligible_and_active[k] = v
            else:
                eligible_not_active[k] = v

        # Determine which download to add to torrents_active
        sorted_list = sorted([(key(v), k) for k, v in eligible_not_active.iteritems() if key_check(v) and not self.session.get_download(k)])
        infohash_add = sorted_list[0][1] if sorted_list else None

        # Determine which download to remove from torrents_active
        sorted_list = sorted([(key(v), k) for k, v in eligible_and_active.iteritems() if key_check(v) and self.session.get_download(k)])
        infohash_remove = sorted_list[-1][1] if sorted_list else None

        return (infohash_add, infohash_remove)


class CreationDatePolicy(BoostingPolicy):

    def apply(self, torrents_eligible, torrents_active):
        key = lambda v: v['creation_date']
        key_check = lambda v: v['creation_date'] > 0
        return BoostingPolicy.apply(self, torrents_eligible, torrents_active, key, key_check)


class SeederRatioPolicy(BoostingPolicy):

    def apply(self, torrents_eligible, torrents_active):
        key = lambda v: v['num_seeders'] / float(v['num_seeders'] + v['num_leechers'])
        key_check = lambda v: v['num_seeders'] != None and v['num_leechers'] != None and v['num_seeders'] + v['num_leechers'] != 0
        return BoostingPolicy.apply(self, torrents_eligible, torrents_active, key, key_check)
