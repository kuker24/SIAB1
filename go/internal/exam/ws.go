package exam

import (
	"crypto/sha1"
	"encoding/base64"
	"encoding/binary"
	"errors"
	"io"
	"net"
	"net/http"
	"strconv"
	"strings"
	"time"

	"siab1/internal/auth"
)

const wsMagic = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"

func (d deps) examWebSocket(w http.ResponseWriter, r *http.Request) {
	if d.store == nil || !d.store.HasPool() {
		d.tryFallback(w, r)
		return
	}
	conn, err := hijackWebSocket(w, r)
	if err != nil {
		writeDetail(w, http.StatusBadRequest, "WebSocket upgrade diperlukan")
		return
	}
	defer conn.Close()
	_ = conn.SetDeadline(time.Now().Add(2 * time.Hour))

	token := strings.TrimSpace(r.URL.Query().Get("token"))
	if token == "" {
		authz := r.Header.Get("Authorization")
		token = auth.Bearer(authz)
	}
	claims, err := auth.Parse(d.secret, token)
	if err != nil {
		writeWSClose(conn, 4401, "Invalid or expired websocket token")
		return
	}
	if claims.Role != "student" && claims.Role != "guruplus" {
		writeWSClose(conn, 4403, "Only exam participants can access exam websocket")
		return
	}
	userID, err := claims.UserID()
	if err != nil {
		writeWSClose(conn, 4401, "Invalid or expired websocket token")
		return
	}
	pathUser, err := strconv.Atoi(r.PathValue("user_id"))
	if err != nil || pathUser != userID {
		writeWSClose(conn, 4403, "Websocket user mismatch")
		return
	}
	examID, err := strconv.Atoi(r.PathValue("exam_id"))
	if err != nil || examID <= 0 {
		writeWSClose(conn, 4404, "Exam not found")
		return
	}
	if settings, err := d.store.APKSettings(r.Context()); err == nil && settings != nil && settings.Freeze {
		writeWSClose(conn, 4403, "System freeze mode active")
		return
	}
	live, err := d.store.HasLiveSession(r.Context(), userID, examID)
	if err != nil {
		writeWSClose(conn, 1011, "Session lookup failed")
		return
	}
	if !live {
		writeWSClose(conn, 4403, "No active session for this exam")
		return
	}
	for {
		_, err := readWSText(conn)
		if err != nil {
			return
		}
	}
}

func hijackWebSocket(w http.ResponseWriter, r *http.Request) (net.Conn, error) {
	if !strings.EqualFold(r.Header.Get("Upgrade"), "websocket") {
		return nil, errors.New("not websocket")
	}
	key := strings.TrimSpace(r.Header.Get("Sec-WebSocket-Key"))
	if key == "" {
		return nil, errors.New("missing key")
	}
	hj, ok := w.(http.Hijacker)
	if !ok {
		return nil, errors.New("hijack unsupported")
	}
	conn, buf, err := hj.Hijack()
	if err != nil {
		return nil, err
	}
	accept := wsAcceptKey(key)
	_, _ = io.WriteString(buf, "HTTP/1.1 101 Switching Protocols\r\n")
	_, _ = io.WriteString(buf, "Upgrade: websocket\r\n")
	_, _ = io.WriteString(buf, "Connection: Upgrade\r\n")
	_, _ = io.WriteString(buf, "Sec-WebSocket-Accept: "+accept+"\r\n\r\n")
	if err := buf.Flush(); err != nil {
		conn.Close()
		return nil, err
	}
	return conn, nil
}

func wsAcceptKey(key string) string {
	sum := sha1.Sum([]byte(key + wsMagic))
	return base64.StdEncoding.EncodeToString(sum[:])
}

func writeWSClose(conn net.Conn, code int, reason string) {
	payload := make([]byte, 2+len(reason))
	binary.BigEndian.PutUint16(payload[:2], uint16(code))
	copy(payload[2:], reason)
	frame := encodeWSFrame(8, payload)
	_, _ = conn.Write(frame)
}

func encodeWSFrame(opcode byte, payload []byte) []byte {
	n := len(payload)
	var hdr []byte
	hdr = append(hdr, 0x80|opcode)
	if n < 126 {
		hdr = append(hdr, byte(n))
	} else if n < 65536 {
		hdr = append(hdr, 126, byte(n>>8), byte(n))
	} else {
		hdr = append(hdr, 127, 0, 0, 0, 0, byte(n>>24), byte(n>>16), byte(n>>8), byte(n))
	}
	return append(hdr, payload...)
}

func readWSText(conn net.Conn) ([]byte, error) {
	_ = conn.SetReadDeadline(time.Now().Add(90 * time.Second))
	head := make([]byte, 2)
	if _, err := io.ReadFull(conn, head); err != nil {
		return nil, err
	}
	opcode := head[0] & 0x0f
	masked := head[1]&0x80 != 0
	n := int(head[1] & 0x7f)
	if n == 126 {
		ext := make([]byte, 2)
		if _, err := io.ReadFull(conn, ext); err != nil {
			return nil, err
		}
		n = int(binary.BigEndian.Uint16(ext))
	} else if n == 127 {
		ext := make([]byte, 8)
		if _, err := io.ReadFull(conn, ext); err != nil {
			return nil, err
		}
		n = int(binary.BigEndian.Uint64(ext))
	}
	if n < 0 || n > 1<<20 {
		return nil, errors.New("frame too large")
	}
	var mask [4]byte
	if masked {
		if _, err := io.ReadFull(conn, mask[:]); err != nil {
			return nil, err
		}
	}
	payload := make([]byte, n)
	if n > 0 {
		if _, err := io.ReadFull(conn, payload); err != nil {
			return nil, err
		}
	}
	if masked {
		for i := range payload {
			payload[i] ^= mask[i%4]
		}
	}
	switch opcode {
	case 8:
		return nil, io.EOF
	case 9:
		_, _ = conn.Write(encodeWSFrame(10, payload))
		return readWSText(conn)
	case 1, 2, 0:
		return payload, nil
	default:
		return payload, nil
	}
}
