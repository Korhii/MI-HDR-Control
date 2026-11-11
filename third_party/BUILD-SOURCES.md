# Third-party and project builds

## Unicorn 2.1.4

`sources/unicorn-2.1.4.tar.gz` is the official PyPI source distribution. The installed Windows native library was matched byte-for-byte to `unicorn-2.1.4-cp37-abi3-win_amd64.whl`. Source URL/digests and the matching library digest are in `provenance.json`. The archive includes QEMU/ARM sources, CMake files and Python build/installation scripts; retain its original notices. Follow its included build instructions for Windows/CMake and Python packaging. A local rebuild was not claimed to be bit-for-bit reproducible with the upstream compiler environment.

## Project helpers

Readable C/C++/Java/ASM is supplied under `scripts/`. `build_bridge.py` uses a JDK, Android API stubs and D8 on the publisher's build machine. Consumer PCs do not need those tools. Project-owned ARM objects accompany their source; `build_local_oem.py` combines them only with the owner's fingerprinted original template. Original vendor modules/models are not distributed.

The native Windows frontend builds with Visual Studio x64 C++ tools using `scripts/windows-launcher/build.cmd`. A registered installation is discovered with vswhere, including prereleases. Alternatively set `MI_VCVARS` to a locally licensed `vcvars64.bat`; no author's installation path is embedded in the public script. WebView2 SDK files come from official NuGet 1.0.3650.58 and retain its BSD license.

Do not regenerate Android signing keys for an update without a tested ownership/signature migration. Private signing keys are never included.

Event helpers are in `scripts/persistence-native/events/`; the service-argument helper is `scripts/mi_service_call_args.c`. Native debug-path sanitization is recorded in `native-build-sanitization.json`; only non-loaded debug strings changed, and all PT_LOAD bytes stayed identical. musl and Zig-runtime notices are included under LICENSES.
