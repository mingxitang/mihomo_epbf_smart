//go:build with_ebpf && (linux || android)

package sing_ebpf

import (
	"testing"

	"github.com/metacubex/mihomo/common/pool"
)

func TestUDPPacketDropReturnsBufferOnce(t *testing.T) {
	packet := &udpPacket{data: pool.Get(1500)}
	if len(packet.Data()) != 1500 {
		t.Fatalf("Data() length is %d, want 1500", len(packet.Data()))
	}
	packet.Drop()
	if packet.Data() != nil {
		t.Fatal("Drop left the payload reachable")
	}
	packet.Drop()
}

func TestSharedRewritePacketDropReturnsBufferOnce(t *testing.T) {
	packet := &sharedRewritePacket{data: pool.Get(1500)}
	if len(packet.Data()) != 1500 {
		t.Fatalf("Data() length is %d, want 1500", len(packet.Data()))
	}
	packet.Drop()
	if packet.Data() != nil {
		t.Fatal("Drop left the payload reachable")
	}
	packet.Drop()
}

func TestPooledPayloadSizesRoundTrip(t *testing.T) {
	for _, size := range []int{1, 64, 512, 1500, 4096, 9000, 65535, 65536} {
		buffer := pool.Get(size)
		if len(buffer) != size {
			t.Fatalf("pool.Get(%d) returned length %d", size, len(buffer))
		}
		if err := pool.Put(buffer); err != nil {
			t.Fatalf("pool.Put of a %d-byte payload failed: %v", size, err)
		}
	}
}
