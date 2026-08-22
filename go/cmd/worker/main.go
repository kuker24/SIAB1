package main

import (
	"context"
	"log"
	"os"
	"os/signal"
	"syscall"
	"time"

	"siab1/internal/config"
	"siab1/internal/exam"
	"siab1/internal/persistence"
)

func main() {
	cfg := config.Load()
	store := persistence.Connect(cfg.DatabaseURL, cfg.RedisURL)
	ctx, stop := signal.NotifyContext(context.Background(), os.Interrupt, syscall.SIGTERM)
	defer stop()
	log.Printf("siab1 worker started")
	go interval(ctx, 60*time.Second, "publications", func() {
		published, unpublished, err := store.ProcessScheduledPublications(ctx, time.Now().UTC())
		if err != nil {
			log.Printf("scheduled publications failed: %v", err)
			return
		}
		if published > 0 || unpublished > 0 {
			log.Printf("scheduled publications: published=%d unpublished=%d", published, unpublished)
		}
	})
	go interval(ctx, 30*time.Second, "close-expired-sessions", func() {
		exam.CloseExpiredSessions(ctx, store)
	})
	<-ctx.Done()
	log.Printf("siab1 worker stopped")
}

func interval(ctx context.Context, d time.Duration, name string, fn func()) {
	t := time.NewTicker(d)
	defer t.Stop()
	for {
		select {
		case <-ctx.Done():
			return
		case <-t.C:
			log.Printf("worker tick %s", name)
			fn()
		}
	}
}

func dailyUTC(ctx context.Context, hour, min int, name string, fn func()) {
	for {
		wait := untilUTC(time.Now().UTC(), hour, min, nil)
		timer := time.NewTimer(wait)
		select {
		case <-ctx.Done():
			timer.Stop()
			return
		case <-timer.C:
			log.Printf("worker tick %s", name)
			fn()
		}
	}
}

func weeklyUTC(ctx context.Context, weekday time.Weekday, hour, min int, name string, fn func()) {
	wd := weekday
	for {
		wait := untilUTC(time.Now().UTC(), hour, min, &wd)
		timer := time.NewTimer(wait)
		select {
		case <-ctx.Done():
			timer.Stop()
			return
		case <-timer.C:
			log.Printf("worker tick %s", name)
			fn()
		}
	}
}

func untilUTC(now time.Time, hour, min int, weekday *time.Weekday) time.Duration {
	next := time.Date(now.Year(), now.Month(), now.Day(), hour, min, 0, 0, time.UTC)
	if weekday != nil {
		for next.Weekday() != *weekday || !next.After(now) {
			next = next.Add(24 * time.Hour)
		}
		return next.Sub(now)
	}
	if !next.After(now) {
		next = next.Add(24 * time.Hour)
	}
	return next.Sub(now)
}
