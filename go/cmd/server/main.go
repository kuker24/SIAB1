package main

import (
	"log"
	"net/http"

	"siab1/internal/config"
	"siab1/internal/httpserver"
	"siab1/internal/persistence"
)

var revision = "unknown"

func main() {
	cfg := config.Load()
	store := persistence.Connect(cfg.DatabaseURL, cfg.RedisURL)
	h := httpserver.New(cfg, store)
	addr := ":" + cfg.Port
	log.Printf("siab1 listening on %s runtime=go revision=%s", addr, revision)
	if err := http.ListenAndServe(addr, h); err != nil {
		log.Fatal(err)
	}
}
