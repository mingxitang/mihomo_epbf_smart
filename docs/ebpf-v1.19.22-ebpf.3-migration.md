# eBPF v1.19.22-ebpf.3 migration

## Target

The migration branch `migration/ebpf-v1.19.22-ebpf.3` combines:

- Smart `Alpha` at `5664b1ba0943206e0fa140eb0f31f393688b0c2d`;
- eBPF release `v1.19.22-ebpf.3` at
  `0c8987595fa2d4466681353bc92111b1f1fa584c`;
- Go module baseline 1.25.0 and default CI/release toolchain Go 1.26.

## Architecture change

The eBPF runtime no longer uses the cgo/C loader boundary. Loading, maps,
cgroup attachment, kernel feature probes, runtime status, and TCX/clsact
selection now use `github.com/cilium/ebpf` from Go. Generated little- and
big-endian BPF bindings and objects live under `common/ebpf/internal/bpfgen`.
Shared-network attachment prefers TCX and falls back to clsact.

The listener configuration and lifecycle use the new nested local/shared
schema. The migration retains the combined repository's UDP timeout unit fix;
the new upstream UDP recovery map replaces the earlier DNS-only
socket-release workaround.

## Build and CI

- `go.mod` and `test/go.mod` require Go 1.25.0.
- General tests run on Go 1.25 and 1.26.
- General and eBPF release builds use Go 1.26.
- eBPF builds and tests run with `CGO_ENABLED=0`; old NDK/cross-C-compiler and
  sing-tun patch steps are no longer part of the eBPF build path.
- The obsolete `common/ebpf/check-kernel.sh` workflow call was removed. The
  privileged job now runs the new pure-Go integration suite directly.
- The automated build/release target is Android ARM64. Linux and other
  platforms remain test or compile checks, but are not published by this
  release pipeline. The artifact and released binary are both named `mihomo`;
  its checksum is `mihomo.sha256`.
- Upstreams are checked at 00:23 UTC every third calendar day. A released
  upstream change triggers the Android build and prerelease automatically;
  manual synchronization defaults to forcing the same pipeline even when the
  upstream state is unchanged.

## Synchronization baseline

`.github/upstream-state.json` records the Smart and eBPF commits and their
current release markers. Future automation must compare from this baseline;
it must not treat `.2` as still integrated.

## Validation status

Validated locally on 2026-08-20 with official Go 1.26.5:

- [x] `gofmt` on every changed Go source file;
- [x] `go vet` across all Git-tracked source package roots;
- [x] default unit tests across all Git-tracked source package roots;
- [x] Linux AMD64 tagged test binaries compile for `common/ebpf` and
  `listener/sing_ebpf`, including the integration-test build tag;
- [x] generated eBPF bindings and objects are byte-identical to the `.3` tag;
- [x] Linux AMD64 v3, Linux ARM64, and Android ARM64 eBPF builds;
- [x] release-shaped Android ARM64 build named `mihomo`, stripped to
  55,574,788 bytes (53.0 MiB);
- [x] non-eBPF Windows AMD64, macOS ARM64, and Linux AMD64 builds;
- [x] all seven GitHub workflow YAML files parse successfully;
- [ ] privileged Linux eBPF integration tests.

The local Windows host cannot execute the compiled Linux tests and access to
WSL is denied, so the privileged suite remains a CI/target-device gate. The
migration is not ready to merge into `Alpha` until that job completes
successfully.
