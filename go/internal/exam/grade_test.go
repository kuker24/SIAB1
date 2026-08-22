package exam

import (
	"testing"

	"siab1/internal/persistence"
)

func TestGradeSingleCorrect(t *testing.T) {
	q := persistence.QuestionRow{
		Type:   "multiple_choice",
		Points: 4,
		Options: []persistence.OptionRow{
			{ID: 1, IsCorrect: false},
			{ID: 2, IsCorrect: true},
		},
	}
	ok, pts := gradeSingle(q, persistence.AnswerRow{SelectedOptionID: persistence.IntPtr(2)})
	if !ok || pts != 4 {
		t.Fatalf("ok=%v pts=%v", ok, pts)
	}
}

func TestGradeComplexAllOrNothing(t *testing.T) {
	q := persistence.QuestionRow{
		Type:   "multiple_choice_complex",
		Points: 10,
		Options: []persistence.OptionRow{
			{ID: 1, IsCorrect: true},
			{ID: 2, IsCorrect: true},
			{ID: 3, IsCorrect: false},
		},
	}
	ok, pts := gradeComplex(q, persistence.AnswerRow{SelectedOptionIDs: []int32{1, 2}})
	if !ok || pts != 10 {
		t.Fatalf("ok=%v pts=%v", ok, pts)
	}
	ok, pts = gradeComplex(q, persistence.AnswerRow{SelectedOptionIDs: []int32{1}})
	if ok || pts != 0 {
		t.Fatalf("partial should fail ok=%v pts=%v", ok, pts)
	}
}

func TestGradeShortAcceptable(t *testing.T) {
	q := persistence.QuestionRow{
		Type:     "short_answer",
		Points:   5,
		Settings: []byte(`{"acceptable_answers":["Jakarta"]}`),
	}
	correct, pts := gradeShort(q, persistence.AnswerRow{AnswerText: persistence.StrPtr("jakarta")})
	if correct == nil || !*correct || pts == nil || *pts != 5 {
		t.Fatalf("correct=%v pts=%v", correct, pts)
	}
}

func TestGradeEssayPending(t *testing.T) {
	correct, pts := gradeAnswer(persistence.QuestionRow{Type: "essay", Points: 10}, persistence.AnswerRow{AnswerText: persistence.StrPtr("uraian")})
	if correct != nil || pts != nil {
		t.Fatalf("essay should stay pending")
	}
}
