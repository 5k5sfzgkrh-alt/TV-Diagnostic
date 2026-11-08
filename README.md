# TV Diagnostic — Hi3751V553

Android TV diagnostic application for the SmartTV235X / Hi3751V553 platform.

This repository is being initialized with the v0.3.0 source and a GitHub Actions workflow to build a debug APK. The app is diagnostic-only: it reads system information and exports JSON; it does not disable services, modify system settings, or flash firmware.

See `BUILD_APK_FROM_IPHONE_RU.md` for build instructions. The APK is not yet built or tested on a physical TV.

## TV Diagnostic 2.1 safe package manager

The 2.1 development branch adds a package inventory screen, a per-package reversible state-change adapter, a one-package pre-change snapshot, and a restore action. The adapter is gated by a firmware-specific allowlist.

**Important:** the allowlist is deliberately empty in this commit. Therefore every disable control is visibly blocked; no package has been proven safe for CS2352P687 yet. The feature is scaffolding for controlled operation, not permission to disable any current candidate. ROOT authorization and physical rollback testing are still required. The existing read-only audit and QR report transfer remain in the source.

Build and physical-device validation are pending.
