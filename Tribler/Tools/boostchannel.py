# Written by Egbert Bouman

import sys
import time
import shutil
import random
import tempfile
from traceback import print_exc

from Tribler.Core.Session import Session
from Tribler.Core.SessionConfig import SessionStartupConfig
from Tribler.Policies.ChannelBooster import ChannelBooster
from Tribler.community.channel.community import ChannelCommunity
from Tribler.community.channel.preview import PreviewChannelCommunity
from Tribler.community.allchannel.community import AllChannelCommunity


def main():
    args = sys.argv

    if not args:
        print "Usage: python boostchannel.py dispersy_cid"
        sys.exit()
    elif len(args) != 2 or not len(args[1]) == 40:
        print "Invalid arguments"
        sys.exit(2)
    else:
        dispersy_cid = args[1].decode('hex')

    print "Press Ctrl-C to stop boosting this channel"

    statedir = tempfile.mkdtemp()

    config = SessionStartupConfig()
    config.set_state_dir(statedir)
    config.set_listen_port(random.randint(10000, 60000))
    config.set_torrent_checking(False)
    config.set_multicast_local_peer_discovery(False)
    config.set_megacache(True)
    config.set_dispersy(True)
    config.set_swift_proc(False)
    config.set_mainline_dht(False)
    config.set_torrent_collecting(False)
    config.set_libtorrent(True)
    config.set_dht_torrent_collecting(False)

    s = Session(config)
    s.start()

    while not s.lm.initComplete:
        time.sleep(1)

    def load_communities():
        dispersy.define_auto_load(AllChannelCommunity, (s.dispersy_member,), load=True)
        dispersy.define_auto_load(ChannelCommunity, load=True)
        dispersy.define_auto_load(PreviewChannelCommunity)
        print >> sys.stderr, "Dispersy communities are ready"

    dispersy = s.get_dispersy_instance()
    dispersy.callback.call(load_communities)

    cb = ChannelBooster(s, dispersy_cid)

    try:
        while True:
            time.sleep(sys.maxsize / 2048)
    except:
        print_exc()

    s.shutdown()
    time.sleep(3)
    shutil.rmtree(statedir)


if __name__ == "__main__":
    main()
