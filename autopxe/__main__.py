#!/usr/bin/python3
import argparse
import logging
from ipaddress import IPv4Network
from pathlib import Path

from autopxe import Pxe, distributions, networking


def get_parser() -> argparse.ArgumentParser:
    psr = argparse.ArgumentParser(
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
        description="Automatically sets up everything for a PXE Linux install",
    )
    psr.add_argument(
        "-d", "--distribution-config", type=Path, default=Path("distros.ini"),
        help="Config file to read distributions from", metavar="FILE"
    )
    psr.add_argument(
        "-l", "--list-distributions", default=False, action="store_true",
        help="List available distributions & exit"
    )
    psr.add_argument(
        "-i", "--interface", metavar="NAME", type=networking.iface_lookup,
        default=networking.get_wired_iface(),
        help="(Wired) interface to handle clients on",
    )
    psr.add_argument(
        "-n", "--network", metavar="CIDR", type=IPv4Network, default=IPv4Network("10.94.0.0/16"),
        help="private subnet to use for server & clients"
    )
    psr.add_argument(
        "-m", "--masquerade-interface", metavar="NAME", type=networking.iface_lookup,
        default=networking.get_default_iface(),
        help="Interface with an internet connection to masquerade on, "
             "so that clients have an internet connection.",
    )
    psr.add_argument(
        "--log-level", default="INFO", choices=("DEBUG", "INFO", "WARNING"), metavar="LEVEL",
        help="Verbosity for log messages"
    )
    psr.add_argument(
        "-p", "--preseed-file", metavar="FILE", type=Path,
        help="Preseed file for debian installer",
    )
    psr.add_argument("distribution", help="Distribution to install", nargs="?")
    return psr


def main():
    psr = get_parser()
    args = psr.parse_args()
    logging.basicConfig(level=args.log_level)
    distros = distributions.from_file(args.distribution_config)
    if args.list_distributions:
        for i in distros:
            print(i)
        exit()
    if not args.distribution:
        psr.error("You must provide a distribution to install, "
                  "use -l to list them")
    if distribution := distros.get(args.distribution):
        Pxe(distribution=distribution,
            pxe_iface=args.interface,
            pxe_net=args.network,
            masquerade_iface=args.masquerade_interface,
            preseed_file=args.preseed_file,
            ).run()
    else:
        psr.error(f"{args.distribution}: unknown distribution")  # TODO


if __name__ == "__main__":
    main()
