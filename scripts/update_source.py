#!/usr/bin/env python3
import hashlib
import json
import os
import plistlib
import subprocess
import tempfile
import urllib.request
import zipfile
from pathlib import Path

UPSTREAM_REPO = "itzzace/ytkace"
RELEASE_API = f"https://api.github.com/repos/{UPSTREAM_REPO}/releases/latest"
SOURCE_URL = "https://raw.githubusercontent.com/Alunatix/ytkace-altstore-source/main/source.json"
REPO_URL = "https://github.com/Alunatix/ytkace-altstore-source"
ITUNES_LOOKUP = "https://itunes.apple.com/lookup?id=544007664&country=ca"
USER_AGENT = "Alunatix/ytkace-altstore-source"
SOURCE_PATH = Path("source.json")
STATE_PATH = Path(".state.json")

EXCLUDED_ENTITLEMENTS = {
    "application-identifier",
    "com.apple.developer.team-identifier",
    "com.app.developer.team-identifier",
}


def request(url: str):
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": USER_AGENT,
    }
    token = os.getenv("GITHUB_TOKEN")
    if token and "api.github.com" in url:
        headers["Authorization"] = f"Bearer {token}"
        headers["X-GitHub-Api-Version"] = "2022-11-28"
    return urllib.request.Request(url, headers=headers)


def get_json(url: str):
    with urllib.request.urlopen(request(url), timeout=60) as response:
        return json.load(response)


def download(url: str, destination: Path) -> str:
    digest = hashlib.sha256()
    with urllib.request.urlopen(request(url), timeout=120) as response, destination.open("wb") as out:
        while True:
            chunk = response.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
            out.write(chunk)
    return digest.hexdigest()


def parse_plist_bytes(data: bytes):
    xml_start = data.find(b"<?xml")
    xml_end = data.rfind(b"</plist>")
    if xml_start != -1 and xml_end != -1:
        return plistlib.loads(data[xml_start : xml_end + len(b"</plist>")])
    binary_start = data.find(b"bplist00")
    if binary_start != -1:
        try:
            return plistlib.loads(data[binary_start:])
        except Exception:
            pass
    return None


def codesign_entitlements(bundle: Path):
    proc = subprocess.run(
        ["codesign", "-d", "--entitlements", ":-", str(bundle)],
        capture_output=True,
        check=False,
    )
    parsed = parse_plist_bytes(proc.stdout + b"\n" + proc.stderr)
    if isinstance(parsed, dict):
        return parsed

    profile = bundle / "embedded.mobileprovision"
    if profile.exists():
        proc = subprocess.run(
            ["security", "cms", "-D", "-i", str(profile)],
            capture_output=True,
            check=False,
        )
        try:
            parsed = plistlib.loads(proc.stdout)
            entitlements = parsed.get("Entitlements", {})
            if isinstance(entitlements, dict):
                return entitlements
        except Exception:
            pass
    return {}


def bundle_paths(main_app: Path):
    bundles = [main_app]
    bundles.extend(sorted(p for p in main_app.rglob("*.appex") if p.is_dir()))
    bundles.extend(sorted(p for p in main_app.rglob("*.app") if p.is_dir() and p != main_app))
    return list(dict.fromkeys(bundles))


def collect_permissions(main_app: Path):
    entitlements = set()
    privacy = {}

    for bundle in bundle_paths(main_app):
        for key in codesign_entitlements(bundle):
            if key not in EXCLUDED_ENTITLEMENTS:
                entitlements.add(key)

        info_path = bundle / "Info.plist"
        if not info_path.exists():
            continue
        with info_path.open("rb") as f:
            info = plistlib.load(f)
        for key, value in info.items():
            if key.startswith("NS") and key.endswith("UsageDescription") and isinstance(value, str):
                privacy[key] = value

    return {
        "entitlements": sorted(entitlements),
        "privacy": dict(sorted(privacy.items())),
    }


def app_icon_url():
    try:
        data = get_json(ITUNES_LOOKUP)
        result = data["results"][0]
        return result.get("artworkUrl512") or result.get("artworkUrl100")
    except Exception:
        return "https://github.com/itzzace.png?size=512"


