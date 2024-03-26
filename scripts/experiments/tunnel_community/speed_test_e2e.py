import argparse
import asyncio
import os
from binascii import unhexlify
from pathlib import Path

from ipv8.messaging.anonymization.tunnel import BACKWARD, FORWARD
from ipv8.messaging.anonymization.utils import run_speed_test
from ipv8.taskmanager import TaskManager, task

from tribler.core.components.ipv8.ipv8_component import Ipv8Component
from tribler.core.components.key.key_component import KeyComponent
from tribler.core.components.restapi.restapi_component import RESTComponent
from tribler.core.components.tunnel.tunnel_component import TunnelsComponent
from tribler.core.utilities.tiny_tribler_service import TinyTriblerService

EXPERIMENT_NUM_MB = int(os.environ.get('EXPERIMENT_NUM_MB', 25))
EXPERIMENT_NUM_CIRCUITS = int(os.environ.get('EXPERIMENT_NUM_CIRCUITS', 10))
EXPERIMENT_NUM_HOPS = int(os.environ.get('EXPERIMENT_NUM_HOPS', 1))


class Service(TinyTriblerService, TaskManager):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs,
                         components=[Ipv8Component(), KeyComponent(), RESTComponent(), TunnelsComponent()])
        TaskManager.__init__(self)
        self.config.dht.enabled = True

        self.index = 0
        self.results = []
        self.output_file = 'speed_test_e2e.txt'
        self.tunnel_community = None

    def _graceful_shutdown(self):
        task = self.async_group.add_task(self.on_tribler_shutdown())
        task.add_done_callback(lambda result: TinyTriblerService._graceful_shutdown(self))

    async def on_tribler_shutdown(self):
        await self.shutdown_task_manager()

        # Fill in the gaps with 0's
        max_time = max(result[0] for result in self.results)
        index = 0
        while index < len(self.results):
            curr = self.results[index]
            _next = self.results[index + 1] if index + 1 < len(self.results) else None
            if not _next or curr[2] != _next[2]:
                self.results[index + 1:index + 1] = [(t + curr[0] + 1, curr[1], curr[2], 0)
                                                     for t in range(max_time - curr[0])]
                index += max_time - curr[0]
            index += 1

        with open(self.output_file, 'w') as f:
            f.write("Time Circuit Type Speed\n")
            for result in self.results:
                f.write(' '.join(map(str, result)) + '\n')

    async def on_tribler_started(self):
        info_hash = unhexlify('e24d8e65a329a59b41a532ebd4eb4a3db7cb291b')
        tunnels_component = self.session.get_instance(TunnelsComponent)
        self.tunnel_community = tunnels_component.community
        self.tunnel_community.join_swarm(info_hash, EXPERIMENT_NUM_HOPS, seeding=False, callback=self.on_circuit_ready)

    @task
    async def on_circuit_ready(self, address):
        index = self.index
        self.index += 1
        self.logger.info(f"on_circuit_ready: {self.index}/{EXPERIMENT_NUM_CIRCUITS}")
        circuit = self.tunnel_community.circuits[self.tunnel_community.ip_to_circuit_id(address[0])]
        self.results += await self.run_speed_test(BACKWARD, circuit, index, EXPERIMENT_NUM_MB)
        self.results += await self.run_speed_test(FORWARD, circuit, index, EXPERIMENT_NUM_MB)
        self.tunnel_community.remove_circuit(circuit.circuit_id)
        if self.index >= EXPERIMENT_NUM_CIRCUITS:
            self._graceful_shutdown()

    async def run_speed_test(self, direction, circuit, index, size):
        request_size = 0 if direction == BACKWARD else 1024
        response_size = 1024 if direction == BACKWARD else 0
        num_requests = size * 1024
        component = self.session.get_instance(TunnelsComponent)
        task = asyncio.create_task(run_speed_test(component.community, circuit, request_size,
                                                  response_size, num_requests, window=50))
        results = []
        prev_transferred = ts = 0
        while not task.done():
            cur_transferred = circuit.bytes_down if direction == BACKWARD else circuit.bytes_up
            results.append((ts, index, direction, (cur_transferred - prev_transferred) / 1024))
            prev_transferred = cur_transferred
            ts += 1
            await asyncio.sleep(1)
        return results


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Run performance experiment for e2e tunnels')
    parser.add_argument('--fragile', '-f', help='Fail at the first error', action='store_true')
    arguments = parser.parse_args()

    service = Service(state_dir=Path.cwd() / 'tribler-statedir')
    service.run(fragile=arguments.fragile, check_already_running=False)
