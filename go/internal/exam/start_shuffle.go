package exam

import (
	"crypto/md5"
	"crypto/sha256"
	"encoding/binary"
	"math/bits"
	"reflect"

	"siab1/internal/persistence"
)

const mtSize = 624

type pythonRandom struct {
	mt    [mtSize]uint32
	index int
}

func newPythonRandom(seed string) *pythonRandom {
	digest := md5.Sum([]byte(seed))
	key := []uint32{
		binary.BigEndian.Uint32(digest[12:16]),
		binary.BigEndian.Uint32(digest[8:12]),
		binary.BigEndian.Uint32(digest[4:8]),
		binary.BigEndian.Uint32(digest[0:4]),
	}
	for len(key) > 1 && key[len(key)-1] == 0 {
		key = key[:len(key)-1]
	}
	r := &pythonRandom{}
	r.seedByArray(key)
	return r
}

func (r *pythonRandom) seedByArray(key []uint32) {
	r.mt[0] = 19650218
	for i := 1; i < mtSize; i++ {
		r.mt[i] = 1812433253*(r.mt[i-1]^(r.mt[i-1]>>30)) + uint32(i)
	}
	i, j := 1, 0
	loops := mtSize
	if len(key) > loops {
		loops = len(key)
	}
	for ; loops > 0; loops-- {
		r.mt[i] = (r.mt[i] ^ ((r.mt[i-1] ^ (r.mt[i-1] >> 30)) * 1664525)) + key[j] + uint32(j)
		i++
		j++
		if i >= mtSize {
			r.mt[0] = r.mt[mtSize-1]
			i = 1
		}
		if j >= len(key) {
			j = 0
		}
	}
	for loops = mtSize - 1; loops > 0; loops-- {
		r.mt[i] = (r.mt[i] ^ ((r.mt[i-1] ^ (r.mt[i-1] >> 30)) * 1566083941)) - uint32(i)
		i++
		if i >= mtSize {
			r.mt[0] = r.mt[mtSize-1]
			i = 1
		}
	}
	r.mt[0] = 0x80000000
	r.index = mtSize
}

func (r *pythonRandom) uint32() uint32 {
	if r.index >= mtSize {
		for i := 0; i < mtSize; i++ {
			y := (r.mt[i] & 0x80000000) | (r.mt[(i+1)%mtSize] & 0x7fffffff)
			r.mt[i] = r.mt[(i+397)%mtSize] ^ (y >> 1)
			if y&1 != 0 {
				r.mt[i] ^= 0x9908b0df
			}
		}
		r.index = 0
	}
	y := r.mt[r.index]
	r.index++
	y ^= y >> 11
	y ^= (y << 7) & 0x9d2c5680
	y ^= (y << 15) & 0xefc60000
	y ^= y >> 18
	return y
}

func (r *pythonRandom) randBelow(n int) int {
	if n <= 1 {
		return 0
	}
	k := bits.Len(uint(n))
	for {
		candidate := int(r.uint32() >> (32 - k))
		if candidate < n {
			return candidate
		}
	}
}

func pythonShuffle[T any](items []T, seed string) {
	if len(items) < 2 {
		return
	}
	original := append([]T(nil), items...)
	random := newPythonRandom(seed)
	for i := len(items) - 1; i > 0; i-- {
		j := random.randBelow(i + 1)
		items[i], items[j] = items[j], items[i]
	}
	equal := true
	for i := range items {
		if !reflect.DeepEqual(items[i], original[i]) {
			equal = false
			break
		}
	}
	if equal {
		digest := md5.Sum([]byte(seed))
		mod := 0
		for _, value := range digest {
			mod = (mod*256 + int(value)) % (len(items) - 1)
		}
		offset := mod + 1
		rotated := append(append([]T(nil), items[offset:]...), items[:offset]...)
		copy(items, rotated)
	}
}

// Legacy preview uses these functions; native START uses pythonShuffle directly.
func shuffleQuestions(items []persistence.QuestionRow, seed string) {
	rnd := seeded(seed)
	for i := len(items) - 1; i > 0; i-- {
		j := int(rnd.Uint32() % uint32(i+1))
		items[i], items[j] = items[j], items[i]
	}
}

func shuffleOptions(items []persistence.OptionRow, seed string) {
	rnd := seeded(seed)
	for i := len(items) - 1; i > 0; i-- {
		j := int(rnd.Uint32() % uint32(i+1))
		items[i], items[j] = items[j], items[i]
	}
}

type rng struct{ s uint64 }

func seeded(seed string) *rng {
	sum := sha256.Sum256([]byte(seed))
	return &rng{s: binary.BigEndian.Uint64(sum[:8])}
}

func (r *rng) Uint32() uint32 {
	r.s = r.s*1664525 + 1013904223
	return uint32(r.s >> 32)
}
