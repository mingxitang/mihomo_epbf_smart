package ebpf

import (
	"net/netip"
	"sort"
)

func compileSharedHostPrefixes(addresses []netip.Addr) ([]netip.Prefix, []netip.Prefix) {
	ipv4Set := make(map[netip.Prefix]struct{})
	ipv6Set := make(map[netip.Prefix]struct{})
	for _, address := range addresses {
		address = address.Unmap()
		switch {
		case address.Is4():
			ipv4Set[netip.PrefixFrom(address, 32)] = struct{}{}
		case address.Is6():
			ipv6Set[netip.PrefixFrom(address, 128)] = struct{}{}
		}
	}
	ipv4 := make([]netip.Prefix, 0, len(ipv4Set))
	for prefix := range ipv4Set {
		ipv4 = append(ipv4, prefix)
	}
	ipv6 := make([]netip.Prefix, 0, len(ipv6Set))
	for prefix := range ipv6Set {
		ipv6 = append(ipv6, prefix)
	}
	sort.Slice(ipv4, func(left, right int) bool {
		return ipv4[left].Addr().Compare(ipv4[right].Addr()) < 0
	})
	sort.Slice(ipv6, func(left, right int) bool {
		return ipv6[left].Addr().Compare(ipv6[right].Addr()) < 0
	})
	return ipv4, ipv6
}
