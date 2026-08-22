package exam

import "testing"

func TestSafeMediaURL(t *testing.T) {
	ok := "https://cdn.example/a.png"
	got, err := safeMediaURL(&ok)
	if err != nil || got == nil || *got != ok {
		t.Fatalf("https: %v %v", got, err)
	}
	rel := "/uploads/a.png"
	got, err = safeMediaURL(&rel)
	if err != nil || got == nil || *got != rel {
		t.Fatalf("rel: %v %v", got, err)
	}
	bad := "javascript:alert(1)"
	if _, err := safeMediaURL(&bad); err == nil {
		t.Fatal("expected reject javascript")
	}
}

func TestClipTextStripsTags(t *testing.T) {
	if got := clipText("  <b>Hai</b>  ", 100); got != "Hai" {
		t.Fatalf("got=%q", got)
	}
}
