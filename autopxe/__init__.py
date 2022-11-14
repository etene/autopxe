from dataclasses import dataclass
from ipaddress import IPv4Address, IPv4Network
from logging import getLogger
from pathlib import Path
from time import sleep
from typing import Optional, Tuple

from autopxe.distributions import Distribution
from autopxe.dnsmasq import DnsMasq
from autopxe.iptables import masquerade
from autopxe.networking import Interface, setup_iface
from autopxe.preseed import Preseeder

LOG = getLogger(__name__)


@dataclass
class Pxe:
    """Sets up everything for a PXE net install to work"""
    # The distribution to install
    distribution: Distribution
    # The interface that we expect to have clients on
    pxe_iface: Interface
    # The network range to serve clients on
    pxe_net: IPv4Network
    # Interface with internet, to masquerade on
    masquerade_iface: Interface
    # How many clients can get an address
    dhcp_range_size: int = 20
    # Whether the process must stop
    must_stop: bool = False
    # Optional preseed file
    preseed_file: Optional[Path] = None

    @property
    def server_address(self) -> IPv4Address:
        """The server (our) address, which is the first address on the network"""
        return next(self.pxe_net.hosts())

    @property
    def dhcp_range(self) -> Tuple[IPv4Address, IPv4Address]:
        """Lower and upper (inclusive) bounds for the DHCP client range"""
        return (first_addr := self.server_address + 1), first_addr + self.dhcp_range_size

    def run(self):
        with (self.distribution.unpack() as tempdir,
              setup_iface(self.server_address, self.pxe_net.prefixlen, self.pxe_iface),
              masquerade(),
              # FIXME: preseed is not mandatory, actually
              Preseeder(file_path=self.preseed_file, server_ip=self.server_address) as preseeder,
              ):
            dhcp_boot = [
                # serve the installer if the client if it isn't the installer itself
                ("tag:!installer", "pxelinux.0", "pxeserver", str(self.server_address)),
            ]
            if self.preseed_file:
                # serve the preseed file to the client if it's the debian installer
                dhcp_boot.append(("tag:installer", preseeder.url))
            with DnsMasq(tftp_root=tempdir,
                         interface=self.pxe_iface.name,
                         dhcp_boot=dhcp_boot,
                         dhcp_range=(*self.dhcp_range, "1h"),
                         listen_address=self.server_address,
                         ) as dnsmasq:
                try:
                    while dnsmasq.running:
                        dnsmasq.read_logs()
                        sleep(.1)
                        if self.must_stop:
                            dnsmasq.stop()
                            break
                except KeyboardInterrupt:
                    dnsmasq.stop()
                # Read the last logs
                dnsmasq.read_logs()
            LOG.info("dnsmasq exited with status %d", dnsmasq.process.poll())
