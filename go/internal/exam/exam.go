package exam

import (
	"context"
	"log"

	"siab1/internal/persistence"
)

func CloseExpiredSessions(ctx context.Context, store *persistence.Store) {
	if store == nil {
		log.Printf("close-expired-sessions skip: no store")
		return
	}
	n, err := store.CloseExpiredSessions(ctx)
	if err != nil {
		log.Printf("close-expired-sessions skip: %v", err)
		return
	}
	log.Printf("close-expired-sessions closed=%d", n)
}
