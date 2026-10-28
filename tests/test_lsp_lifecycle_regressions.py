from __future__ import annotations

import gc
import weakref

import pytest

pytest.importorskip("PySide6")
from PySide6.QtCore import QCoreApplication, QEvent, QEventLoop, QTimer

from core.lsp_servers import ResolvedLspServer
from core.lsp_transport import LspManager


@pytest.mark.parametrize("transport", ["stdio", "external_tcp"])
def test_retired_client_cannot_restart_and_transient_owner_is_not_retained(tmp_path, transport):
    manager = LspManager(project_root=tmp_path, launch_guard=lambda: True)
    server = ResolvedLspServer("Python", "python", "must-not-run", (), transport=transport, port=6008)
    connection = manager._make_connection(server)
    manager._wire_connection(connection)
    manager.connections["Python"] = connection
    connection._set_state(connection.RESTARTING)
    connection._restart_timer.start(60_000)
    manager.shutdown_all(wait=False)
    assert not connection._restart_timer.isActive()
    # Retirement is final even though the manager still points at the same root.
    connection.start()
    assert connection.state == connection.STOPPED
    assert not connection.is_running()
    manager_ref, connection_ref = weakref.ref(manager), weakref.ref(connection)
    del manager, connection
    gc.collect()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    QCoreApplication.processEvents()
    gc.collect()
    assert manager_ref() is None
    assert connection_ref() is None
    # A later nested event loop used to flush a child-delete event which released
    # its last strong parent reference inside QObject::~QObject and crashed.
    loop = QEventLoop()
    QTimer.singleShot(0, loop.quit)
    loop.exec()
