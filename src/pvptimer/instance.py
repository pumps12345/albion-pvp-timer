"""Single-instance support: one running copy, and a second launch brings that copy's window forward."""
import getpass
from pathlib import Path

from PySide6.QtCore import QLockFile, QObject, Signal
from PySide6.QtNetwork import QLocalServer, QLocalSocket

SERVER_NAME = f"PVPTimer-{getpass.getuser()}"


def acquire_single_instance(home: Path) -> QLockFile | None:
    """Lock held for the app's lifetime. None means another instance is already running,
    which must not start: two instances would overwrite each other's ability edits."""
    lock = QLockFile(str(home / "pvptimer.lock"))
    lock.setStaleLockTime(0)  # a lock left by a crashed instance is detected by its dead PID
    return lock if lock.tryLock(100) else None


def ask_running_instance_to_show(name: str = SERVER_NAME) -> bool:
    """Called by a second launch. True if the running instance was reached."""
    socket = QLocalSocket()
    socket.connectToServer(name)
    reached = socket.waitForConnected(1000)
    socket.abort()
    return reached


class InstanceServer(QObject):
    """Listens for second launches; emits `activated` when one connects."""
    activated = Signal()

    def __init__(self, name: str = SERVER_NAME) -> None:
        super().__init__()
        self._server = QLocalServer(self)
        QLocalServer.removeServer(name)  # clear a leftover from a crashed instance
        self._server.newConnection.connect(self._on_connection)
        self._server.listen(name)

    def close(self) -> None:
        self._server.close()

    def _on_connection(self) -> None:
        while self._server.hasPendingConnections():
            self._server.nextPendingConnection().deleteLater()
        self.activated.emit()
