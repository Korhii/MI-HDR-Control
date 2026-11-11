# Safety notice and disclaimer

[中文](SAFETY.zh-CN.md) · [User guide](guide.en.md)

## Project status

This personal experiment was developed, debugged and documented with AI tools and is shared with interested enthusiasts. AI-generated code and explanations may contain errors; the recorded checks define the tested scope. The author is not a professional developer; bugs and compatibility problems are expected. It is supplied as-is, without a commitment to maintenance, fixes, updates, adaptation or requests.

## Recorded scope

The author's unit is a **REDMI Monitor G Pro 32U 2026**, primarily observed manually in **HDR Game, HGiG, High local dimming, backlight 100**. Environment: HyperOS **OS3.0.120.0.UFFMAMN**, Android 14, kernel `5.15.148-android14-11-g37010446f523`; Windows 11 Pro for Workstations 25H2 (26200.8037), RTX 5090 D, 3840×2160 and monitor-reported 160 Hz. [Validation](VALIDATION.en.md) records build-specific checks.

**27U 2026 is estimated, without 27-inch hardware acceptance; numerous bugs are possible. Other monitors are unsupported.** System, driver, firmware or cloud-policy updates may invalidate the tool.

## Before use

- Parameter current, temperature, lifetime and extreme-combination safety have not been tested. Aggressive settings may increase load and heat; complete LED-board/driver ratings are unavailable. Immediate or accumulated damage is possible. Protection effectiveness has not been fully verified.
- Incorrect parameters, kernel adaptation or firmware mismatch can cause black screens, crashes, reboot loops or failure to boot (bricking). ADB and software restoration may then be unavailable, requiring repair or other recovery methods.
- Preserve the initial backup. After ending temporary tuning, use **退出控制器** at the top right and wait for normal exit. Do not terminate the process; that can bypass saving and restoration. A permanently saved scheme requires separate removal and is not canceled by closing the PC.
- Raw values, budgets, model nits and sensor labels do not establish electrical current, backlight-board temperature or long-term safety. The historical 41/86 short-test boundary is not a certified safe setting.
- Warranty treatment has not been confirmed by the manufacturer. Coverage for resulting faults cannot be guaranteed.

Users choose whether to run, tune and install persistence, and bear the corresponding risks. No performance or safety warranty is provided. Liability for resulting loss is excluded to the extent permitted by applicable law.
