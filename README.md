# autopxe

Automatically set up everything to boot and install another computer (or a VM) with PXE.

## Features

- [x] Downloads, caches & unpacks the PXE installer for your distro
- [x] Create a temporary bridge interface to serve requests on
- [ ] Adds your Ethernet interface to it
- [ ] Sets up a NAT
- [x] Runs `dnsmasq` as a TFTP & DHCP server

## Supported distributions (work in progress)

- Debian Buster
- Debian Testing
- Ubuntu Focal
