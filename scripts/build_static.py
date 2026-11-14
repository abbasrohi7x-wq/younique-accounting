#!/usr/bin/env python3
"""Build the static Unique Pro site and prepare same-origin offline Vosk assets.

The model is deliberately downloaded at deploy time, not committed to Git.
No runtime API/server is introduced; the deployed files are static assets.
"""
from __future__ import annotations
import gzip, hashlib, json, os, re, shutil, subprocess, tarfile, tempfile, urllib.request, zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "dist"
VOSK_VERSION = "0.0.8"
VOSK_SOURCE_COMMIT = "4b8eb257503108d96819854d3984372903c2259e"
VOSK_SOURCE_URL = f"https://codeload.github.com/ccoreilly/vosk-browser/tar.gz/{VOSK_SOURCE_COMMIT}"
MODEL_NAME = "vosk-model-small-fa-0.42"
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

def verify_tesseract_assets(asset_root: Path) -> None:
    """Fail the build early if the offline Persian/English OCR bundle is incomplete."""
    required_js = (
        "tesseract.min.js",
        "worker.min.js",
        "core/tesseract-core-simd-lstm.wasm.js",
        "core/tesseract-core-lstm.wasm.js",
    )
    for relative in required_js:
        path = asset_root / relative
        if not path.is_file() or path.stat().st_size == 0:
            raise RuntimeError(f"Offline Tesseract asset is missing or empty: {path.relative_to(DIST)}")

    for language in ("fas", "eng"):
        path = asset_root / "lang" / f"{language}.traineddata.gz"
        if not path.is_file() or path.stat().st_size < 1024:
            raise RuntimeError(f"Tesseract {language} traineddata is missing or suspiciously small")
        try:
            expanded = 0
            with gzip.open(path, "rb") as model:
                while True:
                    chunk = model.read(1024 * 1024)
                    if not chunk:
                        break
                    expanded += len(chunk)
            if expanded < 1024:
                raise RuntimeError(f"Tesseract {language} traineddata is empty or truncated")
        except (OSError, EOFError) as error:
            raise RuntimeError(f"Tesseract {language} traineddata is not a valid gzip archive: {error}") from error

def safe_extract_zip(archive: Path, destination: Path) -> None:
    root = destination.resolve()
    with zipfile.ZipFile(archive) as zf:
        for item in zf.infolist():
            target = (destination / item.filename).resolve()
            if target != root and root not in target.parents:
                raise RuntimeError(f"Unsafe path in model archive: {item.filename}")
        zf.extractall(destination)

def extract_vosk_source(archive: Path, lib_dir: Path, asset_dir: Path) -> None:
    """Extract only the pinned Vosk lib source and its licenses; reject links and traversal."""
    with tarfile.open(archive, "r:gz") as package:
        members = package.getmembers()
        package_json = next((m for m in members if m.isfile() and m.name.endswith("/lib/package.json")), None)
        if package_json is None:
            raise RuntimeError("Pinned Vosk source archive has no lib/package.json")
        prefix = package_json.name[:-len("lib/package.json")]
        root = lib_dir.resolve()
        for member in members:
            marker = prefix + "lib/"
            if not member.name.startswith(marker):
                continue
            relative = Path(member.name[len(marker):])
            if not relative.parts:
                continue
            if ".." in relative.parts:
                raise RuntimeError(f"Unsafe path in Vosk source archive: {member.name}")
            target = (lib_dir / relative).resolve()
            if target != root and root not in target.parents:
                raise RuntimeError(f"Unsafe path in Vosk source archive: {member.name}")
            if member.isdir():
                target.mkdir(parents=True, exist_ok=True)
            elif member.isfile():
                target.parent.mkdir(parents=True, exist_ok=True)
                source = package.extractfile(member)
                if source is None:
                    raise RuntimeError(f"Cannot read Vosk source file: {member.name}")
                with source, target.open("wb") as out:
                    shutil.copyfileobj(source, out)
            else:
                raise RuntimeError(f"Unsupported link or special file in Vosk source: {member.name}")
        for license_name in ("LICENSE", "NOTICE"):
            member = next((m for m in members if m.isfile() and m.name == prefix + license_name), None)
            if member is not None:
                source = package.extractfile(member)
                if source:
                    with source, (asset_dir / license_name).open("wb") as out:
                        shutil.copyfileobj(source, out)

def main() -> None:
    if DIST.exists():
        shutil.rmtree(DIST)
    ignored = shutil.ignore_patterns(".git", ".github", ".vercel", "dist", "tests", "scripts", "__pycache__", "*.pyc")
    shutil.copytree(ROOT, DIST, ignore=ignored)

    verify_tesseract_assets(DIST / "vendor" / "tesseract")

    asset_dir = DIST / "vendor" / "vosk"
    asset_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="unique-vosk-") as tmp:
        temp = Path(tmp)
        source_archive = temp / "vosk-browser-source.tgz"
        source_sha = download(VOSK_SOURCE_URL, source_archive)
        lib_dir = temp / "vosk-browser-lib"
        lib_dir.mkdir()
        extract_vosk_source(source_archive, lib_dir, asset_dir)
        rollup_config = lib_dir / "rollup.config.js"
        config_text = rollup_config.read_text(encoding="utf-8")
        config_text, patched = re.subn(
            r"webWorkerLoader\(\{\s*forceInline:\s*true,\s*targetPlatform:\s*'browser'\s*\}\)",
            "webWorkerLoader({ inline: false, forceInline: false, targetPlatform: 'browser', loadPath: './vendor/vosk/' })",
            config_text,
            count=1
        )
        if patched != 1:
            raise RuntimeError("Pinned Vosk Rollup worker configuration changed unexpectedly")
        rollup_config.write_text(config_text, encoding="utf-8")
        subprocess.run(["npm", "ci", "--no-audit", "--no-fund"], cwd=lib_dir, check=True)
        dist_dir = lib_dir / "dist"
        if dist_dir.exists():
            shutil.rmtree(dist_dir)
        subprocess.run(["npm", "run", "build"], cwd=lib_dir, check=True)
        worker_files = sorted(p for p in dist_dir.glob("*worker*.js") if p.is_file())
        if not (dist_dir / "vosk.js").is_file():
            raise RuntimeError("Rebuilt Vosk dist/vosk.js is missing")
        if not worker_files:
            raise RuntimeError("Rebuilt Vosk external worker asset is missing")
        for source in dist_dir.rglob("*"):
            if source.is_file():
                target = asset_dir / source.relative_to(dist_dir)
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, target)

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
        "voskBrowserSourceCommit": VOSK_SOURCE_COMMIT,
        "voskBrowserSourceArchiveSha256": source_sha,
        "voskWorkerMode": "external-same-origin",
        "voskWorkerAssets": [p.name for p in worker_files],
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
