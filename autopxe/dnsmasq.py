from __future__ import annotations

import functools
import subprocess
import tempfile
from dataclasses import asdict, dataclass
from distutils.spawn import find_executable
from logging import getLogger
from pathlib import Path
from typing import Any, Iterable, Optional, Protocol, TextIO

LOG = getLogger(__name__)

if (DNSMASQ := find_executable("dnsmasq")) is None:
    raise RuntimeError("dnsmasq not in PATH")


class HasStr(Protocol):
    def __str__(self) -> str: ...


@dataclass
class DnsMasq:
    """Context manager that runs dnsmasq.

    Option names closely match the actual dnsmasq options,
    except that the - is replaced by an underscore for obvious reasons.
    """
    interface: HasStr
    tftp_root: HasStr
    dhcp_boot: list[tuple[HasStr, ...]]
    dhcp_range: tuple[HasStr, ...]
    listen_address: HasStr
    pxe_service: tuple[HasStr, ...] = ("x86PC", '"Install Linux"', "pxelinux")
    keep_in_foreground: bool = True
    log_facility: HasStr = "-"
    enable_tftp: bool = True
    no_hosts: bool = True
    bind_interfaces: bool = True
    tftp_no_blocksize: bool = True
    log_dhcp: bool = True
    dhcp_vendorclass: str = "set:installer,d-i"

    def __post_init__(self):
        self.process: Optional[subprocess.Popen] = None
        self.workdir: Optional[tempfile.TemporaryDirectory] = None
        self.logs: Optional[TextIO] = None

    @functools.singledispatchmethod
    def format_option(self, value: Any, switch: str) -> list[str]:
        """Format a regular single value option."""
        return [f"{switch}={value}"]

    @format_option.register
    def _format_bool(self, value: bool, switch: str) -> list[str]:
        """Format a boolean option.

        For on/off switches, a `True` value puts the switch on the commandline
        with no arguments and anything else removes it from the commandline.
        """
        return [switch] if value else []

    @format_option.register
    def _format_tuple(self, value: tuple, switch: str) -> list[str]:
        """Format a tuple of values. dnsmasq expects them joined with commas"""
        return [f"{switch}={','.join(map(str, value))}"]

    @format_option.register
    def _format_list(self, value: list, switch: str) -> list[str]:
        options = []
        for i in value:
            options.extend(self.format_option(i, switch))
        return options

    @property
    def formatted_options(self) -> Iterable[str]:
        """An iterator over the formatted options, ready to pass to dnsmasq"""
        for name, value in asdict(self).items():
            # we have underscores but dnsmasq takes dashes
            yield from self.format_option(value, f"--{name.replace('_', '-')}")

    def __enter__(self) -> DnsMasq:
        """Launches the dnsmasq process and return its handle"""
        assert DNSMASQ
        # Create the working directory
        self.workdir = tempfile.TemporaryDirectory(prefix="autopxe-dnsmasq-")
        # Override the "--log-facility" argument with our log file
        self.log_facility = Path(self.workdir.name) / "dnsmasq.log"
        # Dnsmasq needs it to exist
        self.log_facility.touch()
        cmdline = (DNSMASQ, "-C", "/dev/null", *self.formatted_options)
        LOG.info("running %s", " ".join(cmdline))
        self.process = subprocess.Popen(cmdline, text=True)
        LOG.info("dnsmasq started with pid %d", self.process.pid)
        # Open the logfile
        self.logs = self.log_facility.open(mode="rt")
        return self

    def __exit__(self, *args, **kwargs):
        """Stop dnsmasq"""
        self.stop()
        self.logs.close()
        self.workdir.cleanup()

    def stop(self):
        """Stops and waits for the dnsmasq process if it's running"""
        if self.process.poll() is None:
            LOG.info("Stopping dnsmasq")
            self.process.terminate()
            self.process.wait()

    def read_logs(self):
        """Reads the logfile and logs it with DEBUG level"""
        for line in filter(None, map(str.strip, self.logs.readlines())):
            LOG.info(line)

    @property
    def running(self) -> bool:
        """Whether the dnsmasq process is still running"""
        return self.process is not None and self.process.poll() is None
