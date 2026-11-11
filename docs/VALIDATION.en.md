# Validation · 0.9.26 dimming-only experimental preview

[简体中文](VALIDATION.zh-CN.md) · [Release method](RELEASING.en.md)

The source is the complete personal **0.9.26** package, left unchanged. The public copy retains current dimming functions and excludes launcher/system-menu modifications and personal runtime data. The author has authorized this experimental-preview GitHub publication.

## Observed in this build

| Check | Result and scope |
| :--- | :--- |
| Current Python regression | **152 passed**, including 10 ADB simulation cases. Model tests used legally obtained owner-local firmware fixtures. The suite rejects any unmocked ADB subprocess. |
| JavaScript coupling | **9 passed**: click-time budget/ABL snapshots, profile changes, later drafts, invalidated/late forecasts, off-state priority, retained time spacing and offline file import. |
| Native build and lifecycle | Rebuilt public 0.9.26 EXE; observed portrait-A4 default layout. Normal close removed the native window and stopped its backend, while offline. |
| Public/documentation contracts | **13 public checks and 9 documentation checks passed** in the freshly exported portable directory. |
| Java bridge and GPU | **33 JVM bridge/receipt/provider checks passed**; all **10 hidden-window D3D11 pattern-readback cases** reported wrong_pixels=0, without visible high-brightness test windows or device writes. |
| APP captures | **21** dark-MONO tutorial PNGs remain 1000×1414. **6** real ADB-connected APL/ABL page-top themes use an 885×1454 viewport, 100% UI and native 2× PNGs (1770×2908). Connection addresses and the existing sensor-path privacy rectangle are masked; outside pixels are unchanged. |
| Palette revision | All six now show the APL/ABL page top at the supplied reference proportions. ADB was genuinely connected, live debugging stayed off, no tuning was applied and UI state was not rewritten. |
| Local preparation | Re-prepared budget/model components from 25 existing owner inputs; ready, with no device write. Derived OEM KO/ELF/firmware backups are not distributed. |
| Packaging | The release tool checks scope, licenses, links, defaults and provenance. Actual ZIP, extraction/startup, documentation, patch reconstruction and rollback commands are retained in the external verification record. |

### UI and cache revision

- A startup dialog groups concise risks, backup and normal-exit instructions. Completion notices have one acknowledgement; actual choices retain Cancel.
- Removed redundant manual Save while preserving autosave. The native EXE opened Windows Save As and exported parseable JSON outside the portable directory, including Chinese characters and spaces. Cancel produced no file or error dialog.
- Both automatic and budget charts hid node details immediately after moving off a node while still inside the chart.
- Enabled ABL greys the complete fitting area and disables curve editing. An imported ABL profile with no fit result exposed a missed redraw; it was reproduced, covered and corrected. New UI checks **9/9**; earlier coupling checks **9/9**.
- Cold cache **35.05 → 4.59 s**, approximately **7.63×**; warm reading about **0.36 ms**. Ryzen 9 9950X / 16 cores32 threads / 16 workers; 32U, High, HGiG, 4000-nit PQ, all 729 combinations and 98,415 floats byte-identical. Four additional sampled contexts also matched output and factory-call counts.
- This revision used PC-only checks, without connecting, writing or rebooting a monitor. It adds no hardware-safety or cross-device acceptance.

### Product issues reproduced and corrected

- **Later edits leaking into Apply:** budget, ABL and profile are captured on click. A changed profile rejects the queued submission; newer drafts survive an older completion.
- **Old ABL charts appearing under new parameters:** a new snapshot immediately invalidates the previous chart, late generations are ignored, and off state takes precedence over asset readiness.
- **Offline JSON import blocked as a device edit:** the input guard now permits PC file selection while retaining ADB gates on display parameters. The focused check changed from 8/9 to 9/9; actual UI import was rechecked.
- **ADB portability:** corrupt/empty caches recover, unspecified endpoints are rejected, USB/Wi-Fi identities deduplicate, multiple displays no longer select the first silently, and the known-neighbour limit increased from 32 to 256.

The pristine 0.9.26 legacy Python suite produced **128 tests, 13 failures, 48 errors, exit 1**. Stale fixtures were updated for model confirmation/backup preconditions, removed APIs, session fit tokens, 13 target knots, AW and actual ABL gain semantics. Production gates were not removed to satisfy tests. Explicit rejection tests now cover unconfirmed models, unverified ADB panels, incomplete backups and stale model windows. Original failure logs remain external; they do not establish 61 independent product defects.

## ADB scope

