"""Ventana flotante NATIVA (PySide6 / QtWidgets) — sin QtWebEngine.

Se conecta al orquestador por WebSocket (QWebSocket) y muestra: estado, panel del
copiloto (resumen + ideas + alerta), transcripción en vivo, tarjeta de sugerencia,
botones rápidos y una caja para preguntarle a Claude. Frameless, siempre-encima,
arrastrable. Temas: oscuro/claro/vidrio. Controles: minimizar, expandir, cerrar.
"""
from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "xcb")  # XWayland: frameless/on-top fiables

import json  # noqa: E402

from PySide6.QtCore import Qt, QUrl  # noqa: E402
from PySide6.QtWebSockets import QWebSocket  # noqa: E402
from PySide6.QtWidgets import (  # noqa: E402
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QTextEdit,
    QLineEdit, QPushButton, QFrame, QSizeGrip,
)

# Botones rápidos: (etiqueta, instrucción que se manda a Claude con el contexto vivo)
QUICK_ACTIONS = [
    ("💡 Ideas", "Dame 2-3 ideas o aportes inteligentes que yo podría decir o preguntar ahora mismo."),
    ("📝 Resumen", "Resume en 3 viñetas breves lo que se ha hablado hasta ahora."),
    ("❓ ¿Qué pregunto?", "Sugiéreme 2 buenas preguntas que yo podría hacer ahora."),
    ("🙋 Responder", "Ayúdame a responder lo último que se dijo, con una respuesta breve que yo podría dar."),
]

THEMES = [
    {  # oscuro
        "root": "rgba(20,20,26,235)", "bar": "rgba(27,27,34,240)",
        "text": "#eee", "sub": "#88ffdd", "title": "#8899aa",
        "live": "#99aabb", "card": "rgba(20,48,31,240)", "cardbd": "#22aa55",
        "cardtx": "#ddffee", "inbg": "rgba(14,14,18,235)", "intx": "#eee",
        "inbd": "#444", "btn": "rgba(42,42,51,240)", "btntx": "#eee",
        "ins": "rgba(24,28,40,235)", "instx": "#cdd6f4",
    },
    {  # claro
        "root": "rgba(246,248,251,242)", "bar": "rgba(228,232,238,245)",
        "text": "#1a1a22", "sub": "#00aa77", "title": "#556677",
        "live": "#446677", "card": "rgba(214,245,224,245)", "cardbd": "#33aa77",
        "cardtx": "#114433", "inbg": "rgba(255,255,255,242)", "intx": "#111",
        "inbd": "#bbbbcc", "btn": "rgba(220,224,230,245)", "btntx": "#222",
        "ins": "rgba(225,232,245,245)", "instx": "#243047",
    },
    {  # vidrio
        "root": "rgba(30,34,44,90)", "bar": "rgba(40,44,56,120)",
        "text": "#f0f4ff", "sub": "#bbddff", "title": "#bbccdd",
        "live": "#ccddee", "card": "rgba(30,70,50,120)", "cardbd": "#55cc99",
        "cardtx": "#eeffff", "inbg": "rgba(20,24,32,120)", "intx": "#ffffff",
        "inbd": "rgba(180,200,230,90)", "btn": "rgba(60,66,80,140)", "btntx": "#eeeeff",
        "ins": "rgba(40,46,62,120)", "instx": "#e6ecff",
    },
]
THEME_NAMES = ["oscuro", "claro", "vidrio"]
_NORMAL = (420, 560)
_EXPANDED = (760, 860)


def _qss(t: dict) -> str:
    return f"""
    #root {{ background: {t['root']}; }}
    #bar {{ background: {t['bar']}; }}
    QLabel#status {{ color: {t['sub']}; font-size: 11px; }}
    QLabel#title {{ color: {t['title']}; font-size: 11px; }}
    QLabel#insight {{ background: {t['ins']}; color: {t['instx']}; padding: 6px 9px;
                      font-size: 12px; border-bottom: 1px solid {t['cardbd']}; }}
    QTextEdit#transcript {{ background: transparent; color: {t['text']};
                            border: none; font-size: 13px; }}
    QLabel#live {{ color: {t['live']}; font-style: italic; padding: 2px 8px; }}
    QLabel#suggestion {{ background: {t['card']}; color: {t['cardtx']};
                         border-top: 1px solid {t['cardbd']}; padding: 8px; font-size: 13px; }}
    QLineEdit {{ background: {t['inbg']}; color: {t['intx']}; border: 1px solid {t['inbd']};
                 border-radius: 6px; padding: 6px; }}
    QPushButton {{ background: {t['btn']}; color: {t['btntx']}; border: none;
                   border-radius: 5px; padding: 4px 8px; font-size: 12px; }}
    QPushButton:hover {{ background: {t['cardbd']}; }}
    """


