import argparse
import os
import time
from binascii import hexlify
from pathlib import Path

from ipv8.taskmanager import TaskManager
from ipv8.lazy_community import lazy_wrapper, lazy_wrapper_wd

from tribler.core.components.ipv8.ipv8_component import Ipv8Component
from tribler.core.components.key.key_component import KeyComponent
from tribler.core.components.restapi.restapi_component import RESTComponent
from tribler.core.components.tunnel.tunnel_component import TunnelsComponent
from tribler.core.components.content_discovery.content_discovery_component import ContentDiscoveryComponent
from tribler.core.components.content_discovery.community.payload import TorrentsHealthPayload, SelectResponsePayload
from tribler.core.components.torrent_checker.torrent_checker_component import TorrentCheckerComponent
from tribler.core.components.libtorrent.libtorrent_component import LibtorrentComponent
from tribler.core.components.socks_servers.socks_servers_component import SocksServersComponent
from tribler.core.components.torrent_checker.torrent_checker.dataclasses import HealthInfo
from tribler.core.components.database.database_component import DatabaseComponent
from tribler.core.components.database.db.store import ObjState
from tribler.core.components.database.db.serialization import CHANNEL_TORRENT, COLLECTION_NODE, REGULAR_TORRENT
from tribler.core.utilities.pony_utils import run_threaded
from tribler.core.utilities.tiny_tribler_service import TinyTriblerService

EXPERIMENT_RUN_TIME = int(os.environ.get('EXPERIMENT_RUN_TIME', 600))


class Service(TinyTriblerService, TaskManager):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs,
                         components=[Ipv8Component(), KeyComponent(), RESTComponent(),
                                     TunnelsComponent(), DatabaseComponent(), ContentDiscoveryComponent(),
                                     TorrentCheckerComponent(), LibtorrentComponent(),
                                     SocksServersComponent()])
        TaskManager.__init__(self)
        self.config.dht.enabled = True
        self.start = time.time()
        self.status = {'random': set(),
                       'checked': set(),
                       'preview': set()}
        self.register_task('_graceful_shutdown', self._graceful_shutdown, delay=EXPERIMENT_RUN_TIME)

    def _graceful_shutdown(self):
        task = self.async_group.add_task(self.on_tribler_shutdown())
        task.add_done_callback(lambda result: TinyTriblerService._graceful_shutdown(self))

    async def on_tribler_shutdown(self):
        await self.shutdown_task_manager()

    def update_results(self):
        with open('torrent_collecting.txt', 'a') as f:
            f.write(f"{time.time() - self.start} {len(self.status['random'])} {len(self.status['checked'])} {len(self.status['preview'])}\n")

    async def on_tribler_started(self):
        print(f'Using statedir {self.session.config.state_dir}')
        self.content = self.session.get_instance(ContentDiscoveryComponent).community

        with open('torrent_collecting.txt', 'w') as f:
            f.write("Time Random-torrents Checked-torrents Preview-torrents\n")
        self.update_results()

        @lazy_wrapper(TorrentsHealthPayload)
        async def on_torrents_health(community, peer, payload):
            health_tuples = payload.random_torrents + payload.torrents_checked
            health_list = [HealthInfo(infohash, last_check=last_check, seeders=seeders, leechers=leechers)
                           for infohash, seeders, leechers, last_check in health_tuples]

            random = [t[0] for t in payload.random_torrents]
            checked = [t[0] for t in payload.torrents_checked]

            def on_collected(_, processing_results):
                for result in processing_results:
                    if result.obj_state == ObjState.NEW_OBJECT:
                        infohash = result.md_obj.infohash
                        if infohash in checked:
                            self.status['checked'].add(infohash)
                        elif infohash in random:
                            self.status['random'].add(infohash)
                        self.update_results()

            for infohash in await run_threaded(community.composition.metadata_store.db,
                                               community.process_torrents_health, health_list):
                community.send_remote_select(peer=peer, infohash=infohash, processing_callback=on_collected, last=1)

        self.content.decode_map[TorrentsHealthPayload.msg_id] = lambda *args: on_torrents_health(self.content, *args)

        @lazy_wrapper_wd(SelectResponsePayload)
        async def on_remote_select_response(community, peer, response_payload, data):
            processing_results = await community.on_remote_select_response(peer, data)
            if not processing_results:
                return

            def on_collected(_, processing_results):
                for result in processing_results:
                    if result.obj_state == ObjState.NEW_OBJECT and result.md_obj.metadata_type == REGULAR_TORRENT:
                        self.status['preview'].add(result.md_obj.infohash)
                        self.update_results()

            for result in processing_results:
                if result.obj_state == ObjState.NEW_OBJECT and result.md_obj.metadata_type in (
                        CHANNEL_TORRENT,
                        COLLECTION_NODE,
                ):
                    request_dict = {
                        "metadata_type": [COLLECTION_NODE, REGULAR_TORRENT],
                        "channel_pk": result.md_obj.public_key,
                        "origin_id": result.md_obj.id_,
                        "first": 0,
                        "last": 4,
                    }
                    community.send_remote_select(peer=peer, processing_callback=on_collected, **request_dict)

                for dep_query_dict in result.missing_deps:
                    community.send_remote_select(peer=peer, **dep_query_dict)

        self.content.decode_map[SelectResponsePayload.msg_id] = lambda *args: on_remote_select_response(self.content, *args)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Run torrent collecting experiment')
    parser.add_argument('--fragile', '-f', help='Fail at the first error', action='store_true')
    arguments = parser.parse_args()

    service = Service(state_dir=Path.cwd() / 'tribler-statedir')
    service.run(fragile=arguments.fragile, check_already_running=False)
