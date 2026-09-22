// Fiber (fasthttp) + pgx. Same store, same engine — framework is the only variable.
package main

import (
	"context"
	"errors"
	"log"
	"os"

	"bench/internal/domain"
	"bench/internal/store"

	"github.com/gofiber/fiber/v2"
)

var st *store.Store

func fail(c *fiber.Ctx, err error) error {
	var se *store.StockError
	switch {
	case errors.As(err, &se):
		return c.Status(409).JSON(fiber.Map{"error": "insufficient_stock", "sku": se.SKU})
	case errors.Is(err, store.ErrNotFound):
		return c.Status(404).JSON(fiber.Map{"error": "not_found"})
	default:
		return c.Status(500).JSON(fiber.Map{"error": err.Error()})
	}
}

func main() {
	var err error
	st, err = store.New(context.Background())
	if err != nil {
		log.Fatal(err)
	}
	app := fiber.New(fiber.Config{
		DisableStartupMessage: true,
		StrictRouting:         false,
	})

	app.Get("/health", func(c *fiber.Ctx) error {
		c.Set("Content-Type", "application/json")
		return c.SendString(`{"ok":true}`)
	})

	price := func(write bool) fiber.Handler {
		return func(c *fiber.Ctx) error {
			var req domain.Request
			if err := c.BodyParser(&req); err != nil {
				return c.Status(400).JSON(fiber.Map{"error": "bad_request"})
			}
			var inv domain.Invoice
			var err error
			if write {
				inv, err = st.Checkout(c.UserContext(), req)
			} else {
				inv, err = st.Quote(c.UserContext(), req)
			}
			if err != nil {
				return fail(c, err)
			}
			return c.JSON(inv)
		}
	}
	app.Post("/api/quote", price(false))
	app.Post("/api/checkout", price(true))

	app.Get("/api/customers/:id/summary", func(c *fiber.Ctx) error {
		id, err := c.ParamsInt("id")
		if err != nil {
			return c.Status(400).JSON(fiber.Map{"error": "bad_request"})
		}
		s, err := st.Summary(c.UserContext(), id)
		if err != nil {
			return fail(c, err)
		}
		return c.JSON(s)
	})

	log.Fatal(app.Listen(":" + os.Getenv("PORT")))
}
