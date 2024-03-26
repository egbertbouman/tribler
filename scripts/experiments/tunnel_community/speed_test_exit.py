import argparse
import asyncio
import os
from pathlib import Path
from timeit import default_timer

from ipv8.taskmanager import TaskManager
from ipv8.messaging.anonymization.tunnel import PEER_FLAG_EXIT_BT, PEER_FLAG_RELAY, CIRCUIT_STATE_READY
from ipv8.messaging.interfaces.dispatcher.endpoint import DispatcherEndpoint

from tribler.core.components.ipv8.ipv8_component import Ipv8Component
from tribler.core.components.key.key_component import KeyComponent
from tribler.core.components.restapi.restapi_component import RESTComponent
from tribler.core.components.tunnel.tunnel_component import TunnelsComponent
from tribler.core.utilities.tiny_tribler_service import TinyTriblerService

EXPERIMENT_NUM_MB = int(os.environ.get('EXPERIMENT_NUM_MB', 100))
EXPERIMENT_NUM_HOPS = int(os.environ.get('EXPERIMENT_NUM_HOPS', 1))
EXPERIMENT_SERVER = os.environ.get('EXPERIMENT_SERVER')


class Service(TinyTriblerService, TaskManager):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs,
                         components=[Ipv8Component(), KeyComponent(), RESTComponent(), TunnelsComponent()])
        TaskManager.__init__(self)
        self.tunnels = None
        self.rust = None
        self.config.dht.enabled = True

    async def on_tribler_started(self):
        component = self.session.get_instance(TunnelsComponent)
        self.tunnels = component.community
        self.tunnels.settings.remove_tunnel_delay = 0

        await self.wait_until_ready()
        await self.build_and_test_circuit(EXPERIMENT_NUM_HOPS)
        await self.shutdown_task_manager()
        self._graceful_shutdown()

    async def wait_until_ready(self):
        component = self.session.get_instance(Ipv8Component)
        self.rust = component.ipv8.endpoint
        if isinstance(self.rust, DispatcherEndpoint):
            self.rust = self.rust.interfaces.get("UDPIPv4", None)

        for _ in range(60):
            relays = self.tunnels.get_candidates(PEER_FLAG_RELAY)
            exits = self.tunnels.get_candidates(PEER_FLAG_EXIT_BT)
            if len(relays) >= 1 and len(exits) >= 1:
                self.logger.info("Found %d exits and %d relays. Starting experiment.", len(exits), len(relays))
                break
            await asyncio.sleep(1)

    async def build_and_test_circuit(self, hops, peer=None, retries=3):
        circuit = None
        for _ in range(retries):
            start = default_timer()
            circuit = self.tunnels.create_circuit(hops, required_exit=peer)
            if not circuit:
                self.logger.info('Retrying to create circuit of %d hops', hops)
                continue
            if await circuit.ready:
                self.logger.info('Circuit %d with %d hops created in %.3f seconds',
                                 circuit.circuit_id, hops, default_timer() - start)
                break

        if not circuit or circuit.state != CIRCUIT_STATE_READY:
            self.logger.error('Failed to create circuit with %d hops. Skipping.', hops)
            return

        port = self.rust.rust_ep.create_udp_associate(0, hops)
        results = await self.run_speedtest(EXPERIMENT_SERVER, port, EXPERIMENT_NUM_MB)
        Service.write_results(list(results.values()))
        await self.tunnels.remove_circuit(circuit_id=circuit.circuit_id)

    def run_speedtest(self, server, associate_port, num_mb):
        results = asyncio.Future()
        # We're using: request_size = 50 bytes, response_size = 1024 bytes, timeout_ms = 75, window_size = 150
        self.rust.run_speedtest(server, associate_port, num_mb * 1024,
                                50, 1024, 75, 150, results.set_result)
        return results

    @staticmethod
    def write_results(results):
        # Output RTTs for plotting
        t_start = min([r[0] for r in results])
        rtt_data = sorted([((r[0] - t_start) / 1000,
                            (r[2] - r[0]) if r[2] else 'NA') for r in results],
                          key=lambda t: t[0])

        with open('speed_test_exit_rtt.txt', 'w') as fp:
            fp.write('Time RTT\n')
            for ts, rtt in rtt_data:
                fp.write(f'{ts:.2f} {rtt}\n')

        # Output speeds for plotting
        ts_to_upload = {}
        ts_to_download = {}
        for result in results:
            if result[0]:
                ts_up = (result[0] - t_start) / 1000
                ts_to_upload[ts_up] = ts_to_upload.get(ts_up, 0) + result[1]
            if result[2]:
                ts_down = (result[2] - t_start) / 1000
                ts_to_download[ts_down] = ts_to_download.get(ts_down, 0) + result[3]

        with open('speed_test_exit.txt', 'w') as fp:
            fp.write('Time Up Down\n')
            for ts in sorted(set(ts_to_upload.keys()) | set(ts_to_download.keys())):
                speed_up = ts_to_upload.get(ts, 0)
                speed_down = ts_to_download.get(ts, 0)
                fp.write(f'{ts:.3f} {(speed_up / 1024 ** 2) * 1000} {(speed_down / 1024 ** 2) * 1000}\n')


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Run performance experiment for exit tunnels')
    parser.add_argument('--fragile', '-f', help='Fail at the first error', action='store_true')
    arguments = parser.parse_args()

    service = Service(state_dir=Path.cwd() / 'tribler-statedir')
    service.run(fragile=arguments.fragile, check_already_running=False)
