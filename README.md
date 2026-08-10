# YTKACE AltStore Source

A tiny AltStore Classic source for [YTKACE](https://github.com/itzzace/ytkace).

The source does **not** rebuild, inject, modify, or re-host YTKACE. `source.json` points directly to the IPA attached to the official `itzzace/ytkace` GitHub Release.

## Add to AltStore

Use this source URL:

```text
https://raw.githubusercontent.com/Alunatix/ytkace-altstore-source/main/source.json
```

In AltStore Classic, open **Sources**, tap **+**, and paste the URL.

## How updates work

GitHub Actions checks the latest upstream YTKACE release every 6 hours. When a new release appears, it:

1. Downloads the IPA directly from `itzzace/ytkace`.
2. Verifies the IPA's SHA-256 against GitHub Release metadata when a digest is provided.
3. Reads the app version, build number, minimum iOS version, privacy strings, and signed entitlements from the IPA.
4. Regenerates `source.json` with the official upstream IPA URL and SHA-256.
5. Commits the updated source back to this repository.

The macOS runner is used so the workflow can inspect the IPA's code-signing entitlements with Apple's `codesign` tooling.

## Important limitation

AltStore determines whether an update exists from the IPA's `CFBundleShortVersionString` and `CFBundleVersion`. If YTKACE publishes a tweak-only release while keeping the exact same underlying YouTube version and build number, AltStore may not automatically flag it as an update. Fixing that would require modifying/repacking the IPA, which this source intentionally does not do.

## Trust model

The install path is:

`AltStore → this source.json → official itzzace/ytkace GitHub Release IPA`

This repository only supplies metadata. The IPA itself is never mirrored here.

Not affiliated with Google, YouTube, AltStore, or the YTKACE project.
