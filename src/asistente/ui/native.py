"""Ventana flotante NATIVA (PySide6 / QtWidgets) — sin QtWebEngine.

QtWebEngine (el motor de navegador de pywebview) segfaultea en este Wayland, pero
QtWidgets es estable. Este widget se conecta al orquestador por WebSocket (QWebSocket)
y muestra: estado, transcripción en vivo (con línea de parcial), tarjeta de sugerencia
y una caja para preguntarle a Claude. Es frameless, siempre-encima y arrastrable.
"""
from __future__ import annotations

import os

# En Wayland nativo los clientes no pueden fijar always-on-top ni posicionar
# ventanas frameless de forma fiable; forzamos XWayland (xcb).
os.environ.setdefault("QT_QPA_PLATFORM", "xcb")

import json  # noqa: E402

from PySide6.QtCore import Qt, QUrl  # noqa: E402
from PySide6.QtWebSockets import QWebSocket  # noqa: E402
from PySide6.QtWidgets import (  # noqa: E402
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QTextEdit,
    QLineEdit, QPushButton, QFrame,
)

_STYLE = """
#root { background: #14141a; }
#bar { background: #1b1b22; }
QLabel#status { color: #8fd; font-size: 11px; }
QLabel#title { color: #889; font-size: 11px; }
QTextEdit#transcript { background: #14141a; color: #eee; border: none; font-size: 13px; }
QLabel#live { color: #9ab; font-style: italic; padding: 2px 8px; }
QLabel#suggestion { background: #14301f; color: #dfe; border-top: 1px solid #2a5;
                    padding: 8px; font-size: 13px; }
QLabel#suggestionEmpty { background: #181820; color: #678; border-top: 1px solid #333;
                         padding: 8px; font-size: 13px; }
QLineEdit { background: #0e0e12; color: #eee; border: 1px solid #444;
            border-radius: 6px; padding: 6px; }
QPushButton { background: #2a2a33; color: #eee; border: none; border-radius: 5px;
              padding: 4px 10px; }
QPushButton:hover { background: #3a3a45; }
"""


class AssistantWidget(QWidget):
    def __init__(self, ws_url: str) -> None:
        super().__init__()
        self._url = ws_url
        self._drag_off = None
        self._has_suggestion = False
        self._build_ui()
        self._connect_ws()

    # ---------- UI ----------
    def _build_ui(self) -> None:
        self.setObjectName("root")
        self.setWindowFlags(
            Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool
        )
        self.setStyleSheet(_STYLE)
        self.resize(420, 560)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Barra superior (arrastrable)
        bar = QFrame()
        bar.setObjectName("bar")
        barl = QHBoxLayout(bar)
        barl.setContentsMargins(8, 5, 8, 5)
        self.status = QLabel("conectando…")
        self.status.setObjectName("status")
        title = QLabel("Asistente")
        title.setObjectName("title")
        clear_btn = QPushButton("limpiar")
        clear_btn.clicked.connect(self._clear)
        close_btn = QPushButton("✕")
        close_btn.clicked.connect(self.close)
        barl.addWidget(self.status)
        barl.addStretch(1)
        barl.addWidget(title)
        barl.addWidget(clear_btn)
        barl.addWidget(close_btn)
        root.addWidget(bar)

        # Transcripción (finales) + línea viva (parcial)
        self.transcript = QTextEdit()
        self.transcript.setObjectName("transcript")
        self.transcript.setReadOnly(True)
        root.addWidget(self.transcript, 1)

        self.live = QLabel("")
        self.live.setObjectName("live")
        self.live.setWordWrap(True)
        root.addWidget(self.live)

        # Tarjeta de sugerencia
        self.suggestion = QLabel("💡 La respuesta sugerida aparecerá aquí.")
        self.suggestion.setObjectName("suggestionEmpty")
        self.suggestion.setWordWrap(True)
        root.addWidget(self.suggestion)

        # Caja para preguntar
        askrow = QFrame()
        askrow.setObjectName("bar")
        al = QHBoxLayout(askrow)
        al.setContentsMargins(8, 6, 8, 6)
        self.ask = QLineEdit()
        self.ask.setPlaceholderText("Pregúntale a Claude sobre la reunión…")
        self.ask.returnPressed.connect(self._send)
        send_btn = QPushButton("Preguntar")
        send_btn.clicked.connect(self._send)
        al.addWidget(self.ask, 1)
        al.addWidget(send_btn)
        root.addWidget(askrow)

    # ---------- arrastre ----------
    def mousePressEvent(self, e) -> None:
        if e.button() == Qt.LeftButton:
            self._drag_off = e.globalPosition().toPoint() - self.frameGeometry().topLeft()
            e.accept()

    def mouseMoveEvent(self, e) -> None:
        if self._drag_off is not None and e.buttons() & Qt.LeftButton:
            self.move(e.globalPosition().toPoint() - self._drag_off)
            e.accept()

    def mouseReleaseEvent(self, e) -> None:
        self._drag_off = None

    # ---------- WebSocket ----------
    def _connect_ws(self) -> None:
        self.ws = QWebSocket()
        self.ws.connected.connect(lambda: self.status.setText("conectado"))
        self.ws.disconnected.connect(lambda: self.status.setText("desconectado"))
        self.ws.textMessageReceived.connect(self._on_msg)
        self.ws.open(QUrl(self._url))

    def _on_msg(self, raw: str) -> None:
        try:
            m = json.loads(raw)
        except json.JSONDecodeError:
            return
        t = m.get("type")
        if t == "transcript.partial":
            self.live.setText(m.get("text", ""))
        elif t == "transcript.final":
            self.transcript.append(m.get("text", ""))
            self.live.setText("")
        elif t == "suggestion":
            self.suggestion.setObjectName("suggestion")
            self.suggestion.setStyleSheet(_STYLE)  # re-aplica para el nuevo objectName
            self.suggestion.setText("💡 " + m.get("text", ""))
        elif t == "status":
            detail = m.get("detail", "")
            self.status.setText(m.get("state", "") + (f" — {detail}" if detail else ""))

    def _send(self) -> None:
        text = self.ask.text().strip()
        if not text:
            return
        self.ws.sendTextMessage(json.dumps({"type": "ask", "text": text}))
        self.ask.clear()

    def _clear(self) -> None:
        self.transcript.clear()
        self.live.setText("")


def open_widget(ws_url: str) -> None:
    app = QApplication.instance() or QApplication([])
    w = AssistantWidget(ws_url)
    w.show()
    app.exec()


if __name__ == "__main__":
    import sys
    url = sys.argv[1] if len(sys.argv) > 1 else \
        "ws://127.0.0.1:8765/ws?token=cambia-este-token"
    open_widget(url)
