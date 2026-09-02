package resolver

import (
	"net/netip"
	"testing"
)

func TestEBPPrefixStoreReplacesBothFamilies(t *testing.T) {
	var store EBPPrefixStore
	ipv4 := netip.MustParsePrefix("198.18.0.0/15")
	ipv6 := netip.MustParsePrefix("fc00::/18")
	store.Set(ipv4, ipv6)
	got4, got6 := store.Get()
	if got4 != ipv4 || got6 != ipv6 {
		t.Fatalf("unexpected prefixes: %s %s", got4, got6)
	}
	store.Set(netip.Prefix{}, netip.Prefix{})
	got4, got6 = store.Get()
	if got4.IsValid() || got6.IsValid() {
		t.Fatalf("stale prefixes were not cleared: %s %s", got4, got6)
	}
}
