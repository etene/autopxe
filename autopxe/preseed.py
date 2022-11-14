from functools import partial
import http.server
from ipaddress import IPv4Address
import logging
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Thread
from shutil import copyfile
from typing import ClassVar, Optional

LOG = logging.getLogger(__name__)


class Preseeder:
    """Copies a preseed configuration file to a temporary directory and serves it via http"""
    FILE_NAME: ClassVar[str] = "preseed.cfg"

    def __init__(self, file_path: Optional[Path], server_ip: IPv4Address, port: int = 8000) -> None:
        self._td = None
        self._tempdir_name: Optional[Path] = None
        self.file_path = file_path
        self.server_addr = (str(server_ip), port)

    @property
    def url(self) -> str:
        """The preseed file url for debian installer"""
        ip, port = self.server.server_address
        return f"http://{ip}:{port}/{self.FILE_NAME}"

    @property
    def temporary_directory_name(self) -> Path:
        return self._tempdir_name

    def __enter__(self):
        # TODO refactor, that's dirty
        self._td = TemporaryDirectory("preseed")
        self._tempdir_name = Path(self._td.__enter__())
        handler_cls = partial(http.server.SimpleHTTPRequestHandler,
                              directory=self.temporary_directory_name)
        self.server = http.server.ThreadingHTTPServer(
            server_address=self.server_addr,
            RequestHandlerClass=handler_cls,
        )
        self.server_thread = Thread(target=self.server.serve_forever)
        if self.file_path:
            copyfile(self.file_path, self.temporary_directory_name / self.FILE_NAME)
            LOG.info("Preseed configuration copied to %s", self.temporary_directory_name)
        self.server_thread.start()
        LOG.info("Serving preseed config as %s", self.url)
        return self

    def __exit__(self, exc, value, tb):
        self.server.shutdown()
        self.server_thread.join()
        self._td.__exit__(exc, value, tb)
