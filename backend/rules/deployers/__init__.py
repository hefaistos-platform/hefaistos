"""
Platform deployers package.

Provides abstract base class and concrete deployers for each supported SIEM/EDR platform.
"""

from .base import PlatformDeployer, DeploymentResult
from .defender import DefenderDeployer
from .sentinel import SentinelDeployer
from .splunk import SplunkDeployer
from .qradar import QRadarDeployer
from .wazuh import WazuhDeployer

PLATFORM_DEPLOYER_MAP: dict[str, type[PlatformDeployer]] = {
    'defender': DefenderDeployer,
    'sentinel': SentinelDeployer,
    'splunk': SplunkDeployer,
    'qradar': QRadarDeployer,
    'wazuh': WazuhDeployer,
}

__all__ = [
    'PlatformDeployer',
    'DeploymentResult',
    'DefenderDeployer',
    'SentinelDeployer',
    'SplunkDeployer',
    'QRadarDeployer',
    'WazuhDeployer',
    'PLATFORM_DEPLOYER_MAP',
]
