# TV Diagnostic 2.1 — Safe, reversible component control

Status: implementation specification; no device-side changes are performed by this repository change.

Target: CS2352P687 / HiSilicon Hi3751V553 / Android 14 (API 34).

## Non-negotiable safety model

1. Default mode is READ-ONLY. Scanning never changes package/component state.
2. No automatic disable operation, no boot-time automation, no batch disable, no removal/uninstall, no writes to system/vendor/boot/recovery/vbmeta/DTB/DTBO or partition tables.
3. The app must never disable vendor HALs, init services, system_server services, framework packages, SystemUI, Settings, launcher/home, input method, package installer, permission controller, media/audio/display/DTV, DRM/HDCP, Wi-Fi/Bluetooth, storage, update/recovery, or security components.
4. A package is not "safe" because it is large, unused-looking, or has no obvious launcher activity.
5. Only an explicit, evidence-backed allowlist may expose an Enable/Disable control. Unknown or incomplete dependency data means BLOCKED, not "probably safe".
6. Every state-changing action requires a per-item confirmation showing package/component, evidence, risks, current state, and exact rollback action.
7. Before a change, save a timestamped JSON snapshot of package enabled states and app-op state where readable. Never claim this is a full system backup.
8. Apply one component at a time. Verify the resulting state. If verification fails, immediately attempt rollback and report both outcomes.
9. Provide a persistent "Restore previous state" screen using the saved snapshot. Rollback must be available without network access.
10. Never use broad shell strings or interpolate untrusted package names. Validate identifiers and invoke fixed commands with argument separation.

## Classification

- GREEN / ELIGIBLE: all required static and runtime evidence exists, package is explicitly reviewed for this exact firmware fingerprint, no protected role or dependency edge is found, and rollback is supported.
- AMBER / REVIEW: optional-looking but dependency or runtime evidence is incomplete. No action control.
- RED / PROTECTED: critical, vendor, framework, boot, security, connectivity, TV, media, display, input, storage, update, or recovery role. No action control.
- GRAY / UNKNOWN: not enough evidence. No action control.

GREEN is firmware-specific. It must be keyed to the complete build fingerprint, board/platform, Android SDK, and vendor build identifiers. A change of fingerprint invalidates the allowlist.

## Evidence required before GREEN

- Decoded manifest: package name, sharedUserId/shared UID, requested and privileged permissions, exported components, services, receivers, providers, intent filters, foreground-service types.
- Package metadata: system/privileged/product/vendor location, signing certificate digest, shared libraries, enabled state, install/update source.
- Cross references: overlays, sysconfig, privapp-permissions, default-permissions, permissions XML, init RC, VINTF manifest/matrix, SELinux policy, framework resources, role holders, device config and vendor configuration.
- Runtime evidence: observed processes/services and package usage over a representative period, while noting that absence during observation does not prove non-use.
- Functional dependency review: TV boot/home, remote/input, DTV, HDMI, audio, video/DRM, Wi-Fi, Bluetooth, updates, settings, sleep/wake and factory reset.
- Human review of the evidence and a device-specific test plan.

## Execution policy

- First release may implement inventory, dependency graph, classification, snapshots, and rollback UI.
- The actual disable adapter must remain feature-gated until the allowlist and rollback path have been validated on the exact CS2352P687 firmware.
- Prefer disabling an individual non-critical app component over disabling an entire package. If component-level state cannot be safely restored, do not expose the operation.
- Where elevated privileges are required, use a narrow fixed-command adapter; explain root requirement and show the exact operation before confirmation.
- Do not request root during passive scanning. Never execute commands against block devices.

## Initial protected groups for this device

All vendor packages and all vendor HAL/init integrations; DolphinOS launcher and TV shell; DTV, tuner, media, audio, display, graphics, DRM/HDCP; Wi-Fi/Bluetooth stacks and drivers; SystemUI, Settings, framework, package/permission manager, input/remote services, storage, update and recovery.

## Current candidate queue

Chrome, Tubesky, HkGuide, MovieArk, DolphinWebWindow, DolphinTVStore, HkMusic, HkHotelMenu, HkGalleryL and HkCleanMaster remain AMBER/GRAY pending exact APK manifest, certificate, cross-reference and runtime analysis. No package is approved for disabling by this document.

## Acceptance tests

- Read-only scan produces identical package state before and after.
- Protected/unknown packages never show an active disable control.
- Stale or mismatched fingerprint disables all GREEN actions.
- Each action requires individual confirmation and creates a snapshot first.
- One-item operation only; no bulk action.
- Successful disable is verified by querying actual package/component state.
- Failed operation triggers rollback attempt and explicit result.
- Restore can re-enable exactly the previously enabled items without network access.
- App crash/reboot between action and confirmation does not lose the snapshot.
- QR/Wi-Fi export, if present, exports reports only and never exposes control endpoints.

## Current verified repository limitation

The inspected 2.0 branch manifest and README establish a basic diagnostic-only app. They do not establish that ROOT auditing, QR transfer, APK dependency analysis, or reversible disable functionality is implemented. These capabilities must be verified in source and on physical hardware before being described as available.
