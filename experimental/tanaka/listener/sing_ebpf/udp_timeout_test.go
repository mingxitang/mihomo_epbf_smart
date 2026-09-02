//go:build with_ebpf && (linux || android)

package sing_ebpf

import (
	"testing"
	"time"
)

func TestNormalizeUDPTimeout(t *testing.T) {
	for _, test := range []struct {
		name    string
		seconds int64
		want    time.Duration
		wantErr bool
	}{
		{name: "default", want: 5 * time.Minute},
		{name: "seconds", seconds: 300, want: 5 * time.Minute},
		{name: "negative", seconds: -1, wantErr: true},
		{name: "overflow", seconds: int64(1<<63-1)/int64(time.Second) + 1, wantErr: true},
	} {
		t.Run(test.name, func(t *testing.T) {
			got, err := normalizeUDPTimeout(test.seconds)
			if (err != nil) != test.wantErr {
				t.Fatalf("normalizeUDPTimeout(%d) error = %v", test.seconds, err)
			}
			if !test.wantErr && got != test.want {
				t.Fatalf("normalizeUDPTimeout(%d) = %v, want %v", test.seconds, got, test.want)
			}
		})
	}
}
