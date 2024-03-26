import argparse
import asyncio
import os
from binascii import unhexlify
from pathlib import Path

from ipv8.messaging.anonymization.tunnel import BACKWARD, FORWARD
from ipv8.messaging.anonymization.utils import run_speed_test
from ipv8.taskmanager import TaskManager, task

from tribler.core.components.tunnel.tunnel_component import TunnelsComponent
from scripts.experiments.tunnel_community.speed_test_exit import Service as SpeedTestService

EXPERIMENT_NUM_MB = int(os.environ.get('EXPERIMENT_NUM_MB', 25))
EXPERIMENT_NUM_CIRCUITS = int(os.environ.get('EXPERIMENT_NUM_CIRCUITS', 10))
EXPERIMENT_NUM_HOPS = int(os.environ.get('EXPERIMENT_NUM_HOPS', 1))


class Service(SpeedTestService, TaskManager):
    def __init__(self, *args, **kwargs):
        SpeedTestService.__init__(self, *args, **kwargs)
        TaskManager.__init__(self)
        self.config.dht.enabled = True

        self.busy = False
        self.index = 0
        self.results = []
        self.tunnels = self.rust = None
        self.finished = [False for _ in range(EXPERIMENT_NUM_CIRCUITS)]

    async def on_tribler_started(self):
        component = self.session.get_instance(TunnelsComponent)
        self.tunnels = component.community
        self.tunnels.settings.remove_tunnel_delay = 0

        await self.wait_until_ready()
        info_hash = unhexlify('e24d8e65a329a59b41a532ebd4eb4a3db7cb291b')
        self.tunnels.join_swarm(info_hash, EXPERIMENT_NUM_HOPS, seeding=False, callback=self.on_circuit_ready)

    @task
    async def on_circuit_ready(self, address):
        if self.index >= EXPERIMENT_NUM_CIRCUITS or self.busy:
            return

        self.busy = True
        index = self.index
        self.index += 1
        self.logger.info(f"on_circuit_ready: {index+1}/{EXPERIMENT_NUM_CIRCUITS}")
        circuit = self.tunnels.circuits[self.tunnels.ip_to_circuit_id(address[0])]
        self.results += await self.run_speed_test(BACKWARD, circuit, index, EXPERIMENT_NUM_MB)
        self.results += await self.run_speed_test(FORWARD, circuit, index, EXPERIMENT_NUM_MB)
        self.finished[index] = True
        self.busy = False
        if all(self.finished):
            await self.on_circuit_finished()

    async def on_circuit_finished(self):
        with open('speed_test_e2e.txt', 'w') as f:
            f.write("Time Circuit Type Speed\n")
            for result in self.results:
                f.write(' '.join(map(str, result)) + '\n')

        self._graceful_shutdown()

    async def run_speed_test(self, direction, circuit, index, size):
        request_size = 0 if direction == BACKWARD else 1024
        response_size = 1024 if direction == BACKWARD else 0
        num_requests = size * 1024
        component = self.session.get_instance(TunnelsComponent)
        task = asyncio.create_task(run_speed_test(component.community, circuit, request_size,
                                                  response_size, num_requests, window=50))
        ts = 0
        results = []
        prev_transferred = circuit.bytes_down if direction == BACKWARD else circuit.bytes_up
        while not task.done():
            cur_transferred = circuit.bytes_down if direction == BACKWARD else circuit.bytes_up
            results.append((ts, index, direction, (cur_transferred - prev_transferred) / 1024))
            prev_transferred = cur_transferred
            await asyncio.sleep(1)
            ts += 1

        return results


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Run performance experiment for e2e tunnels')
    parser.add_argument('--fragile', '-f', help='Fail at the first error', action='store_true')
    arguments = parser.parse_args()

    service = Service(state_dir=Path.cwd() / 'tribler-statedir')
    service.run(fragile=arguments.fragile, check_already_running=False)
