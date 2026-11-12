#!/usr/bin/env python3
"""
Installs Apache JMeter (and a Java runtime if none is found) into ~/tools - no admin rights needed.

    python scripts/install_jmeter.py

* Verifies JMeter's SHA-512 checksum.
* Reuses an existing Java (JAVA_HOME or PATH, version 8+); otherwise downloads Eclipse Temurin JRE 17.
* Safe to re-run: skips anything already installed.
Afterwards the load suite finds JMeter automatically (or set JMETER_HOME / JAVA_HOME yourself).
"""
import hashlib
import os
import platform
import shutil
import subprocess
import sys
import tarfile
import urllib.request
import zipfile
from pathlib import Path

JMETER_VERSION = "5.6.3"
TOOLS = Path(os.environ.get("BT_TOOLS_DIR", Path.home() / "tools"))
DL = TOOLS / "dl"
JMETER_URLS = [f"https://dlcdn.apache.org/jmeter/binaries/apache-jmeter-{JMETER_VERSION}.zip",
               f"https://archive.apache.org/dist/jmeter/binaries/apache-jmeter-{JMETER_VERSION}.zip"]


def download(urls, dest: Path):
    for u in ([urls] if isinstance(urls, str) else urls):
        try:
            print(f"  downloading {u}")
            req = urllib.request.Request(u, headers={"User-Agent": "bt-installer"})
            with urllib.request.urlopen(req, timeout=60) as r, open(dest, "wb") as f:
                shutil.copyfileobj(r, f, 1 << 20)
            return
        except Exception as e:
            print(f"  failed ({type(e).__name__}: {e}); trying next source")
    raise SystemExit(f"Could not download {dest.name}")


def java_ok() -> str:
    cands = []
    if os.environ.get("JAVA_HOME"):
        cands.append(Path(os.environ["JAVA_HOME"]) / "bin" / ("java.exe" if os.name == "nt" else "java"))
    w = shutil.which("java")
    if w:
        cands.append(Path(w))
    cands += sorted(TOOLS.glob("jre-*/*/bin/java*")) + sorted(TOOLS.glob("jdk-*/*/bin/java*"))
    for c in cands:
        if c.exists() and c.name.startswith("java"):
            try:
                out = subprocess.run([str(c), "-version"], capture_output=True, text=True, timeout=20).stderr
                if "version" in out:
                    return str(c.parent.parent)
            except Exception:
                pass
    return ""


def install_java() -> str:
    home = java_ok()
    if home:
        print(f"[1/2] Java found: {home}")
        return home
    print("[1/2] No Java found - installing Temurin JRE 17")
    osn = {"Windows": "windows", "Linux": "linux", "Darwin": "mac"}[platform.system()]
    arch = "aarch64" if platform.machine().lower() in ("arm64", "aarch64") else "x64"
    url = f"https://api.adoptium.net/v3/binary/latest/17/ga/{osn}/{arch}/jre/hotspot/normal/eclipse"
    DL.mkdir(parents=True, exist_ok=True)
    arc = DL / ("jre17.zip" if osn == "windows" else "jre17.tar.gz")
    if not arc.exists() or arc.stat().st_size < 10_000_000:
        download(url, arc)
    tmp = TOOLS / "jre-17"
    shutil.rmtree(tmp, ignore_errors=True)
    tmp.mkdir(parents=True)
    if arc.suffix == ".zip":
        zipfile.ZipFile(arc).extractall(tmp)
    else:
        tarfile.open(arc).extractall(tmp)
    root = next(p for p in tmp.iterdir() if p.is_dir())
    if osn == "mac" and (root / "Contents" / "Home").exists():
        root = root / "Contents" / "Home"
    print(f"  installed to {root}")
    return str(root)


def install_jmeter() -> Path:
    target = TOOLS / f"apache-jmeter-{JMETER_VERSION}"
    if (target / "bin").exists():
        print(f"[2/2] JMeter {JMETER_VERSION} already installed: {target}")
        return target
    print(f"[2/2] Installing JMeter {JMETER_VERSION}")
    DL.mkdir(parents=True, exist_ok=True)
    arc = DL / f"apache-jmeter-{JMETER_VERSION}.zip"
    sha_file = DL / (arc.name + ".sha512")
    sha_url = f"https://archive.apache.org/dist/jmeter/binaries/{arc.name}.sha512"
    download(sha_url, sha_file)
    expected = sha_file.read_text().split()[0].lower()

    def digest():
        h = hashlib.sha512()
        with open(arc, "rb") as f:
            for chunk in iter(lambda: f.read(1 << 20), b""):
                h.update(chunk)
        return h.hexdigest()

    if not arc.exists() or digest() != expected:
        download(JMETER_URLS, arc)
    if digest() != expected:
        raise SystemExit("Checksum mismatch - refusing to install a corrupt/tampered archive")
    print("  SHA-512 verified")
    zipfile.ZipFile(arc).extractall(TOOLS)
    if os.name != "nt":
        for f in (target / "bin").glob("*"):
            f.chmod(0o755)
    return target


def main() -> int:
    TOOLS.mkdir(parents=True, exist_ok=True)
    java_home = install_java()
    target = install_jmeter()
    exe = target / "bin" / ("jmeter.bat" if os.name == "nt" else "jmeter")
    # jmeter.bat launches `java` from PATH (it ignores JAVA_HOME), so put the JRE first on PATH.
    # stdin=DEVNULL stops the batch file's trailing `pause` from hanging; failure is detected from the output text.
    env = dict(os.environ, JAVA_HOME=java_home, PATH=str(Path(java_home) / "bin") + os.pathsep + os.environ.get("PATH", ""))
    out = subprocess.run([str(exe), "--version"], capture_output=True, text=True, env=env, timeout=120, stdin=subprocess.DEVNULL)
    text = out.stdout + out.stderr
    print("\n".join(text.strip().splitlines()[-6:]))
    if "Not able to find Java" in text or JMETER_VERSION not in text:
        print("JMeter did not start - check the Java installation above.")
        return 1
    print(f"\nOK. JMeter: {exe}\n    JAVA_HOME: {java_home}\nRun the load suite:  python test_suite/jmeter_real_runner.py --profile smoke")
    return 0


if __name__ == "__main__":
    sys.exit(main())
