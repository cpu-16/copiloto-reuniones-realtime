"""Abre la UI web dentro de una ventana nativa sin bordes, siempre-encima y
arrastrable, usando pywebview."""
from __future__ import annotations

import webview


def open_window(url: str, title: str = "Asistente") -> None:
    webview.create_window(
        title,
        url=url,
        width=420,
        height=560,
        frameless=True,
        easy_drag=True,
        on_top=True,
        transparent=False,
    )
    webview.start()


if __name__ == "__main__":
    import sys
    open_window(sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8765/")
