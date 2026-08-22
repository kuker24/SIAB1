package auth

import "testing"

func TestBearerParse(t *testing.T) {
	if Bearer("Bearer abc") != "abc" {
		t.Fatal("bearer")
	}
	if Bearer("bearer xyz") != "xyz" {
		t.Fatal("case")
	}
	if Bearer("Token abc") != "" {
		t.Fatal("reject")
	}
}

func TestParseTampered(t *testing.T) {
	tok, err := SignUser("secret", 1, "u", "student", "", "", true)
	if err != nil {
		t.Fatal(err)
	}
	if _, err := Parse("other", tok); err == nil {
		t.Fatal("expected bad token")
	}
}