class AssistantWidget(QWidget):
    def __init__(self, ws_url: str) -> None:
        super().__init__()
        self._url = ws_url
        self._drag_off = None
        self._theme = 0
        self._expanded = False
        self._restore_size = _NORMAL
        self._build_ui()
        self._apply_theme()
        self._connect_ws()

    def _build_ui(self) -> None:
        self.setObjectName("root")
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.resize(*_NORMAL)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Barra superior
        bar = QFrame()
        bar.setObjectName("bar")
        barl = QHBoxLayout(bar)
        barl.setContentsMargins(8, 5, 8, 5)
        self.status = QLabel("conectando…")
        self.status.setObjectName("status")
        barl.addWidget(self.status)
        barl.addStretch(1)
        for label, slot in [("tema", self._cycle_theme), ("limpiar", self._clear),
                            ("–", self._toggle_min), ("⤢", self._toggle_expand),
                            ("✕", self.close)]:
            b = QPushButton(label)
            b.clicked.connect(slot)
            barl.addWidget(b)
        root.addWidget(bar)

        # Cuerpo (se oculta al minimizar)
        self.body = QWidget()
        body = QVBoxLayout(self.body)
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)

        self.insight = QLabel("")
        self.insight.setObjectName("insight")
        self.insight.setWordWrap(True)
        self.insight.setVisible(False)
        body.addWidget(self.insight)

        self.transcript = QTextEdit()
        self.transcript.setObjectName("transcript")
        self.transcript.setReadOnly(True)
        body.addWidget(self.transcript, 1)

        self.live = QLabel("")
        self.live.setObjectName("live")
        self.live.setWordWrap(True)
        body.addWidget(self.live)

        self.suggestion = QLabel("💡 La respuesta sugerida aparecerá aquí.")
        self.suggestion.setObjectName("suggestion")
        self.suggestion.setWordWrap(True)
        body.addWidget(self.suggestion)

        # Botones rápidos
        quickrow = QFrame()
        quickrow.setObjectName("bar")
        ql = QHBoxLayout(quickrow)
        ql.setContentsMargins(6, 4, 6, 4)
        ql.setSpacing(4)
        for label, prompt in QUICK_ACTIONS:
            b = QPushButton(label)
            b.clicked.connect(lambda _=False, p=prompt: self._quick(p))
            ql.addWidget(b)
        body.addWidget(quickrow)

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
        body.addWidget(askrow)

        griprow = QHBoxLayout()
        griprow.setContentsMargins(0, 0, 2, 2)
        griprow.addStretch(1)
        griprow.addWidget(QSizeGrip(self), 0, Qt.AlignRight | Qt.AlignBottom)
        body.addLayout(griprow)

        root.addWidget(self.body, 1)

    def _apply_theme(self) -> None:
        self.setStyleSheet(_qss(THEMES[self._theme]))

    def _cycle_theme(self) -> None:
        self._theme = (self._theme + 1) % len(THEMES)
        self._apply_theme()

    def _toggle_min(self) -> None:
        if self.body.isVisible():
            self._restore_size = (self.width(), self.height())
            self.body.hide()
            self.adjustSize()
        else:
            self.body.show()
            self.resize(*self._restore_size)

    def _toggle_expand(self) -> None:
        if not self.body.isVisible():
            self.body.show()
        self._expanded = not self._expanded
        self.resize(*(_EXPANDED if self._expanded else _NORMAL))

    # arrastre
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

    # WebSocket
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
            self.suggestion.setText("💡 " + m.get("text", ""))
        elif t == "insight":
            parts = []
            if m.get("summary"):
                parts.append("🧠 " + m["summary"])
            if m.get("ideas"):
                parts.append("💡 " + m["ideas"])
            if m.get("alert"):
                parts.append("📌 " + m["alert"])
            self.insight.setText("\n".join(parts))
            self.insight.setVisible(bool(parts))
        elif t == "toggle":
            if self.isVisible():
                self.hide()
            else:
                self.show()
                self.raise_()
                self.activateWindow()
        elif t == "status":
            detail = m.get("detail", "")
            self.status.setText(m.get("state", "") + (f" — {detail}" if detail else ""))

    def _send(self) -> None:
        text = self.ask.text().strip()
        if not text:
            return
        self.ws.sendTextMessage(json.dumps({"type": "ask", "text": text}))
        self.ask.clear()

    def _quick(self, prompt: str) -> None:
        self.ws.sendTextMessage(json.dumps({"type": "ask", "text": prompt}))

    def _clear(self) -> None:
        self.transcript.clear()
        self.live.setText("")

    def closeEvent(self, e) -> None:
        try:
            self.ws.close()
        except Exception:
            pass
        e.accept()
        app = QApplication.instance()
        if app is not None:
            app.quit()


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
