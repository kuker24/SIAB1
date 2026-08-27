package exam

import (
	"context"
	"net/http"
	"sync"
)

type startAdmission struct {
	limit       int
	sem         chan struct{}
	mu          sync.Mutex
	holders     int
	waiters     int
	peakHolders int
	peakWaiters int
}

func newStartAdmission(limit int) *startAdmission {
	if limit <= 0 {
		limit = 4
	}
	return &startAdmission{limit: limit, sem: make(chan struct{}, limit)}
}

func (a *startAdmission) acquire(ctx context.Context) (func(), error) {
	a.mu.Lock()
	a.waiters++
	if a.waiters > a.peakWaiters {
		a.peakWaiters = a.waiters
	}
	a.mu.Unlock()

	select {
	case a.sem <- struct{}{}:
		a.mu.Lock()
		a.waiters--
		a.holders++
		if a.holders > a.peakHolders {
			a.peakHolders = a.holders
		}
		a.mu.Unlock()
	case <-ctx.Done():
		a.mu.Lock()
		a.waiters--
		a.mu.Unlock()
		return nil, ctx.Err()
	}

	var once sync.Once
	return func() {
		once.Do(func() {
			<-a.sem
			a.mu.Lock()
			a.holders--
			a.mu.Unlock()
		})
	}, nil
}

type startAdmissionSnapshot struct {
	Limit       int
	Holders     int
	Waiters     int
	PeakHolders int
	PeakWaiters int
}

func (a *startAdmission) snapshot() startAdmissionSnapshot {
	a.mu.Lock()
	defer a.mu.Unlock()
	return startAdmissionSnapshot{
		Limit:       a.limit,
		Holders:     a.holders,
		Waiters:     a.waiters,
		PeakHolders: a.peakHolders,
		PeakWaiters: a.peakWaiters,
	}
}

func (d deps) startAdmissionStatus(w http.ResponseWriter, _ *http.Request) {
	snapshot := d.startGate.snapshot()
	writeJSON(w, http.StatusOK, map[string]int{
		"limit":        snapshot.Limit,
		"holders":      snapshot.Holders,
		"waiters":      snapshot.Waiters,
		"peak_holders": snapshot.PeakHolders,
		"peak_waiters": snapshot.PeakWaiters,
	})
}
