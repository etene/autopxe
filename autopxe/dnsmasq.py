from __future__ import annotations

import functools
import subprocess
import tempfile
from dataclasses import asdict, dataclass
from distutils.spawn import find_executable
from logging import getLogger
from pathlib import Path
from typing import Any, Iterable, Optional, Protocol, TextIO, Tuple

LOG = getLogger(__name__)

if (DNSMASQ := find_executable("dnsmasq")) is None:
    raise RuntimeError("dnsmasq not in PATH")


class HasStr(Protocol):
    def __str__(self) -> str: ...


HasStrTriple = Tuple[HasStr, HasStr, HasStr]


@dataclass
class DnsMasq:
    """Context manager that runs dnsmasq.

    Option names closely match the actual dnsmasq options,
    except that the - is replaced by an underscore for obvious reasons.
    """
    interface: HasStr
    tftp_root: HasStr
    dhcp_boot: HasStrTriple
    dhcp_range: HasStrTriple
    listen_address: HasStr
    pxe_service: HasStrTriple = ("x86PC", '"Install Linux"', "pxelinux")
    keep_in_foreground: bool = True
    log_facility: HasStr = "-"
    enable_tftp: bool = True
    no_hosts: bool = True
    bind_interfaces: bool = True
    tftp_no_blocksize: bool = True

    def __post_init__(self):
        self.process: Optional[subprocess.Popen] = None
        self.workdir: Optional[tempfile.TemporaryDirectory] = None
        self.logs: Optional[TextIO] = None

    @functools.singledispatchmethod
    def format_option(self, value: Any, switch: str) -> Optional[str]:
        """Format a regular single value option."""
        return f"{switch}={value}"

    @format_option.register
    def _format_bool(self, value: bool, switch: str) -> Optional[str]:
        """Format a boolean option.

        For on/off switches, a `True` value puts the switch on the commandline
        with no arguments and anything else removes it from the commandline.
        """
        return switch if value else None

    @format_option.register
    def _format_tuple(self, value: tuple, switch: str) -> str:
        """Format a tuple of value. dnsmasq expects them joined with commas"""
        return f"{switch}={','.join(map(str, value))}"

    @property
    def formatted_options(self) -> Iterable[str]:
        """An iterator over the formatted options, ready to pass to dnsmasq"""
        for name, value in asdict(self).items():
            # we have underscores but dnsmasq takes dashes
            if formatted := self.format_option(value, f"--{name.replace('_', '-')}"):
                yield formatted

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
        LOG.debug("running %s", " ".join(cmdline))
        self.process = subprocess.Popen(cmdline, text=True)
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
            LOG.debug(line)
