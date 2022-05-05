"""used to set up masquerading with iptables"""
from contextlib import contextmanager
from logging import getLogger
from subprocess import check_call

from autopxe.networking import get_default_iface

LOG = getLogger(__name__)


@contextmanager
def call_iptables(**kwargs: str):
    """Adds a rule to iptables and removes it.
    Only append rules are supported.

    kwargs format is iptables_option = option_value
    where iptables_option is a snake_cased iptable commandline option.
    """
    assert "append" in kwargs, "non-append rules are not supported"
    # Arguments for the call that adds the rule
    iptables_add_args = ["iptables"]
    # Add option and its value to the arguments
    for key, value in kwargs.items():
        iptables_add_args.extend((
            "--" + key.replace("_", "-"), value
        ))
    # Arguments for the call that deletes the rule
    iptables_del_args = iptables_add_args.copy()
    # We just replace --append with --delete, that works for our needs
    iptables_del_args[iptables_del_args.index("--append")] = "--delete"
    try:
        LOG.info("%s", " ".join(iptables_add_args))
        check_call(iptables_add_args)
        yield
    finally:
        LOG.info("%s", " ".join(iptables_del_args))
        check_call(iptables_del_args)


@contextmanager
def masquerade():
    """Setups crude masquerading with iptables."""
    iface = get_default_iface()
    with (call_iptables(append="FORWARD",
                        out_interface=iface.name,
                        jump="ACCEPT"),
          call_iptables(append="FORWARD",
                        in_interface=iface.name,
                        jump="ACCEPT"),
          call_iptables(table="nat",
                        append="POSTROUTING",
                        out_interface=iface.name,
                        jump="MASQUERADE"),
          ):
        yield
