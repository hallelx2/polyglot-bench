// Gin + pgx: the popular Go framework over the same hand-written SQL the
// stdlib service uses, so Gin's cost shows up on its own rather than mixed
// with an ORM's. Compare against cmd/gingorm for what the ORM adds.
package main

import (
	"context"
	"errors"
	"log"
	"net/http"
	"os"
	"strconv"

	"bench/internal/domain"
	"bench/internal/store"

	"github.com/gin-gonic/gin"
)

var st *store.Store

func fail(c *gin.Context, err error) {
	var se *store.StockError
	switch {
	case errors.As(err, &se):
		c.JSON(409, gin.H{"error": "insufficient_stock", "sku": se.SKU})
	case errors.Is(err, store.ErrNotFound):
		c.JSON(404, gin.H{"error": "not_found"})
	default:
		c.JSON(500, gin.H{"error": err.Error()})
	}
}

func main() {
	var err error
	st, err = store.New(context.Background())
	if err != nil {
		log.Fatal(err)
	}
	gin.SetMode(gin.ReleaseMode)
	r := gin.New()

	r.GET("/health", func(c *gin.Context) { c.JSON(http.StatusOK, gin.H{"ok": true}) })

	price := func(write bool) gin.HandlerFunc {
		return func(c *gin.Context) {
			var req domain.Request
			if err := c.ShouldBindJSON(&req); err != nil {
				c.JSON(400, gin.H{"error": "bad_request"})
				return
			}
			var inv domain.Invoice
			var err error
			if write {
				inv, err = st.Checkout(c.Request.Context(), req)
			} else {
				inv, err = st.Quote(c.Request.Context(), req)
			}
			if err != nil {
				fail(c, err)
				return
			}
			c.JSON(200, inv)
		}
	}
	r.POST("/api/quote", price(false))
	r.POST("/api/checkout", price(true))
	r.GET("/api/customers/:id/summary", func(c *gin.Context) {
		id, err := strconv.Atoi(c.Param("id"))
		if err != nil {
			c.JSON(400, gin.H{"error": "bad_request"})
			return
		}
		s, err := st.Summary(c.Request.Context(), id)
		if err != nil {
			fail(c, err)
			return
		}
		c.JSON(200, s)
	})

	log.Fatal(r.Run(":" + os.Getenv("PORT")))
}
