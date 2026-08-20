# eBPF transparent inbound

This document covers the Linux/Android cgroup eBPF transparent inbound and the
optional shared-network TCX/TC data path. The feature is enabled in pure-Go
builds with the `with_ebpf` build tag on Linux or Android. Other platforms
compile with a stub that returns an explicit unsupported error.

## Supported environments

- Operating systems: Linux, Android.
- Architectures built by CI: linux/amd64, linux/arm64, android/arm64.
- Make targets: `linux-amd64-ebpf`, `linux-arm64-ebpf`, `android-arm64-ebpf`, `all-ebpf`.
- Kernel: cgroup v2 with BPF support. The loader does not assume a fixed
  minimum kernel version; run the capability probe below on the target device.
- cgroup mode: v2 only. cgroup v1 is rejected with a clear error.

Required kernel features are detected at runtime:

- cgroup/sockaddr program types: connect4/connect6, sendmsg4/6, recvmsg4/6.
- BPF maps: hash, lpm_trie, array, and prog_array as used by the loader.
- Optional: cgroup inet sock release attach type and
  `BPF_MAP_LOOKUP_AND_DELETE_ELEM`. When either is missing the loader uses a
  compatibility path automatically.

## Capabilities and kernel configuration

The process must be privileged or hold the following effective capabilities:

- `CAP_BPF` or `CAP_SYS_ADMIN` for BPF syscalls and cgroup attach.
- `CAP_NET_ADMIN` for shared-network TC qdisc attachment and route/sysctl setup.
- `CAP_NET_RAW` for raw socket operations used by the data path.
- The ability to raise `RLIMIT_MEMLOCK` enough for configured BPF maps.

The kernel needs at least `CONFIG_BPF`, `CONFIG_BPF_SYSCALL`, and
`CONFIG_CGROUP_BPF`. `CONFIG_BPF_JIT` is strongly recommended for throughput.
The shared-network path additionally needs `CONFIG_NET_CLS_BPF`.

## Capability probe

The cilium/ebpf backend performs direct kernel feature probes while preparing
the inbound and reports unsupported required features in the startup error.
The old `common/ebpf/check-kernel.sh` probe was removed in `.3`. For a
repeatable preflight, run the privileged integration suite shown below on the
target kernel; `bpftool prog show`, `bpftool map show`, and `bpftool link show`
remain useful for observing active state.

## Build

Normal builds consume the checked-in generated BPF objects and do not require
cgo, clang, a cross C compiler, or an Android NDK:

```bash
CGO_ENABLED=0 GOOS=linux GOARCH=amd64 go build -tags "with_gvisor with_ebpf" -o mihomo-ebpf .
```

Maintainers need Clang and the pinned NDK sysroot only when regenerating the
objects with `make ebpf_generate`; see `common/ebpf/README.md`.

## Configuration

Add an `ebpf` listener to the `listeners` section:

```yaml
listeners:
  - name: ebpf-inbound
    type: ebpf
    mode: hybrid
    network: [tcp, udp]
    dns-mode: hijack
    udp-timeout: 300
    bypass-private-address: true
    bypass-rule-set: []
    local:
      cgroup-path: /sys/fs/cgroup
      ipv6-mode: auto
      include-uid: []
      exclude-uid: []
      state-capacity: 65536
    shared:
      interface: [wlan0]
      ipv6-mode: off
      state-capacity: 65536
      advanced:
        tc-priority: 0
```

Field behavior:

- `network`: `tcp`, `udp`, or both. Defaults to both when omitted.
- `mode`: `local`, `shared`, or `hybrid`.
- `dns-mode`: `hijack`, `respect_bypass`, or `off`.
- `udp-timeout`: UDP NAT mapping timeout in seconds. Defaults to 300. The
  startup log prints the normalized duration as `udp_timeout=5m0s` for a value
  of `300`.
- `bypass-rule-set`: rule provider tags whose CIDRs populate the bypass map.
- `local.cgroup-path`: absolute cgroup v2 directory. Empty means auto-detect.
- `local.ipv6-mode`: `always`, `auto`, or `off`.
- `local.include-uid`, `local.include-uid-range`, `local.exclude-uid`,
  `local.exclude-uid-range`:
  UID-based interception policy. Ranges use `start:end` syntax.
- Android-only package and user policy also lives under `local`.
- `shared.interface` selects downstream interfaces. Default priority uses TCX
  when available and falls back to clsact; non-default `advanced.tc-priority`
  uses clsact.

## IPv4 and IPv6 behavior

The internal TCP and UDP listeners are created with explicit address families
(`tcp4`, `tcp6`, `udp4`, `udp6`) and IPv6 listeners set `IPV6_V6ONLY`. This
avoids implicit dual-stack listener behavior and keeps the BPF lookup keys
deterministic. With `local.ipv6-mode: auto`, IPv6 interception is enabled only
when the host appears to provide IPv6 connectivity; the probe result is logged.

The redirect address must not overlap routable local traffic. For IPv4 the
default `127.128.0.0/9` is a loopback range that is not normally used by
clients. For IPv6 supply a ULA or local-use prefix such as
`fd00:ebpf::/64`; the IPv6 mode must not be `off` when an IPv6 prefix is
configured.

