"""Ventana flotante NATIVA (PySide6 / QtWidgets) — sin QtWebEngine.

Se conecta al orquestador por WebSocket (QWebSocket) y muestra: estado, panel del
copiloto (resumen + ideas + alerta), transcripción en vivo, tarjeta de sugerencia
proactiva, un panel lateral de respuestas a pedido (con pestañas) y una caja para
preguntarle a Claude. Frameless, siempre-encima, arrastrable. Temas: oscuro/claro/vidrio.
Controles: pausar captura, minimizar, expandir, cerrar.
"""
from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "xcb")  # XWayland: frameless/on-top fiables

import json  # noqa: E402
from datetime import datetime  # noqa: E402

from asistente.ui.history import append_history  # noqa: E402

from PySide6.QtCore import Qt, QUrl  # noqa: E402
from PySide6.QtWebSockets import QWebSocket  # noqa: E402
from PySide6.QtWidgets import (  # noqa: E402
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QTextEdit,
    QLineEdit, QPushButton, QFrame, QSizeGrip, QStackedWidget, QButtonGroup,
)

# Pestañas del panel de respuestas a pedido: (tab_id, etiqueta del botón lanzador,
# instrucción que se manda a Claude). La pestaña "libre" se llena con el cuadro de abajo.
QUICK_ACTIONS = [
    ("ideas", "💡 Ideas", "Dame 2-3 ideas o aportes inteligentes que yo podría decir o preguntar ahora mismo."),
    ("resumen", "📝 Resumen", "Resume en 3 viñetas breves lo que se ha hablado hasta ahora."),
    ("pregunto", "❓ ¿Qué pregunto?", "Sugiéreme 2 buenas preguntas que yo podría hacer ahora."),
    ("respondo", "🙋 Responder", "Ayúdame a responder lo último que se dijo, con una respuesta breve que yo podría dar."),
]
# Orden e iconos de las pestañas dentro del panel ("libre" = cuadro de texto;
# "contexto" = briefing durable editable de la sesión).
PANEL_TABS = [
    ("ideas", "💡"), ("resumen", "📝"), ("pregunto", "❓"),
    ("respondo", "🙋"), ("libre", "💬"), ("contexto", "📋"),
]
TAB_TITLES = {
    "ideas": "💡 Ideas", "resumen": "📝 Resumen", "pregunto": "❓ Preguntas",
    "respondo": "🙋 Responder", "libre": "💬 Pregunta libre",
    "contexto": "📋 Contexto de sesión",
}
# Pestañas que NO se consultan a Claude al abrirlas (se llenan a mano).
_NO_ASK_TABS = {"libre", "contexto"}
PROMPTS = {tab: prompt for tab, _label, prompt in QUICK_ACTIONS}

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
    {  # vidrio (muy transparente)
        "root": "rgba(30,34,44,90)", "bar": "rgba(40,44,56,120)",
        "text": "#f0f4ff", "sub": "#bbddff", "title": "#bbccdd",
        "live": "#ccddee", "card": "rgba(26,60,44,210)", "cardbd": "#55cc99",
        "cardtx": "#eeffff", "inbg": "rgba(20,24,32,120)", "intx": "#ffffff",
        "inbd": "rgba(180,200,230,90)", "btn": "rgba(60,66,80,140)", "btntx": "#eeeeff",
        "ins": "rgba(30,36,52,210)", "instx": "#e6ecff",
    },
    {  # vidrio legible (semi-transparente pero con letras claras)
        "root": "rgba(16,18,26,210)", "bar": "rgba(28,32,44,228)",
        "text": "#f2f5ff", "sub": "#bfe3ff", "title": "#c2cfe0",
        "live": "#aebccf", "card": "rgba(20,52,36,228)", "cardbd": "#44cc88",
        "cardtx": "#ecfff5", "inbg": "rgba(12,14,20,220)", "intx": "#ffffff",
        "inbd": "rgba(150,170,200,130)", "btn": "rgba(48,54,70,225)", "btntx": "#eef",
        "ins": "rgba(24,28,42,220)", "instx": "#dde7ff",
    },
]
THEME_NAMES = ["oscuro", "claro", "vidrio", "vidrio legible"]
_NORMAL = (420, 560)
_EXPANDED = (760, 860)
_PANEL_W = 340          # ancho extra que añade el panel lateral
_PAUSED_COLOR = "#e6b450"