Simulations cover foreign USB serials, different private IPv4 ranges, multiple-interface/long neighbour tables, dynamic mDNS connect ports, pairing-port exclusion, unauthorized states, unrelated phones, USB+network deduplication, multiple-display ambiguity and corrupt caches.

**No second physical display or LAN was available.** The user selected analytical and simulated checks. IPv6-only networks, isolation, blocked advertisements, absent neighbour records and unadvertised custom ports are not guaranteed to auto-discover. Manual `HOST:PORT` remains available without bypassing RSA. [Connection guide](guide.en.md#adb)

## Figures and algorithm evidence

Alpha notes now explain Mean, Max, bins, stored parameter values, mixed requests, raw scales, MCU model buffers, global APP AW and optical nits. The equal-10%-white example retains its original data: 32 α4 cells, 96 α7 cells and 1024 black cells; all 1152 distributed-point cells change from 17408 to 65280 for Alpha0=3→16. That is not an emitted-brightness multiplier.

SF/Alpha and static-budget figures retain their original data. Response caching now distributes the same sampling loop across isolated processes. All 729 combinations and samples from four additional model/tone/level contexts were byte-identical; source fingerprints and equivalence evidence were updated. Research data remains labeled offline/historical. Current 0.9.26 ABL retains cycle ranges and unresolved outcomes. The waterfall retains transparent time slices, adaptive draw spacing and XY/ZY projections. Current GUI captures add no photometer, electrical or thermal measurements.

Four genuine monitor-menu images are retained from the earlier same-firmware session: Control → Settings → Account & security → ADB debugging, plus About. Only cropping/privacy masking was used. Factory-fresh activation, the initial RSA prompt and physical chassis-button positions were not re-enacted.

## Existing physical evidence and limits

Unchanged bridge, adapter, device-helper and generation objects retain component-scoped historical evidence: short 32U read/write checks, eight level/tone operations, parameter restoration and one observed local-boot start after about 337.49 seconds. A later cleaned-build reboot lost ADB; reconnect read budget=20, then another controller took over. An uninterrupted interference-free sustained reboot check remains incomplete.

Consequently **`boot_verified=false`** remains, and permanent save retains experimental confirmation. Historical cleanup checked 36 original directory files and 11 parameters, with the local scheme disabled, budget module unloaded and SELinux Enforcing. This round did not reboot/write the display for screenshots or overwrite those historical conclusions.

Reference hardware: **REDMI Monitor G Pro 32U 2026**, active panel PTBCN1L; HyperOS **OS3.0.120.0.UFFMAMN**, Android 14, kernel `5.15.148-android14-11-g37010446f523`. Manual observations mainly used High local dimming, HGiG and backlight 100, 3840×2160 and device-reported 160 Hz. PC: Windows 11 Pro for Workstations 25H2 (26200.8037), RTX 5090 D, driver 32.0.16.2114.

There are no traceable ambient/backlight-board temperature, current, illuminance or instrument-calibration records. No 27-inch hardware acceptance, long-term/extreme-setting safety, full power-loss recovery or professional EOTF measurement was completed. 27U remains inferred; firmware changes require revalidation. Maintenance or fixes are not promised.

## Publication state

Program: GPL-2.0-only. Original documentation/figures and independent materials: CC BY-NC-SA 4.0. Third-party terms remain unchanged. Licensing, credit, languages and palettes are confirmed. Exports default to `publication_authorized=false` and `release_ready=false`. This publication has explicit owner authorization, recorded through a manual approval step with repository and tag. `release_ready=true` means publishable as an experimental preview, not hardware-safety certification.

## GitHub publication supplement

The paired disclaimers, READMEs and startup notice now disclose AI-assisted creation. Only curated source, documentation and the portable bundle are published. GitHub checks cover public files, documentation and JavaScript coupling; they never connect a monitor or automatically release new versions. Hardware, 27-inch and persistence limitations are unchanged.

## Connected themes, portable relocation and feedback

This update changes the homepage, documentation, gallery and feedback entry points only; the published 0.9.26 ZIP and tag remain unchanged. Issues, Discussions and PRs are open without promised replies, updates, fixes or merges. Following real read-only ADB capture, the package was moved to a Unicode/space path and launched from an outside directory. Actual reconnection reused one identical backup, retained valid prepared caches and unchanged native dimming readback, then exited normally with status 0. Existing package-root path behavior required no runtime change.

The current GitHub download is marked Latest while the title remains Experimental preview. This metadata adjustment did not change the version tag, portable ZIP or checksum asset.
