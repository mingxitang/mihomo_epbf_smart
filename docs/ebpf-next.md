# Experimental eBPF next inbound

`ebpf-next` is a side-by-side staging area for TanakaLun's unified eBPF
inbound. The existing `type: ebpf` implementation and its source directories
remain unchanged.

## Provenance and scope

- eBPF base: `TanakaLun/mihomo` `e3256f2f`.
- Smart base already present in this branch: `vernesong/mihomo` `86ece769`.
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
