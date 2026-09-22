// stdlib net/http + pgx. No framework.
package main

import (
	"context"
	"encoding/json"
	"errors"
	"log"
	"net/http"
	"os"
	"strconv"
	"strings"

	"bench/internal/domain"
	"bench/internal/store"
)

var st *store.Store

func writeErr(w http.ResponseWriter, code int, msg string, extra map[string]any) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(code)
	m := map[string]any{"error": msg}
	for k, v := range extra {
		m[k] = v
	}
	json.NewEncoder(w).Encode(m)
}

func handlePrice(write bool) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodPost {
			writeErr(w, 405, "method_not_allowed", nil)
			return
		}
		var req domain.Request
		if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
			writeErr(w, 400, "bad_request", nil)
			return
		}
		var inv domain.Invoice
		var err error
		if write {
			inv, err = st.Checkout(r.Context(), req)
		} else {
			inv, err = st.Quote(r.Context(), req)
		}
		if err != nil {
			var se *store.StockError
			switch {
			case errors.As(err, &se):
				writeErr(w, 409, "insufficient_stock", map[string]any{"sku": se.SKU})
			case errors.Is(err, store.ErrNotFound):
				writeErr(w, 404, "not_found", nil)
			default:
				writeErr(w, 500, err.Error(), nil)
			}
			return
		}
		w.Header().Set("Content-Type", "application/json")
		json.NewEncoder(w).Encode(inv)
	}
}

func handleSummary(w http.ResponseWriter, r *http.Request) {
	p := strings.TrimPrefix(r.URL.Path, "/api/customers/")
	p = strings.TrimSuffix(p, "/summary")
	id, err := strconv.Atoi(p)
	if err != nil {
		writeErr(w, 400, "bad_request", nil)
		return
	}
	s, err := st.Summary(r.Context(), id)
	if err != nil {
		if errors.Is(err, store.ErrNotFound) {
			writeErr(w, 404, "not_found", nil)
			return
		}
		writeErr(w, 500, err.Error(), nil)
		return
	}
	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(s)
}

func main() {
	var err error
	st, err = store.New(context.Background())
	if err != nil {
		log.Fatal(err)
	}
	mux := http.NewServeMux()
	mux.HandleFunc("/health", func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		w.Write([]byte(`{"ok":true}`))
	})
	mux.HandleFunc("/api/quote", handlePrice(false))
	mux.HandleFunc("/api/checkout", handlePrice(true))
	mux.HandleFunc("/api/customers/", handleSummary)

	port := os.Getenv("PORT")
	srv := &http.Server{Addr: ":" + port, Handler: mux}
	log.Fatal(srv.ListenAndServe())
}
