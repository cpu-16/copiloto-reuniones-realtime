"""De-risk de captura: lista targets de PipeWire y graba 5s del monitor del sink.
Uso:
    python scripts/derisk_audio.py --list
    python scripts/derisk_audio.py --target <node-id-o-nombre> --out prueba.wav
Luego abre prueba.wav y confirma que se oye el audio del sistema (los demás).
"""
import argparse
import subprocess
import sys
import wave


def list_targets() -> None:
    print("=== pw-record --list-targets ===")
    subprocess.run(["pw-record", "--list-targets"], check=False)
    print("\n=== wpctl status (busca el sink de salida por defecto) ===")
    subprocess.run(["wpctl", "status"], check=False)


def record(target: str, out: str, seconds: int = 5, rate: int = 16000) -> None:
    cmd = ["pw-record", "--rate", str(rate), "--channels", "1", "--format", "s16"]
    if target:
        cmd += ["--target", target]
    cmd += [out]
    print(f"Grabando {seconds}s -> {out}\n  cmd: {' '.join(cmd)}")
    proc = subprocess.Popen(cmd)
    try:
        proc.wait(timeout=seconds)
    except subprocess.TimeoutExpired:
        proc.terminate()
        proc.wait()
    with wave.open(out, "rb") as w:
        frames = w.getnframes()
    print(f"OK: {frames} frames grabados ({frames / rate:.1f}s).")
    if frames == 0:
        print("ADVERTENCIA: 0 frames. Target equivocado o sin audio sonando.")
        sys.exit(1)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--target", default="")
    ap.add_argument("--out", default="prueba.wav")
    args = ap.parse_args()
    if args.list:
        list_targets()
    else:
        record(args.target, args.out)


if __name__ == "__main__":
    main()
