//go:build with_ebpf && (linux || android)

package sing_ebpf

import (
	"testing"
	"time"
)

func TestNormalizeUDPTimeout(t *testing.T) {
	for _, test := range []struct {
		seconds int64
		expect  time.Duration
	}{
		{0, 5 * time.Minute},
		{1, time.Second},
		{300, 5 * time.Minute},
		{3600, time.Hour},
	} {
		actual, err := normalizeUDPTimeout(test.seconds)
		if err != nil {
			t.Fatalf("normalize %d seconds: %v", test.seconds, err)
		}
		if actual != test.expect {
			t.Fatalf("normalize %d seconds: expected %s, got %s", test.seconds, test.expect, actual)
		}
	}

	for _, seconds := range []int64{-1, int64(1<<63-1)/int64(time.Second) + 1} {
		if _, err := normalizeUDPTimeout(seconds); err == nil {
			t.Fatalf("expected %d seconds to be rejected", seconds)
		}
	}
}
