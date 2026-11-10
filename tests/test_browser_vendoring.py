"""Offline safety checks for the reproducible browser-asset updater."""

import base64
import hashlib
import importlib.util
import io
import json
import sys
import tarfile
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "vendor_browser_dependencies.py"
SPEC = importlib.util.spec_from_file_location("browser_vendoring", SCRIPT)
vendor = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(vendor)


@pytest.fixture
def package_archive(monkeypatch):
    payload = b"window.synthetic = true;\n"
    archive_bytes = io.BytesIO()
    with tarfile.open(fileobj=archive_bytes, mode="w:gz") as archive:
        for name, data in [("package/dist/index.js", payload), ("package/LICENSE", b"MIT")]:
            member = tarfile.TarInfo(name)
            member.size = len(data)
            archive.addfile(member, io.BytesIO(data))
    data = archive_bytes.getvalue()
    monkeypatch.setattr(vendor, "download", lambda url: data)
    return {
        "name": "synthetic", "version": "1.0.0", "license": "MIT",
        "tarball": "https://example.invalid/synthetic.tgz",
        "integrity": "sha512-" + base64.b64encode(hashlib.sha512(data).digest()).decode(),
        "member": "package/dist/index.js",
        "payload_sha256": hashlib.sha256(payload).hexdigest(),
    }, payload


def test_verified_archive_preserves_payload_and_license(package_archive):
    package, payload = package_archive
    asset, licenses = vendor.package_contents(package)
    assert asset == vendor.banner(package) + payload
    assert licenses == {"package/LICENSE": b"MIT"}


@pytest.mark.parametrize("field, message", [
    ("integrity", "Archive integrity mismatch"),
    ("payload_sha256", "Asset digest mismatch"),
])
def test_tampered_archive_or_payload_is_rejected(package_archive, field, message):
    package, _ = package_archive
    package[field] = "invalid"
    with pytest.raises(ValueError, match=message):
        vendor.package_contents(package)


def test_license_digest_mismatch_is_rejected(monkeypatch):
    monkeypatch.setattr(vendor, "download", lambda url: b"changed license")
    notice = {"title": "synthetic", "url": "https://example.invalid/LICENSE", "sha256": "invalid"}
    with pytest.raises(ValueError, match="License digest mismatch"):
        vendor.notice_text(notice, {})


def test_non_https_source_is_rejected():
    with pytest.raises(ValueError, match="must use HTTPS"):
        vendor.download("http://example.invalid/package.tgz")


def test_oversized_download_is_rejected(monkeypatch):
    monkeypatch.setattr(vendor, "MAX_DOWNLOAD_BYTES", 3)
    monkeypatch.setattr(vendor, "urlopen", lambda *args, **kwargs: io.BytesIO(b"1234"))
    with pytest.raises(ValueError, match="exceeds size limit"):
        vendor.download("https://example.invalid/package.tgz")


def test_check_reports_drift_without_overwriting_files(tmp_path, monkeypatch):
    (tmp_path / "vendor-manifest.json").write_text(json.dumps({}))
    asset = tmp_path / "synthetic.js"
    asset.write_bytes(b"local modification")
    monkeypatch.setattr(vendor, "LIB_DIR", tmp_path)
    monkeypatch.setattr(vendor, "expected_files", lambda manifest: {"synthetic.js": b"upstream"})
    monkeypatch.setattr(sys, "argv", [str(SCRIPT), "--check"])
    with pytest.raises(SystemExit, match="differs from pinned source"):
        vendor.main()
    assert asset.read_bytes() == b"local modification"


def test_all_sources_are_verified_before_replacing_any_asset(tmp_path, monkeypatch):
    (tmp_path / "vendor-manifest.json").write_text(json.dumps({}))
    asset = tmp_path / "synthetic.js"
    asset.write_bytes(b"original")

    def fail_verification(manifest):
        raise ValueError("Archive integrity mismatch")

    monkeypatch.setattr(vendor, "LIB_DIR", tmp_path)
    monkeypatch.setattr(vendor, "expected_files", fail_verification)
    monkeypatch.setattr(sys, "argv", [str(SCRIPT)])
    with pytest.raises(ValueError, match="Archive integrity mismatch"):
        vendor.main()
    assert asset.read_bytes() == b"original"
