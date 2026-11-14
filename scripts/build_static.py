#!/usr/bin/env python3
"""Build the static Unique Pro site and prepare same-origin offline Vosk assets.

The model is deliberately downloaded at deploy time, not committed to Git.
No runtime API/server is introduced; the deployed files are static assets.
"""
from __future__ import annotations
import hashlib, json, os, re, shutil, subprocess, tarfile, tempfile, urllib.request, zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "dist"
VOSK_VERSION = "0.0.5"
MODEL_NAME = "vosk-model-small-fa-0.42"
NPM_URL = f"https://registry.npmjs.org/vosk-browser/-/vosk-browser-{VOSK_VERSION}.tgz"
MODEL_URL = os.environ.get("VOSK_MODEL_URL", f"https://alphacephei.com/vosk/models/{MODEL_NAME}.zip")

def download(url: str, target: Path) -> str:
    request = urllib.request.Request(url, headers={"User-Agent": "Unique-Pro-static-build/1.0"})
    digest = hashlib.sha256()
    with urllib.request.urlopen(request, timeout=180) as response, target.open("wb") as out:
        while True:
            chunk = response.read(1024 * 1024)
            if not chunk:
                break
            out.write(chunk)
            digest.update(chunk)
    return digest.hexdigest()

def safe_extract_zip(archive: Path, destination: Path) -> None:
    root = destination.resolve()
    with zipfile.ZipFile(archive) as zf:
        for item in zf.infolist():
            target = (destination / item.filename).resolve()
            if target != root and root not in target.parents:
                raise RuntimeError(f"Unsafe path in model archive: {item.filename}")
        zf.extractall(destination)

def main() -> None:
    if DIST.exists():
        shutil.rmtree(DIST)
    ignored = shutil.ignore_patterns(".git", ".github", ".vercel", "dist", "tests", "scripts", "__pycache__", "*.pyc")
    shutil.copytree(ROOT, DIST, ignore=ignored)

    asset_dir = DIST / "vendor" / "vosk"
    asset_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="unique-vosk-") as tmp:
        temp = Path(tmp)
        npm_archive = temp / "vosk-browser.tgz"
        npm_sha = download(NPM_URL, npm_archive)
        with tarfile.open(npm_archive, "r:gz") as package:
            members = [m for m in package.getmembers() if m.isfile() and m.name.startswith("package/dist/")]
            if not members:
                raise RuntimeError("vosk-browser package has no package/dist assets")
            for member in members:
                relative = Path(member.name).relative_to("package/dist")
                if ".." in relative.parts:
                    raise RuntimeError("Unsafe path in vosk-browser package")
                target = asset_dir / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                source = package.extractfile(member)
                if source is None:
                    raise RuntimeError(f"Cannot read {member.name}")
                with source, target.open("wb") as out:
                    shutil.copyfileobj(source, out)
            for license_path in ("package/LICENSE", "package/NOTICE"):
                try:
                    member = package.getmember(license_path)
                except KeyError:
                    continue
                source = package.extractfile(member)
                if source:
                    with source, (asset_dir / Path(license_path).name).open("wb") as out:
                        shutil.copyfileobj(source, out)
        if not (asset_dir / "vosk.js").is_file():
            raise RuntimeError("vosk-browser dist/vosk.js is missing")

        model_archive = temp / (MODEL_NAME + ".zip")
        model_sha = download(MODEL_URL, model_archive)
        extracted = temp / "model-extracted"
        extracted.mkdir()
        safe_extract_zip(model_archive, extracted)
        candidates = [p for p in extracted.iterdir() if p.is_dir()]
        model_dir = next((p for p in candidates if p.name == MODEL_NAME), None)
        if model_dir is None and len(candidates) == 1:
            model_dir = candidates[0]
        if model_dir is None:
            raise RuntimeError("Persian Vosk model folder was not found in the official ZIP")
        required = ["am/final.mdl", "conf/mfcc.conf"]
        for rel in required:
            if not (model_dir / rel).is_file():
                raise RuntimeError(f"Persian model is incomplete: {rel} is missing")
        graph = model_dir / "graph"
        if not any((graph / name).is_file() for name in ("HCLG.fst", "Gr.fst")):
            raise RuntimeError("Persian model graph is missing (HCLG.fst / Gr.fst)")
        conf = model_dir / "conf" / "model.conf"
        if not conf.exists():
            conf.write_text("--beam=13.0\n--max-active=7000\n--lattice-beam=6.0\n", encoding="utf-8")
        with tarfile.open(asset_dir / "model.tar.gz", "w:gz", compresslevel=6) as package:
            package.add(model_dir, arcname="model")

    (asset_dir / "MODEL-SOURCE.txt").write_text(
        "Persian acoustic model: " + MODEL_NAME + "\n"
        "Source: https://alphacephei.com/vosk/models\n"
        "License: Apache License 2.0. License text: https://www.apache.org/licenses/LICENSE-2.0.txt\n",
        encoding="utf-8"
    )
    for js_file in ("src/ui/offline-voice.js", "src/ui/upgrade.js", "src/ui/local-nlu.js"):
        subprocess.run(["node", "--check", str(DIST / js_file)], check=True)
    # The main app contains substantial inline JavaScript; validate it too,
    # not only the separately maintained modules.
    html = (DIST / "index.html").read_text(encoding="utf-8")
    with tempfile.TemporaryDirectory(prefix="unique-inline-js-") as check_dir:
        cursor = 0
        number = 0
        while True:
            opening = re.search(r"<script\b([^>]*)>", html[cursor:], re.I)
            if not opening:
                break
            attrs = opening.group(1)
            body_start = cursor + opening.end()
            closing = re.search(r"</script\s*>", html[body_start:], re.I)
            if not closing:
                raise RuntimeError("Unclosed script element in index.html")
            code = html[body_start:body_start + closing.start()]
            cursor = body_start + closing.end()
            current = number
            number += 1
            if re.search(r"\bsrc\s*=", attrs, re.I):
                continue
            type_match = re.search(r"""\btype\s*=\s*["']([^"']+)["']""", attrs, re.I)
            script_type = type_match.group(1).lower() if type_match else ""
            if script_type and "javascript" not in script_type and "ecmascript" not in script_type and script_type != "module":
                continue
            if not code.strip():
                continue
            check_file = Path(check_dir) / f"inline-{current}.js"
            check_file.write_text(code, encoding="utf-8")
            subprocess.run(["node", "--check", str(check_file)], check=True)

    manifest = {
        "voskBrowserVersion": VOSK_VERSION,
        "voskBrowserTarballSha256": npm_sha,
        "model": MODEL_NAME,
        "modelSource": MODEL_URL,
        "modelZipSha256": model_sha,
        "modelArchive": "vendor/vosk/model.tar.gz",
        "generatedAtBuild": True
    }
    (asset_dir / "build-manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Unique static output ready: {DIST}")
    print(f"Vosk assets: {asset_dir}")

if __name__ == "__main__":
    main()