## Android differences

Android uses the same cgroup v2 mechanism but the effective cgroup hierarchy
and permission model differ by vendor. The auto-detected cgroup path can be
overridden with `cgroup-path`. Package policy is resolved to Android UIDs and
`local.include-android-user` maps a user ID to its per-user UID range.

SELinux must permit BPF map/program creation, cgroup attach, and socket
operations for the mihomo domain. On restricted Android builds the feature is
usually only usable from a root or Magisk-provided service context. Use the
startup probe error and privileged integration suite before debugging traffic.

## Containers

A container running the eBPF inbound needs:

- `/sys/fs/cgroup` mounted read-write and containing the target cgroup v2 hierarchy.
- `CAP_BPF` (or `CAP_SYS_ADMIN`) and `CAP_NET_ADMIN`.
- `RLIMIT_MEMLOCK` not blocked by the container runtime.
- No seccomp profile that filters `bpf`, `setsockopt`, `netlink`, or `tc`.

For shared-network TC mode the container also needs the downstream interface
inside its network namespace and the `net.ipv4.conf.<iface>.route_localnet`
sysctl set on that interface.

## Diagnostics

Start with the capability probe and the startup log line that lists the cgroup,
listener port, DNS mode, programs, and bypass CIDR counts.

- Verifier failure: the log includes the program name, errno, and verifier log.
  Check kernel config/helpers, map capacity, and `RLIMIT_MEMLOCK`.
- Permission denied: verify root or `CAP_BPF`/`CAP_SYS_ADMIN`/`CAP_NET_ADMIN`,
  seccomp, Android SELinux, and container device policy.
- Attach failed: verify the configured path is a cgroup v2 mount, is writable,
  and is not already attached by another instance.
- Port conflict: the internal listener set binds an ephemeral port shared
  across the enabled protocol/family listeners. Startup rolls back all
  listeners if any bind fails; check `ss -lntup` for the reported port.
- `cgroup_path` errors: the path must be absolute and inside the cgroup2 mount.
- `missing UDP DNS binding` or `lookup UDP original destination: ... no such
  file or directory`: use a build containing the connected-DNS lifetime fix.
  Active cached UDP state is refreshed for every packet, and a short-lived
  connected DNS socket keeps its original-destination entry until userspace
  processes the queued response and the normal `udp-timeout` cleanup runs.
  `dns-mode: hijack` can remain enabled. Restart mihomo after upgrading so all
  eBPF programs and maps are recreated from the new build.
- If the startup line prints a duration much shorter than the configured
  `udp-timeout`, the binary predates the timeout-unit fix. Earlier combined
  builds interpreted a configured integer as nanoseconds; `udp-timeout: 300`
  therefore caused userspace cleanup every five seconds and configured the BPF
  flow timeout as one second. Upgrade and confirm the startup line contains
  `udp_timeout=5m0s`.

## Shutdown and cleanup

`Close()` is idempotent. It stops UDP sweeps, detaches BPF links, closes map and
program file descriptors, closes the internal listeners, removes shared-network
TC attachments and local routes, and unregisters the socket protect function.
No BPF objects are pinned by the implementation, so stopping mihomo should
leave no persistent program or map names. Verify with:

```bash
bpftool prog show
bpftool map show
bpftool link show
```

If an old process crashed, restart mihomo; it creates new file descriptors and
does not depend on stale pinned objects.

## Privileged integration tests

The `privileged-integration` job in `.github/workflows/build-ebpf.yml` runs the
real pure-Go suite as an advisory hosted-runner check. It does not block the
Android artifact because GitHub-hosted runners do not guarantee the required
kernel capabilities. Run the same suite as a required gate on a self-hosted
Linux runner with cgroup v2 and root access:

```bash
SING_BOX_EBPF_INTEGRATION=1 CGO_ENABLED=0 go test -count=1 \
  -tags "with_gvisor with_ebpf ebpf_integration" \
  ./common/ebpf/... -run Integration
```

The suite creates temporary cgroups, loads programs, attaches traffic
helpers, and cleans up all state on completion. After stopping mihomo on the
same host, verify `bpftool prog show`, `bpftool map show`, and
`bpftool link show` report no leftover objects.

## Repository automation prerequisites

The sync workflow creates PRs and failure Issues. The target repository must
have:

- Issues enabled, otherwise the failure notification step exits with an
  actionable error instead of creating an Issue.
- GitHub Actions permitted to create and approve pull requests.
- The sync workflow present on the repository default branch so the
  `schedule` trigger is active.

## Relationship with TUN, TProxy, and Redir

The eBPF inbound intercepts sockets inside the selected cgroup; it is not a
full TUN device and does not route all host traffic by itself. It can coexist
with TUN, TProxy, and Redir, but avoid attaching multiple transparent inbound
mechanisms to the same cgroup or interface unless you intentionally split
traffic with UID, CIDR, and `bypass-rule-set` policies. The shared-network mode
uses TC on named downstream interfaces and can be used for hotspot forwarding
while the cgroup path handles local apps.
