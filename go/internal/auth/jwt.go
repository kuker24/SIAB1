package auth

import (
	"crypto/hmac"
	"crypto/sha256"
	"encoding/base64"
	"encoding/json"
	"errors"
	"fmt"
	"strconv"
	"strings"
	"time"
)

var (
	ErrNoToken  = errors.New("missing token")
	ErrBadToken = errors.New("invalid token")
	ErrExpired  = errors.New("token expired")
	ErrNoSecret = errors.New("jwt secret missing")
)

type Claims struct {
	Sub          string `json:"sub"`
	Username     string `json:"username"`
	Role         string `json:"role"`
	FullName     string `json:"full_name,omitempty"`
	StudentClass string `json:"student_class,omitempty"`
	JobTitle     string `json:"job_title,omitempty"`
	IsActive     bool   `json:"is_active"`
	Exp          int64  `json:"exp"`
	isActiveSet  bool
}

func (c *Claims) UnmarshalJSON(data []byte) error {
	type claimsAlias Claims
	var decoded claimsAlias
	if err := json.Unmarshal(data, &decoded); err != nil {
		return err
	}
	var fields map[string]json.RawMessage
	if err := json.Unmarshal(data, &fields); err != nil {
		return err
	}
	*c = Claims(decoded)
	_, c.isActiveSet = fields["is_active"]
	return nil
}

// Active matches FastAPI's hot-path rule: old tokens without is_active remain active.
func (c Claims) Active() bool {
	return !c.isActiveSet || c.IsActive
}

func (c Claims) UserID() (int, error) {
	id, err := strconv.Atoi(strings.TrimSpace(c.Sub))
	if err != nil || id <= 0 {
		return 0, ErrBadToken
	}
	return id, nil
}

func Sign(secret string, claims Claims) (string, error) {
	if strings.TrimSpace(secret) == "" {
		return "", ErrNoSecret
	}
	if claims.Exp == 0 {
		claims.Exp = time.Now().UTC().Add(time.Duration(ExamJWTExpiryMinutes) * time.Minute).Unix()
	}
	header, err := json.Marshal(map[string]string{"alg": "HS256", "typ": "JWT"})
	if err != nil {
		return "", err
	}
	payload, err := json.Marshal(claims)
	if err != nil {
		return "", err
	}
	h := b64(header)
	p := b64(payload)
	sig := signHS256(secret, h+"."+p)
	return h + "." + p + "." + sig, nil
}

func Parse(secret, token string) (*Claims, error) {
	if strings.TrimSpace(secret) == "" {
		return nil, ErrNoSecret
	}
	token = strings.TrimSpace(token)
	if token == "" {
		return nil, ErrNoToken
	}
	parts := strings.Split(token, ".")
	if len(parts) != 3 {
		return nil, ErrBadToken
	}
	if !validHeader(parts[0]) || !hmac.Equal(
		[]byte(signHS256(secret, parts[0]+"."+parts[1])),
		[]byte(parts[2]),
	) {
		return nil, ErrBadToken
	}
	raw, err := base64.RawURLEncoding.DecodeString(parts[1])
	if err != nil {
		return nil, ErrBadToken
	}
	var claims Claims
	if err := json.Unmarshal(raw, &claims); err != nil {
		return nil, ErrBadToken
	}
	if claims.Username == "" || claims.Role == "" || claims.Sub == "" {
		return nil, ErrBadToken
	}
	if claims.Exp > 0 && time.Now().UTC().Unix() >= claims.Exp {
		return nil, ErrExpired
	}
	return &claims, nil
}

func ParseAllowExpired(secret, token string) (*Claims, error) {
	if strings.TrimSpace(secret) == "" {
		return nil, ErrNoSecret
	}
	token = strings.TrimSpace(token)
	if token == "" {
		return nil, ErrNoToken
	}
	parts := strings.Split(token, ".")
	if len(parts) != 3 {
		return nil, ErrBadToken
	}
	if !validHeader(parts[0]) || !hmac.Equal(
		[]byte(signHS256(secret, parts[0]+"."+parts[1])),
		[]byte(parts[2]),
	) {
		return nil, ErrBadToken
	}
	raw, err := base64.RawURLEncoding.DecodeString(parts[1])
	if err != nil {
		return nil, ErrBadToken
	}
	var claims Claims
	if err := json.Unmarshal(raw, &claims); err != nil {
		return nil, ErrBadToken
	}
	if claims.Username == "" || claims.Role == "" || claims.Sub == "" {
		return nil, ErrBadToken
	}
	return &claims, nil
}

func WithinRefreshGrace(c *Claims, graceMinutes int) bool {
	if c == nil || c.Exp <= 0 {
		return false
	}
	if graceMinutes < 0 {
		graceMinutes = 0
	}
	return time.Now().UTC().Unix() <= c.Exp+int64(graceMinutes)*60
}

func Bearer(header string) string {
	header = strings.TrimSpace(header)
	if len(header) < 8 {
		return ""
	}
	if !strings.EqualFold(header[:7], "bearer ") {
		return ""
	}
	return strings.TrimSpace(header[7:])
}

func signHS256(secret, data string) string {
	mac := hmac.New(sha256.New, []byte(secret))
	_, _ = mac.Write([]byte(data))
	return b64(mac.Sum(nil))
}

func validHeader(encoded string) bool {
	raw, err := base64.RawURLEncoding.DecodeString(encoded)
	if err != nil {
		return false
	}
	var header struct {
		Algorithm string `json:"alg"`
	}
	return json.Unmarshal(raw, &header) == nil && header.Algorithm == "HS256"
}

func b64(v []byte) string {
	return base64.RawURLEncoding.EncodeToString(v)
}

func MustUserID(c *Claims) int {
	id, err := c.UserID()
	if err != nil {
		return 0
	}
	return id
}

func TokenTTLSeconds() int {
	return ExamJWTExpiryMinutes * 60
}

func FormatDetail(err error) string {
	switch {
	case errors.Is(err, ErrExpired):
		return "Token kedaluwarsa"
	case errors.Is(err, ErrNoToken):
		return "Not authenticated"
	default:
		return "Not authenticated"
	}
}

func SignUser(secret string, userID int, username, role, fullName, studentClass string, active bool) (string, error) {
	return Sign(secret, Claims{
		Sub:          fmt.Sprintf("%d", userID),
		Username:     username,
		Role:         role,
		FullName:     fullName,
		StudentClass: studentClass,
		IsActive:     active,
	})
}

func SignPayload(secret string, payload any) (string, error) {
	if strings.TrimSpace(secret) == "" {
		return "", ErrNoSecret
	}
	header, err := json.Marshal(map[string]string{"alg": "HS256", "typ": "JWT"})
	if err != nil {
		return "", err
	}
	body, err := json.Marshal(payload)
	if err != nil {
		return "", err
	}
	h := b64(header)
	p := b64(body)
	return h + "." + p + "." + signHS256(secret, h+"."+p), nil
}

func SessionPollToken(secret string, sessionID, userID int) (string, error) {
	payload := struct {
		Sub     string `json:"sub"`
		SID     int    `json:"sid"`
		Type    string `json:"typ"`
		Expires int64  `json:"exp"`
	}{
		Sub:     fmt.Sprintf("%d", userID),
		SID:     sessionID,
		Type:    "session_poll",
		Expires: time.Now().UTC().Add(15 * time.Minute).Unix(),
	}
	return SignPayload(secret, payload)
}
