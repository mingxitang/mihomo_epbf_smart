package outboundgroup

import "testing"

func TestSmartDialCandidateOrder(t *testing.T) {
	for _, total := range []int{0, 2, 3, 4, 8, 10} {
		visited := 0
		for iteration := 0; iteration < maxRetries; iteration++ {
			begin, end := smartDialBatchBounds(total, iteration)
			if begin == end {
				break
			}
			if begin != visited || end > total || end <= begin {
				t.Fatalf("total=%d iteration=%d: invalid or repeated batch [%d,%d), visited=%d", total, iteration, begin, end, visited)
			}
			if iteration < 3 && end-begin != 1 {
				t.Fatalf("candidate %d must be tried alone, got [%d,%d)", iteration, begin, end)
			}
			visited = end
		}
		if visited != total {
			t.Fatalf("tried %d of %d candidates", visited, total)
		}
	}
	for iteration := 0; iteration < maxRetries; iteration++ {
		begin, end := smartDialBatchBounds(1, iteration)
		if begin != 0 || end != 1 {
			t.Fatal("single candidate must remain retryable")
		}
	}
}
