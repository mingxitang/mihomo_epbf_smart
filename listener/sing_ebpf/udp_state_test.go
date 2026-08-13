//go:build with_ebpf && (linux || android)

package sing_ebpf

import (
	"net/netip"
	"testing"
	"time"
)

func TestCachedPacketStateRefreshesActivity(t *testing.T) {
	client := netip.MustParseAddrPort("127.0.0.1:53111")
	redirectAddress := netip.MustParseAddr("127.128.0.10")
	destination := netip.MustParseAddrPort("8.8.8.8:53")
	table := &udpClientTable{}
	table.setBinding(client, destination, redirectAddress, false)

	clientState, loaded := table.load(client)
	if !loaded {
		t.Fatal("expected UDP client state")
	}
	oldActivity := time.Now().Add(-10 * time.Minute)
	clientState.access.Lock()
	clientState.lastActive = oldActivity
	clientState.access.Unlock()

	beforeLookup := time.Now()
	original, bindingReady, loaded := table.cachedPacketState(client, redirectAddress)
	if !loaded || !bindingReady {
		t.Fatal("expected cached UDP packet state and redirect binding")
	}
	if original.original.Destination != destination {
		t.Fatalf("unexpected original destination: %s", original.original.Destination)
	}
	clientState.access.RLock()
	lastActive := clientState.lastActive
	clientState.access.RUnlock()
	if lastActive.Before(beforeLookup) {
		t.Fatalf("cached packet did not refresh activity: %s", lastActive)
	}
}

func TestDeleteIdleClientRechecksActivity(t *testing.T) {
	client := netip.MustParseAddrPort("127.0.0.1:53111")
	redirectAddress := netip.MustParseAddr("127.128.0.10")
	destination := netip.MustParseAddrPort("8.8.8.8:53")
	table := &udpClientTable{}
	table.setBinding(client, destination, redirectAddress, false)
	clientState, loaded := table.load(client)
	if !loaded {
		t.Fatal("expected UDP client state")
	}

	now := time.Now()
	clientState.access.Lock()
	clientState.lastActive = now
	clientState.access.Unlock()
	if releases := table.deleteIdleClient(client, clientState, now, 5*time.Minute); len(releases) != 0 {
		t.Fatalf("active client unexpectedly released %d redirects", len(releases))
	}
	if _, loaded = table.load(client); !loaded {
		t.Fatal("active UDP client was deleted")
	}
}

func TestSweepDeletesIdleClient(t *testing.T) {
	client := netip.MustParseAddrPort("127.0.0.1:53111")
	redirectAddress := netip.MustParseAddr("127.128.0.10")
	destination := netip.MustParseAddrPort("8.8.8.8:53")
	table := &udpClientTable{}
	table.setBinding(client, destination, redirectAddress, false)
	clientState, loaded := table.load(client)
	if !loaded {
		t.Fatal("expected UDP client state")
	}
	now := time.Now()
	clientState.access.Lock()
	clientState.lastActive = now.Add(-10 * time.Minute)
	clientState.access.Unlock()

	var releases []udpRedirectRelease
	table.sweep(now, 5*time.Minute, func(values []udpRedirectRelease) {
		releases = append(releases, values...)
	})
	if _, loaded = table.load(client); loaded {
		t.Fatal("idle UDP client was not deleted")
	}
	if len(releases) != 1 {
		t.Fatalf("expected one redirect release, got %d", len(releases))
	}
	if releases[0].reference != (udpRedirectReference{address: redirectAddress}) {
		t.Fatalf("unexpected redirect release: %+v", releases[0])
	}
	if releases[0].sharedFlow != nil {
		t.Fatal("unexpected shared-network flow in cgroup redirect release")
	}
}

func TestConnectedDNSBindingReleasedOnIdle(t *testing.T) {
	client := netip.MustParseAddrPort("127.0.0.1:53111")
	redirectAddress := netip.MustParseAddr("127.128.0.10")
	destination := netip.MustParseAddrPort("8.8.8.8:53")
	table := &udpClientTable{}
	table.setBinding(client, destination, redirectAddress, true)

	clientState, loaded := table.load(client)
	if !loaded {
		t.Fatal("expected UDP client state")
	}
	now := time.Now()
	clientState.access.Lock()
	clientState.lastActive = now.Add(-10 * time.Minute)
	clientState.access.Unlock()

	var releases []udpRedirectRelease
	table.sweep(now, 5*time.Minute, func(values []udpRedirectRelease) {
		releases = append(releases, values...)
	})
	if len(releases) != 1 {
		t.Fatalf("expected connected DNS redirect release, got %d", len(releases))
	}
}

func TestConnectedNonDNSBindingUsesKernelRelease(t *testing.T) {
	client := netip.MustParseAddrPort("127.0.0.1:53111")
	redirectAddress := netip.MustParseAddr("127.128.0.10")
	destination := netip.MustParseAddrPort("1.1.1.1:443")
	table := &udpClientTable{}
	table.setBinding(client, destination, redirectAddress, true)

	clientState, loaded := table.load(client)
	if !loaded {
		t.Fatal("expected UDP client state")
	}
	now := time.Now()
	clientState.access.Lock()
	clientState.lastActive = now.Add(-10 * time.Minute)
	clientState.access.Unlock()

	var releases []udpRedirectRelease
	table.sweep(now, 5*time.Minute, func(values []udpRedirectRelease) {
		releases = append(releases, values...)
	})
	if len(releases) != 0 {
		t.Fatalf("connected non-DNS redirect should be released by the kernel, got %d userspace releases", len(releases))
	}
}
