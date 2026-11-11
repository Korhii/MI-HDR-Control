# Licensing, credit and third-party components

[简体中文](LEGAL.zh-CN.md) · [LICENSE](../LICENSE) · [NOTICE](../NOTICE.md)

## Code and materials have separate licenses

Credit: **MI HDR Control contributors**.

| Content | License and scope |
| :--- | :--- |
| Original project software, functional UI code and corresponding compiled components | **GPL-2.0-only**. Includes Python, Java, C/C++/ASM, JavaScript, HTML/CSS and build scripts. Files identifying upstream authors or other terms retain them. |
| Original prose, diagrams, research figures and separately authored artwork | **CC BY-NC-SA 4.0**: attribution, noncommercial use, share-alike, license retention and change notices. |
| Fonts, dependencies and third-party content in instructional screenshots | Their own terms/ownership, without an added project commercial-use ban. |

GPL code permits commercial use under its source, attribution and distribution requirements. Including original noncommercial materials in a complete package does not grant commercial rights to those materials. Commercial use of those materials needs separate permission. Functional CSS/HTML remains GPL code rather than being restricted by an artwork license. [Full GPL terms](../LICENSES/GPL-2.0-only.txt) · [Full CC terms](../LICENSES/CC-BY-NC-SA-4.0.txt)

This retains the current bridge, budget and offline model without replacing Unicorn. The first release is an **experimental preview**, with a Chinese application UI and bilingual README/guides.

## Third-party handling

| Component | Handling |
| :--- | :--- |
| Java bridge | Independent implementation and readable source; the old unlicensed helper JAR is excluded. |
| Vendor KO, extracted ELF/instructions, full XML/INI/gamma | Excluded from repository/ZIP; read from each user's device and prepared locally. Only necessary numerical references remain. |
| Budget adapter | Project C/ASM, generator and own objects supplied; vendor template obtained locally and fingerprint-matched. |
| Unicorn 2.1.4 | GPL/BSD/component terms, matching upstream source and build instructions retained. |
| Python / pyelftools / ADB / WebView2 | Version-matched notices; SDK and system-runtime scope recorded separately. |
| Fonts | Provenance/open terms retained for Noto Serif SC, Roboto Condensed and Share Tech Mono; no Matisse. |

Details: `third_party/provenance.json`, `LICENSES/`, `third_party/BUILD-SOURCES.md`. [Unicorn terms](https://github.com/unicorn-engine/unicorn/blob/2.1.4/COPYING) · [CC BY-NC-SA 4.0](https://creativecommons.org/licenses/by-nc-sa/4.0/)

This notice creates no exclusive rights in numerical facts. Vendor UI, fonts and marks in instructional captures retain their owners' rights. Published captures use cropping/privacy masking only, without generative UI reconstruction.

Owner-side extraction reduces direct vendor-file distribution; it does not establish authorization for every use. Rules on necessary modification, research and redistribution still depend on applicable law and actual conduct. [Chinese software regulation, articles 16, 17 and 24](https://xzfg.moj.gov.cn/mobile/law/detail?LawID=581)

Names identify compatibility/provenance, not endorsement. Publish from a fresh clean export, never personal history, backups, private binary patches or rollback archives.
