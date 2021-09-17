from unittest.mock import Mock

from tribler_core.components.base import Component, testcomponent
from tribler_core.config.tribler_config import TriblerConfig
from tribler_core.modules.resource_monitor.core import CoreResourceMonitor


class ResourceMonitorComponent(Component):
    enable_in_gui_test_mode = True
    resource_monitor: CoreResourceMonitor

    @classmethod
    def should_be_enabled(cls, config: TriblerConfig):
        return config.resource_monitor.enabled

    @classmethod
    def make_implementation(cls, config: TriblerConfig, enable: bool):
        if enable:
            from tribler_core.components.implementation.resource_monitor import ResourceMonitorComponentImp
            return ResourceMonitorComponentImp(cls)
        return ResourceMonitorComponentMock(cls)


@testcomponent
class ResourceMonitorComponentMock(ResourceMonitorComponent):
    resource_monitor = Mock()