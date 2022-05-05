"""Networking stuff using the pyroute2 library"""
from __future__ import annotations

import errno
from contextlib import contextmanager
from dataclasses import dataclass
from ipaddress import IPv4Address
from logging import getLogger
from socket import AddressFamily
from typing import Any, Iterator, List, Mapping

from pyroute2 import IPRoute
from pyroute2.netlink.exceptions import NetlinkError
from pyroute2.nftables import expressions
from pyroute2.nftables.main import NFTables  # type: ignore

LOG = getLogger(__name__)

# https://git.netfilter.org/nftables/tree/src/parser_json.c
# linux/netfilter.h
NFPROTO_UNSPEC = 0
NFPROTO_INET = 1
NFPROTO_IPV4 = 2


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

    def __str__(self) -> str:
        return self.name


def iface_lookup(name: str) -> Interface:
    """Returns the first interface matching the given name"""
    with IPRoute() as ipr:
        return Interface(
            name=name,
            index=ipr.link_lookup(ifname=name)[0]
        )


def get_default_iface() -> Interface:
    """Returns the interface associated with the default route."""
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
def make_bridge(addr: IPv4Address, prefixlen: int, for_iface: Interface) -> Iterator[Interface]:
    """Context manager that creates & returns a bridge"""
    name = "autopxe-temp-br"  # TODO
    with IPRoute() as ipr:
        ipr.link("add", ifname=name, kind="bridge")
        iface: Interface = iface_lookup(name)
        ipr.addr("add", index=iface.index, address=str(addr), prefixlen=prefixlen)
        ipr.link("set", index=iface.index, state="up")
        ipr.link("set", index=for_iface.index, master=iface.index)
        yield iface
        ipr.link("del", index=iface.index)


@contextmanager
def setup_iface(addr: IPv4Address, prefixlen: int, iface: Interface):
    """Adds the given address to the interface. Also sets it up."""
    with IPRoute() as ipr:
        address_exists: bool = False
        try:
            LOG.info("Adding %s/%d to %s", addr, prefixlen, iface)
            ipr.addr("add", index=iface.index, address=str(addr), prefixlen=prefixlen)
        except NetlinkError as err:
            if err.code == errno.EEXIST:
                LOG.info("%s already has address %s/%d", iface, addr, prefixlen)
                address_exists = True
            else:
                raise
        ipr.link("set", index=iface.index, state="up")
        LOG.info("%s is up", iface)
        yield
        if not address_exists:
            LOG.info("Deleting %s/%d from %s", addr, prefixlen, iface)
            ipr.addr("del", index=iface.index, address=str(addr), prefixlen=prefixlen)


@contextmanager
def _masquerade():
    with NFTables(nfgen_family=0) as nft:
        # if nft.get_rules():
        #   raise RuntimeError("nftables rules are present, we don't want to mess them up")
        FILT_TABLE = "autopxe-filter"
        NAT_TABLE = "autopxe-nat"
        nft.table("add", name=FILT_TABLE, nfgen_family=NFPROTO_INET)
        nft.table("add", name=NAT_TABLE, nfgen_family=NFPROTO_IPV4)
        # forward stuff
        # https://elixir.bootlin.com/linux/latest/source/net/netfilter/nf_tables_api.c
        nft.chain("add", table=FILT_TABLE, name="autopxe-forward",
                  hook="forward", type="filter", policy=1)

        def oifname(name: str):
            stuff = []
            encoded_name: bytes = name.encode().ljust(16, b"\x00")
            stuff.append(expressions.genex("meta", {
                "key": 7,  # NFT_META_OIFNAME
                "dreg": 1,
            }))
            stuff.append(expressions.genex("cmp", {
                "sreg": 1,
                "op": 0,  # NFT_CMP_EQ
                "data": {
                    "attrs": [("NFTA_DATA_VALUE", encoded_name)],
                },
            }))
            return stuff
        nft.rule("add",
                 table=FILT_TABLE,
                 chain="autopxe-forward",
                 expressions=(oifname("wlp61s0"),
                              expressions.verdict(1))
                 )
        breakpoint()
        pass
        yield