def _qss(t: dict) -> str:
    return f"""
    #root {{ background: {t['root']}; }}
    #bar {{ background: {t['bar']}; }}
    QLabel#status {{ color: {t['sub']}; font-size: 11px; }}
    QLabel#status[paused="true"] {{ color: {_PAUSED_COLOR}; font-weight: bold; }}
    QLabel#title {{ color: {t['title']}; font-size: 11px; }}
    QLabel#insight {{ background: {t['ins']}; color: {t['instx']}; padding: 6px 9px;
                      font-size: 12px; border-bottom: 1px solid {t['cardbd']}; }}
    QTextEdit#transcript {{ background: {t['ins']}; color: {t['text']};
                            border: none; font-size: 13px; padding: 4px 8px; }}
    QLabel#live {{ background: {t['ins']}; color: {t['live']}; font-style: italic;
                   padding: 2px 8px; }}
    QLabel#suggestion {{ background: {t['card']}; color: {t['cardtx']};
                         border-top: 1px solid {t['cardbd']}; padding: 8px; font-size: 13px; }}
    QLineEdit {{ background: {t['inbg']}; color: {t['intx']}; border: 1px solid {t['inbd']};
                 border-radius: 6px; padding: 6px; }}
    QPushButton {{ background: {t['btn']}; color: {t['btntx']}; border: none;
                   border-radius: 5px; padding: 4px 8px; font-size: 12px; }}
    QPushButton:hover {{ background: {t['cardbd']}; }}
    QPushButton#pausebtn[paused="true"] {{ background: {_PAUSED_COLOR}; color: #1a1a22; }}
    #panel {{ background: {t['ins']}; border-left: 1px solid {t['cardbd']}; }}
    QLabel#panelhdr {{ color: {t['sub']}; font-size: 12px; font-weight: bold; padding: 2px 4px; }}
    QPushButton#ptab {{ background: {t['btn']}; color: {t['btntx']}; padding: 4px 7px;
                        font-size: 13px; }}
    QPushButton#ptab:checked {{ background: {t['cardbd']}; color: #ffffff; }}
    QTextEdit#answer {{ background: transparent; color: {t['instx']};
                        border: none; font-size: 13px; }}
    """


