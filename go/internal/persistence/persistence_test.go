package persistence

import (
	"testing"

	"github.com/jackc/pgx/v5"
)

func TestPgBouncerPoolConfigPinsScoredSettings(t *testing.T) {
	config, err := pgbouncerPoolConfig(
		"postgresql://examuser@example.test/siab1" +
			"?pool_max_conns=9&default_query_exec_mode=cache_statement&statement_cache_capacity=512",
	)
	if err != nil {
		t.Fatal(err)
	}
	if config.MaxConns != 4 {
		t.Fatalf("MaxConns=%d", config.MaxConns)
	}
	if config.ConnConfig.DefaultQueryExecMode != pgx.QueryExecModeSimpleProtocol {
		t.Fatalf("DefaultQueryExecMode=%v", config.ConnConfig.DefaultQueryExecMode)
	}
	if config.ConnConfig.StatementCacheCapacity != 0 {
		t.Fatalf("StatementCacheCapacity=%d", config.ConnConfig.StatementCacheCapacity)
	}
}
