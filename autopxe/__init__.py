from dataclasses import dataclass
from ipaddress import IPv4Address, IPv4Network
from logging import getLogger
from typing import Tuple

from autopxe.distributions import Distribution
from autopxe.dnsmasq import DnsMasq
from autopxe.networking import Interface, make_bridge

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
    # How many clients can get an address
    dhcp_range_size: int = 20

    @property
    def server_address(self) -> IPv4Address:
        """The server (our) address, which is the first address on the network"""
        return next(self.pxe_net.hosts())

    @property
    def dhcp_range(self) -> Tuple[IPv4Address, IPv4Address]:
        """Lower and upper (inclusive) bounds for the DHCP client range"""
        return (first_addr := self.server_address + 1), first_addr + self.dhcp_range_size

    def run(self):
        LOG.debug("Setting up & running %s", self)
        with self.distribution.unpack() as tempdir:
            LOG.info("%s unpacked to %s", self.distribution.name, tempdir)
            with make_bridge(self.server_address, self.pxe_net.prefixlen) as br:
                LOG.info("bridge %r set up successfully", br.name)
                with DnsMasq(tftp_root=tempdir,
                             interface=br.name,
                             dhcp_boot=("pxelinux.0", "pxeserver", str(self.server_address)),
                             dhcp_range=(*self.dhcp_range, "1h"),
                             listen_address=self.server_address,
                             ) as dnsmasq:
                    LOG.info("dnsmasq started with pid %d", dnsmasq.process.pid)
                    try:
                        while True:
                            data = dnsmasq.logs.readline().strip()
                            if data:
                                LOG.debug("dnsmasq: %s", data)
                        dnsmasq.process.wait()
                    except KeyboardInterrupt:
                        print("exiting")
        LOG.info("dnsmasq exited with status %d", dnsmasq.process.poll())
