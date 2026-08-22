package exam

import "testing"

func TestCanShuffleOptions(t *testing.T) {
	if !canShuffleOptions(map[string]any{}, false) {
		t.Fatal("normal question")
	}
	if canShuffleOptions(map[string]any{"is_placeholder": true}, true) {
		t.Fatal("image placeholder locked")
	}
	if !canShuffleOptions(map[string]any{"is_placeholder": true, "allow_placeholder_shuffle": true}, false) {
		t.Fatal("allowed placeholder")
	}
}
