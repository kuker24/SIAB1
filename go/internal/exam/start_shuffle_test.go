package exam

import (
	"reflect"
	"testing"
)

func TestPythonShuffleMatchesFastAPISeeds(t *testing.T) {
	fixture := loadStartParityFixture(t)
	tests := []struct {
		seed  string
		items []int
		want  []int
	}{
		{"siab1_test_seed", []int{1, 2, 3, 4, 5}, fixture.StableShuffle},
		{"test-secret_42_9_question_11_options", []int{1, 2, 3, 4}, []int{2, 3, 1, 4}},
		{"test-secret_7_3_question_21_statements", []int{0, 1, 2}, []int{2, 0, 1}},
	}
	for _, test := range tests {
		items := append([]int(nil), test.items...)
		pythonShuffle(items, test.seed)
		if !reflect.DeepEqual(items, test.want) {
			t.Fatalf("seed %q: got %v want %v", test.seed, items, test.want)
		}
	}
}