class AssistantWidget(QWidget):
    def __init__(self, ws_url: str) -> None:
        super().__init__()
        self._url = ws_url
        self._drag_off = None
        self._theme = 0
        self._expanded = False
        self._paused = False
        self._ghost = False               # modo fantasma: ventana atravesable (click-through)
        self._loaded: set[str] = set()    # pestañas con respuesta ya cargada
        self._pending: set[str] = set()   # pestañas esperando respuesta
        self._tab_edit: dict[str, QTextEdit] = {}
        self._tab_index: dict[str, int] = {}
        self._index_tab: dict[int, str] = {}
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
        self.pause_btn = QPushButton("⏸")
        self.pause_btn.setObjectName("pausebtn")
        self.pause_btn.setToolTip("Pausar/reanudar captura")
        self.pause_btn.clicked.connect(self._toggle_pause)
        barl.addWidget(self.pause_btn)
        self.ghost_btn = QPushButton("👻")
        self.ghost_btn.setToolTip(
            "Modo fantasma: la ventana se vuelve atravesable (los clics pasan a lo de "
            "atrás). Para volver, usa el atajo global de fantasma.")
        self.ghost_btn.clicked.connect(self._toggle_ghost)
        barl.addWidget(self.ghost_btn)
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

        # Fila de 2 columnas: izquierda (transcripción/flujo) + panel lateral de respuestas
        cols = QHBoxLayout()
        cols.setContentsMargins(0, 0, 0, 0)
        cols.setSpacing(0)

        left = QVBoxLayout()
        left.setContentsMargins(0, 0, 0, 0)
        left.setSpacing(0)

        self.insight = QLabel("")
        self.insight.setObjectName("insight")
        self.insight.setWordWrap(True)
        self.insight.setVisible(False)
        left.addWidget(self.insight)

        self.transcript = QTextEdit()
        self.transcript.setObjectName("transcript")
        self.transcript.setReadOnly(True)
        left.addWidget(self.transcript, 1)

        self.live = QLabel("")
        self.live.setObjectName("live")
        self.live.setWordWrap(True)
        left.addWidget(self.live)

        self.suggestion = QLabel("💡 La respuesta sugerida aparecerá aquí.")
        self.suggestion.setObjectName("suggestion")
        self.suggestion.setWordWrap(True)
        left.addWidget(self.suggestion)

        cols.addLayout(left, 1)
        cols.addWidget(self._build_panel())
        body.addLayout(cols, 1)

        # Botones lanzadores de respuestas a pedido (un toque = abre panel + pestaña + consulta)
        quickrow = QFrame()
        quickrow.setObjectName("bar")
        ql = QHBoxLayout(quickrow)
        ql.setContentsMargins(6, 4, 6, 4)
        ql.setSpacing(4)
        for tab, label, _prompt in QUICK_ACTIONS:
            b = QPushButton(label)
            b.clicked.connect(lambda _=False, tb=tab: self._open_tab(tb))
            ql.addWidget(b)
        body.addWidget(quickrow)

        # Caja para preguntar (cae en la pestaña "libre")
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

    def _build_panel(self) -> QWidget:
        """Panel lateral derecho: pestañas + respuestas a pedido (persistentes)."""
        self.panel = QFrame()
        self.panel.setObjectName("panel")
        self.panel.setFixedWidth(_PANEL_W)
        self.panel.setVisible(False)
        pl = QVBoxLayout(self.panel)
        pl.setContentsMargins(6, 6, 6, 6)
        pl.setSpacing(4)

        # Fila de pestañas (navegación entre respuestas ya pedidas)
        tabrow = QHBoxLayout()
        tabrow.setContentsMargins(0, 0, 0, 0)
        tabrow.setSpacing(3)
        self._tab_group = QButtonGroup(self)
        self._tab_group.setExclusive(True)
        self._tab_buttons: list[QPushButton] = []
        for i, (tab, icon) in enumerate(PANEL_TABS):
            tb = QPushButton(icon)
            tb.setObjectName("ptab")
            tb.setCheckable(True)
            tb.setToolTip(TAB_TITLES[tab])
            tb.clicked.connect(lambda _=False, t=tab: self._open_tab(t))
            self._tab_group.addButton(tb)
            tabrow.addWidget(tb)
            self._tab_buttons.append(tb)
            self._tab_index[tab] = i
            self._index_tab[i] = tab
        tabrow.addStretch(1)
        pl.addLayout(tabrow)

        self.panel_hdr = QLabel("")
        self.panel_hdr.setObjectName("panelhdr")
        pl.addWidget(self.panel_hdr)

        self.stack = QStackedWidget()
        for tab, _icon in PANEL_TABS:
            edit = QTextEdit()
            edit.setObjectName("answer")
            if tab == "contexto":   # editable: el usuario escribe el briefing
                edit.setReadOnly(False)
                edit.setPlaceholderText(
                    "Proyecto, participantes, objetivos, términos… "
                    "(se envía a Claude como contexto durable de la sesión)")
            else:
                edit.setReadOnly(True)
                edit.setPlaceholderText("Toca esta pestaña para pedirlo…")
            self._tab_edit[tab] = edit
            self.stack.addWidget(edit)
        pl.addWidget(self.stack, 1)

        # Acciones del panel
        actrow = QHBoxLayout()
        actrow.setContentsMargins(0, 0, 0, 0)
        actrow.setSpacing(4)
        for label, slot in [("🔄 actualizar", self._refresh_tab),
                            ("💾 contexto", self._save_briefing),
                            ("🧹 limpiar", self._clear_tab),
                            ("copiar", self._copy_tab), ("✕", self._close_panel)]:
            b = QPushButton(label)
            b.clicked.connect(slot)
            actrow.addWidget(b)
        pl.addLayout(actrow)
        return self.panel

    # ---- tamaño / temas ----
    def _base_size(self) -> tuple[int, int]:
        return _EXPANDED if self._expanded else _NORMAL

    def _apply_size(self) -> None:
        w, h = self._base_size()
        if self.panel.isVisible():
            w += _PANEL_W
        self.resize(w, h)

    def _apply_theme(self) -> None:
        self.setStyleSheet(_qss(THEMES[self._theme]))

    def _cycle_theme(self) -> None:
        self._theme = (self._theme + 1) % len(THEMES)
        self._apply_theme()

    def _toggle_min(self) -> None:
        if self.body.isVisible():
            self.body.hide()
            self.adjustSize()
        else:
            self.body.show()
            self._apply_size()

    def _toggle_expand(self) -> None:
        if not self.body.isVisible():
            self.body.show()
        self._expanded = not self._expanded
        self._apply_size()

    # ---- panel de respuestas ----
    def _open_panel(self) -> None:
        if not self.panel.isVisible():
            self.panel.setVisible(True)
            self._apply_size()

    def _close_panel(self) -> None:
        if self.panel.isVisible():
            self.panel.setVisible(False)
            self._apply_size()

    def _open_tab(self, tab: str) -> None:
        """Muestra el panel en la pestaña dada; si está vacía, dispara la consulta.
        Si ya tiene contenido, solo la muestra (no re-consulta)."""
        self._open_panel()
        self._select_tab(tab)
        if tab not in _NO_ASK_TABS and tab not in self._loaded and tab not in self._pending:
            self._ask_tab(tab)

    def _select_tab(self, tab: str) -> None:
        i = self._tab_index[tab]
        self.stack.setCurrentIndex(i)
        self.panel_hdr.setText(TAB_TITLES[tab])
        self._tab_buttons[i].setChecked(True)

    def _ask_tab(self, tab: str) -> None:
        # "pensando" va al encabezado, NO al cuerpo: así no se pisa el historial.
        self._pending.add(tab)
        self.panel_hdr.setText(TAB_TITLES[tab] + "  ⏳…")
        self.ws.sendTextMessage(json.dumps({"type": "ask", "text": PROMPTS[tab], "tab": tab}))

    def _refresh_tab(self) -> None:
        tab = self._index_tab[self.stack.currentIndex()]
        if tab in _NO_ASK_TABS:
            return  # libre/contexto se llenan a mano, no tienen prompt fijo
        self._loaded.discard(tab)
        self._ask_tab(tab)

    def _save_briefing(self) -> None:
        """Envía el contenido de la pestaña Contexto como briefing durable."""
        edit = self._tab_edit.get("contexto")
        if edit is None:
            return
        self.ws.sendTextMessage(
            json.dumps({"type": "briefing.set", "text": edit.toPlainText()}))
        self.panel_hdr.setText(TAB_TITLES["contexto"] + "  ✓ guardado")

    def _clear_tab(self) -> None:
        tab = self._index_tab[self.stack.currentIndex()]
        self._tab_edit[tab].clear()
        self._loaded.discard(tab)

    def _copy_tab(self) -> None:
        tab = self._index_tab[self.stack.currentIndex()]
        text = self._tab_edit[tab].toPlainText()
        if text and not text.startswith("⏳"):
            QApplication.clipboard().setText(text)

    # ---- pausa ----
    def _toggle_pause(self) -> None:
        # Manda el comando; la UI se actualiza al recibir el Status difundido por el server.
        self.ws.sendTextMessage(json.dumps({"type": "capture", "paused": not self._paused}))

    def _set_paused_ui(self, paused: bool) -> None:
        self._paused = paused
        self.pause_btn.setText("▶" if paused else "⏸")
        for w in (self.status, self.pause_btn):
            w.setProperty("paused", "true" if paused else "false")
            w.style().unpolish(w)
            w.style().polish(w)

    # ---- modo fantasma (click-through) ----
    def _ghost_http_url(self) -> str:
        """Deriva la URL http /ghost desde la ws_url (para el curl de emergencia)."""
        u = self._url.replace("wss://", "https://").replace("ws://", "http://")
        return u.replace("/ws?", "/ghost?")

    def _toggle_ghost(self) -> None:
        """Alterna click-through: la ventana se vuelve atravesable (los clics pasan a la
        app de atrás) y semitransparente. Cambiar el flag exige re-mostrar la ventana, así
        que preservamos la geometría. SALIDAS: el atajo Super+G, el atajo mostrar/ocultar,
        o el curl que se imprime abajo (para no quedar atrapado sin atajos)."""
        self._ghost = not self._ghost
        geo = self.geometry()
        self.setWindowFlag(Qt.WindowTransparentForInput, self._ghost)
        self.setWindowOpacity(0.6 if self._ghost else 1.0)
        self.show()                 # re-aplica el flag (si no, no surte efecto)
        self.setGeometry(geo)       # evita que el re-show la reubique
        if self._ghost:
            print("\n  👻 Modo fantasma ON (ventana atravesable). Para salir:")
            print("     · atajo Super+G  · tu atajo de mostrar/ocultar  · o ejecuta:")
            print(f'     curl -s "{self._ghost_http_url()}"\n')

    # ---- arrastre ----
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

    # ---- WebSocket ----
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
            sb = self.transcript.verticalScrollBar()   # auto-scroll a lo último
            sb.setValue(sb.maximum())
        elif t == "suggestion":
            self.suggestion.setText("💡 " + m.get("text", ""))
        elif t == "answer":
            tab = m.get("tab", "libre")
            edit = self._tab_edit.get(tab)
            if edit is not None:
                # Acumula: la respuesta nueva se añade debajo de las anteriores con hora.
                when = datetime.now().strftime("%H:%M")
                edit.setPlainText(append_history(edit.toPlainText(), m.get("text", ""), when))
                self._loaded.add(tab)
                self._pending.discard(tab)
                self._open_panel()
                self._select_tab(tab)
                sb = edit.verticalScrollBar()   # auto-scroll a lo último
                sb.setValue(sb.maximum())
        elif t == "briefing.state":
            edit = self._tab_edit.get("contexto")
            # No pisar si el usuario está editando justo ahora.
            if edit is not None and not edit.hasFocus():
                edit.setPlainText(m.get("text", ""))
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
                if self._ghost:           # mostrar SIEMPRE restaura interactividad
                    self._toggle_ghost()
                self.show()
                self.raise_()
                self.activateWindow()
        elif t == "ghost":
            self._toggle_ghost()   # atajo global de modo fantasma (curl /ghost)
        elif t == "status":
            state = m.get("state", "")
            detail = m.get("detail", "")
            self.status.setText(state + (f" — {detail}" if detail else ""))
            if state in ("pausado", "capturando"):
                self._set_paused_ui(state == "pausado")

    def _send(self) -> None:
        text = self.ask.text().strip()
        if not text:
            return
        self._open_panel()
        self._select_tab("libre")
        self._pending.add("libre")
        self.panel_hdr.setText(TAB_TITLES["libre"] + "  ⏳…")
        self.ws.sendTextMessage(json.dumps({"type": "ask", "text": text, "tab": "libre"}))
        self.ask.clear()

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
