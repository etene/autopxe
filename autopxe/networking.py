"""Networking stuff using the pyroute2 library"""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from ipaddress import IPv4Address
from logging import getLogger
from socket import AddressFamily
from typing import Any, Iterator, List, Mapping

from pyroute2 import IPRoute  # type: ignore

LOG = getLogger(__name__)


class CantGuessInterface(LookupError):
    """Raised when failing to guess an interface"""


class NLA(Mapping):
    """The missing type annotation for pyroute2 stuff"""
    def get_attr(self, attr: str) -> Any: ...


@dataclass
class Interface:
    """A Linux interface"""
    # kernel interface index
    index: int
    # interface name
    name: str

    @classmethod
    def from_netlink(cls, netlink_iface: NLA) -> Interface:
        return cls(
            index=netlink_iface["index"],
            name=netlink_iface.get_attr("IFLA_IFNAME"),
        )


def iface_lookup(name: str) -> Interface:
    """Returns the first interface matching the given name"""
    with IPRoute() as ipr:
        return Interface(
            name=name,
            index=ipr.link_lookup(ifname=name)[0]
        )


def get_default_iface() -> Interface:
    """TODO will i need this"""
    with IPRoute() as ipr:
        default_routes: List[NLA] = ipr.get_default_routes(family=AddressFamily.AF_INET)
        if not default_routes:
            raise CantGuessInterface("No default IPv4 route")
        if len(default_routes) > 1:
            raise CantGuessInterface("Too many default IPv4 routes")
        default_route = default_routes[0]
        iface_index: int = default_route.get_attr("RTA_OIF")
        iface_info: NLA = ipr.link("get", index=iface_index)[0]
    return Interface.from_netlink(iface_info)


def get_wired_iface() -> Interface:
    """Returns the first Ethernet interface found"""
    with IPRoute() as ipr:
        # TODO use correct constant for ethernet
        ethernet: List[NLA] = [i for i in ipr.get_links() if i.get("ifi_type") == 1]
    if not ethernet:
        raise CantGuessInterface("No ethernet interface found")
    elif len(ethernet) > 1:
        LOG.warning("%d ethernet interfaces found !", len(ethernet))
        LOG.warning("selecting the first one, that might not be what you want")
    return Interface.from_netlink(ethernet[0])


@contextmanager
def make_bridge(addr: IPv4Address, prefixlen: int, name: str = "autopxe-br") -> Iterator[Interface]:
    """Context manager that creates & returns a bridge"""
    with IPRoute() as ipr:
        ipr.link("add", ifname=name, kind="bridge")
        iface: Interface = iface_lookup(name)
        ipr.addr("add", index=iface.index, address=str(addr), prefixlen=prefixlen)
        ipr.link("set", index=iface.index, state="up")
        yield iface
        ipr.link("del", index=iface.index)
