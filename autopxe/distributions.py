
import tarfile
from configparser import ConfigParser
from contextlib import contextmanager
from dataclasses import dataclass
from hashlib import blake2s
from logging import getLogger
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Dict, Iterator
from urllib.parse import urlparse
from urllib.request import urlretrieve

LOG = getLogger(__name__)


@dataclass(frozen=True)
class Distribution:
    """Represents a Linux distribution that can be installed with PXE."""
    # A user friendly name (but not too much, spaces are annoying on the commandline)
    name: str
    # The URL at which the netboot.tar.gz archive for this distribution can be retrieved
    url: str

    @property
    def filename(self) -> str:
        """The filename as guessed from the URL"""
        parsed = urlparse(self.url)
        return parsed.path.rsplit("/", 1)[-1]

    @property
    def url_hash(self) -> str:
        """A hash of the url, for caching purposes."""
        # TODO blake2s is probably not ideal
        return blake2s(self.url.encode()).hexdigest()

    @contextmanager
    def get_archive(self) -> Iterator[tarfile.TarFile]:
        """Downloads (or gets from cache) the netboot tar archive and opens it."""
        # FIXME only works for tar files
        # Where the archive is cached to avoid redownloading it
        cached_path = Path.home().joinpath(".cache", "pxe", self.url_hash, self.filename)
        if not cached_path.parent.exists():
            LOG.debug("Creating %s", cached_path.parent)
            cached_path.parent.mkdir(exist_ok=True, parents=True)
        if not cached_path.exists():
            LOG.info("Downloading %s", self.url)

            def report_cb(blocks: int, block_size: int, total_size: int):
                print(end=".", flush=True)
            # TODO does not cleanup if aborted
            urlretrieve(self.url, cached_path, reporthook=report_cb)
            print()
        LOG.debug("Opening %s", cached_path)
        with tarfile.open(cached_path) as tar:
            # TODO check tar contents
            # FIXME gaping security hole esp since run as root
            yield tar

    @contextmanager
    def unpack(self) -> Iterator[Path]:
        """Unpacks the netboot archive to a temporary directory,
        cleaned when the context manager exits"""
        with TemporaryDirectory("pxe") as td:
            with self.get_archive() as tar:
                LOG.info("Extracting %s to %s", self.name, td)
                tar.extractall(path=td)
            yield Path(td)


def from_file(path: Path) -> Dict[str, Distribution]:
    """Reads distributions from the given file"""
    assert path.exists()
    config = ConfigParser()
    config.read("distros.ini")
    distros: Dict[str, Distribution] = {
        i: Distribution(name=i, **config[i]) for i in config.sections()
    }
    if not distros:
        raise ValueError(f"Could not parse any distributions from {path}")
    LOG.debug("Parsed distributions:")
    for i in distros.values():
        LOG.debug(i)
    return distros
