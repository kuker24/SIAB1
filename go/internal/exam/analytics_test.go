package exam

import (
	"reflect"
	"testing"

	"siab1/internal/persistence"
)

func TestBuildExamAnalyticsPreservesLegacySemantics(t *testing.T) {
	passing := 40.0
	average, highest, lowest := 45.3333333333, 81.0, 15.0
	row := &persistence.ExamAnalyticsRow{
		TotalParticipants: 6, ActiveSessions: 1, CompletedSessions: 4,
		ScoredSessions: 3, AverageScore: &average, HighestScore: &highest,
		LowestScore: &lowest, PassedSessions: 2, Score0To20: 1,
		Score21To40: 1, Score81To100: 1, TotalViolations: 8,
	}
	got := buildExamAnalytics(677, &passing, row)
	if got["average_score"] != 45.33 || got["pass_rate"] != 50.0 {
		t.Fatalf("scores=%v pass_rate=%v", got["average_score"], got["pass_rate"])
	}
	wantDistribution := map[string]int{
		"0-20": 1, "21-40": 1, "41-60": 0, "61-80": 0, "81-100": 1,
	}
	if !reflect.DeepEqual(got["score_distribution"], wantDistribution) {
		t.Fatalf("distribution=%v", got["score_distribution"])
	}
}

func TestBuildExamAnalyticsZeroPassingAndEmpty(t *testing.T) {
	zero := 0.0
	row := &persistence.ExamAnalyticsRow{
		TotalParticipants: 6, CompletedSessions: 4, ScoredSessions: 3,
	}
	if got := buildExamAnalytics(677, &zero, row); got["pass_rate"] != 75.0 {
		t.Fatalf("zero passing score pass_rate=%v", got["pass_rate"])
	}
	empty := buildExamAnalytics(677, nil, &persistence.ExamAnalyticsRow{})
	if !reflect.DeepEqual(empty["score_distribution"], map[string]int{}) ||
		!reflect.DeepEqual(empty["violation_stats"], map[string]int{}) {
		t.Fatalf("empty payload=%v", empty)
	}
}

func TestQuestionDifficultyStats(t *testing.T) {
	for _, tc := range []struct {
		total, correct int
		rate           float64
		label          string
	}{
		{0, 0, 0, "unknown"}, {10, 8, 80, "easy"},
		{10, 5, 50, "medium"}, {3, 1, 33.33, "hard"},
	} {
		rate, label := questionDifficultyStats(tc.total, tc.correct)
		if rate != tc.rate || label != tc.label {
			t.Fatalf("%d/%d: rate=%v label=%s", tc.correct, tc.total, rate, label)
		}
	}
}

func TestTruncateQuestionTextUsesCharacters(t *testing.T) {
	input := ""
	for range 101 {
		input += "é"
	}
	got := truncateQuestionText(input)
	if len([]rune(got)) != 103 || got[len(got)-3:] != "..." {
		t.Fatalf("truncated text has %d characters", len([]rune(got)))
	}
}

func TestAssessmentClassifications(t *testing.T) {
	if got := panLetter(90, 70, 10); got != "A" {
		t.Fatalf("PAN letter=%s", got)
	}
	if got := panLetter(70, 70, 0); got != "C" {
		t.Fatalf("zero deviation PAN=%s", got)
	}
	if got := panScale10(70, 70, 0); got != 5 {
		t.Fatalf("zero deviation scale=%d", got)
	}
	if papLetter(89.9) != "B" || papLetter(59.9) != "E" {
		t.Fatal("unexpected PAP classification")
	}
	if !isUAMExam(&persistence.ExamRow{Title: "UAM 2026"}) {
		t.Fatal("UAM title not detected")
	}
}
