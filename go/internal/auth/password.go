package auth

import "golang.org/x/crypto/bcrypt"

func HashPassword(plain string) (string, error) {
	b, err := bcrypt.GenerateFromPassword([]byte(plain), 12)
	if err != nil {
		return "", err
	}
	return string(b), nil
}

func VerifyPassword(plain, hash string) bool {
	if plain == "" || hash == "" {
		return false
	}
	return bcrypt.CompareHashAndPassword([]byte(hash), []byte(plain)) == nil
}