def main():
    release = get_json(RELEASE_API)
    if release.get("draft") or release.get("prerelease"):
        raise RuntimeError("Latest upstream release is not a stable published release.")

    ipa_assets = [
        asset
        for asset in release.get("assets", [])
        if asset.get("name", "").lower().endswith(".ipa")
    ]
    if len(ipa_assets) != 1:
        raise RuntimeError(f"Expected exactly one IPA asset, found {len(ipa_assets)}.")

    asset = ipa_assets[0]
    download_url = asset["browser_download_url"]
    expected_prefix = f"https://github.com/{UPSTREAM_REPO}/releases/download/"
    if not download_url.startswith(expected_prefix):
        raise RuntimeError(f"Refusing unexpected IPA URL: {download_url}")

    with tempfile.TemporaryDirectory() as tmp:
        tmpdir = Path(tmp)
        ipa_path = tmpdir / asset["name"]
        actual_sha256 = download(download_url, ipa_path)

        expected_digest = asset.get("digest")
        if expected_digest:
            algorithm, _, digest = expected_digest.partition(":")
            if algorithm.lower() != "sha256" or digest.lower() != actual_sha256:
                raise RuntimeError("Downloaded IPA SHA-256 does not match GitHub release metadata.")

        extract_dir = tmpdir / "extracted"
        with zipfile.ZipFile(ipa_path) as archive:
            archive.extractall(extract_dir)

        apps = list((extract_dir / "Payload").glob("*.app"))
        if len(apps) != 1:
            raise RuntimeError(f"Expected one top-level .app, found {len(apps)}.")
        app_dir = apps[0]

        with (app_dir / "Info.plist").open("rb") as f:
            info = plistlib.load(f)

        bundle_id = str(info["CFBundleIdentifier"])
        version = str(info["CFBundleShortVersionString"])
        build_version = str(info["CFBundleVersion"])
        min_os = str(info.get("MinimumOSVersion", "16.0"))
        permissions = collect_permissions(app_dir)

    tag = release["tag_name"]
    ytkace_version = tag[1:] if tag.startswith("v") else tag
    release_date = release["published_at"]
    release_notes = (release.get("body") or "").strip()
    version_description = (
        "Unmodified official upstream IPA from itzzace/ytkace."
        + (f"\n\n{release_notes}" if release_notes else "")
    )

    icon_url = app_icon_url()

    source = {
        "name": "YTKACE — official IPA",
        "subtitle": "A minimal AltStore source that points directly to YTKACE's upstream IPA.",
        "description": (
            "This source is maintained only as an AltStore index. "
            "It does not rebuild, inject, modify, or re-host YTKACE; every install "
            "downloads the IPA directly from the official itzzace/ytkace GitHub Release."
        ),
        "iconURL": icon_url,
        "website": REPO_URL,
        "tintColor": "#FF0000",
        "featuredApps": [bundle_id],
        "apps": [
            {
                "name": "YTKACE",
                "bundleIdentifier": bundle_id,
                "developerName": "itzzace0",
                "subtitle": "YouTube with YTKACE enhancements.",
                "localizedDescription": (
                    "YTKACE for iOS, distributed here without modification. "
                    "The IPA URL points directly to the official upstream GitHub Release."
                ),
                "iconURL": icon_url,
                "tintColor": "#FF0000",
                "category": "photo-video",
                "versions": [
                    {
                        "version": version,
                        "buildVersion": build_version,
                        "marketingVersion": f"YouTube {version} · YTKACE {ytkace_version}",
                        "date": release_date,
                        "localizedDescription": version_description,
                        "downloadURL": download_url,
                        "size": int(asset["size"]),
                        "sha256": actual_sha256,
                        "minOSVersion": min_os,
                    }
                ],
                "appPermissions": permissions,
            }
        ],
        "news": [],
    }

    SOURCE_PATH.write_text(json.dumps(source, ensure_ascii=False, indent=2) + "\n")
    STATE_PATH.write_text(
        json.dumps(
            {
                "upstreamRepo": UPSTREAM_REPO,
                "releaseId": release["id"],
                "releaseTag": tag,
                "assetId": asset["id"],
                "assetName": asset["name"],
                "sourceURL": SOURCE_URL,
            },
            indent=2,
        )
        + "\n"
    )

    print(
        f"Updated source for {tag}: {bundle_id} {version} ({build_version}), "
        f"{asset['size']} bytes, sha256={actual_sha256}"
    )
    print(
        f"Permissions: {len(permissions['entitlements'])} entitlements, "
        f"{len(permissions['privacy'])} privacy strings"
    )


if __name__ == "__main__":
    main()
