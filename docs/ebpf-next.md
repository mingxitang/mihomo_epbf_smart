# Experimental eBPF next inbound

`ebpf-next` is a side-by-side staging area for TanakaLun's unified eBPF
inbound. The existing `type: ebpf` implementation and its source directories
remain unchanged.

## Provenance and scope

- eBPF base: `TanakaLun/mihomo` `e88bb8c6`.
- Smart base already present in this branch: `vernesong/mihomo` `4bc3d49f`.
- Reference used only for stability review: `liuran001/mihomo` `60558cf6`.

This staging path does not include liuran001's automatic UDP/IPv6-capable
proxy selection, Tailscale inbound/Subnet Router/Exit Node additions, TUN
coexistence extension, updater redirection, or cleanup command extensions.

## Layout

- `experimental/tanaka/common/ebpf`: unified eBPF backend.
- `experimental/tanaka/listener/config`: next-generation listener options.
- `experimental/tanaka/listener/sing_ebpf`: unified cgroup/TC/shared inbound.
- `listener/inbound/ebpf_next.go`: opt-in integration with mihomo listeners.

Use the existing `with_ebpf` build tag on Linux or Android. Select the new
path explicitly with `type: ebpf-next`:

```yaml
listeners:
  - name: ebpf-next
    type: ebpf-next
    mode: hybrid
    network: [tcp, udp]
    udp-timeout: 300
    local:
      data-plane: cgroup
      dns-mode: hijack
      ipv6: true
    shared:
      data-plane: packet_rewrite
      interface: [wlan0]
      dns-mode: hijack
      ipv6: true
```

Valid local data planes are `cgroup` and `tc`. Valid shared data planes are
`packet_rewrite` and `socket_assign`. `udp-timeout` is expressed in seconds
and defaults to 300.

## Local stability fixes

- Validate and convert `udp-timeout` seconds instead of treating the integer
  as nanoseconds.
- Publish Fake-IP prefixes through a synchronized store and clear stale values
  when DNS leaves Fake-IP mode.
- Reuse UDP payload buffers and return them exactly once on drop/error paths.

The path is experimental until it has passed privileged traffic tests on the
target Linux/Android kernel. Switching back requires only changing the listener
type from `ebpf-next` to `ebpf` and restoring the old listener fields.

## September 6 upstream synchronization

GitHub automatic merges returned HTTP 409 for both upstreams. Smart was
merged locally; its smart.go conflict was caused by downstream formatting.
Tanaka changes from e3256f2f to e88bb8c6 were applied to the experimental
paths, preserving the existing UDP timeout, Fake-IP synchronization, and
buffer ownership fixes. The legacy `ebpf` backend remains on its own baseline.

The update adds client-data-plane DNS replies, bypass CIDR updates on every
active backend, immutable compiled policies, event-driven shared-flow cleanup,
and TCX/sysctl lifecycle fixes. Both generation-check workflows now check the
experimental objects as well. The build workflow includes experimental backend
privileged tests, with host-capability failures remaining advisory. Integration-test compilation
is a separate required step so compile errors cannot be hidden by that policy.

`.github/upstream-state.json` records the Smart merge and the legacy eBPF
release. The experimental eBPF snapshot is recorded here because it is a
path-mapped port, not a whole-tree merge. Future eBPF-next updates should diff
from e88bb8c6 and map common/ebpf and listener/sing_ebpf into
experimental/tanaka, with listener/config/ebpf.go mapped likewise.

Validation results are recorded in the accompanying dated gap audit.

The first privileged run exposed stale test APIs in the legacy suite and two
upstream experimental test defects: a typed-nil NextKeyBytes cursor/end-of-map
handling, and IPv6 tests requesting programs for disabled data planes. These
test helpers/configurations were corrected without changing either data plane.
