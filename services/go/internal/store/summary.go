package store

import (
	"context"
	"sort"
	"time"
)

type CategorySpend struct {
	Category string `json:"category"`
	NetCents int    `json:"netCents"`
}

type Summary struct {
	CustomerID    int             `json:"customerId"`
	Tier          string          `json:"tier"`
	OrderCount    int             `json:"orderCount"`
	LifetimeCents int             `json:"lifetimeValueCents"`
	AvgOrderCents int             `json:"avgOrderValueCents"`
	TopCategories []CategorySpend `json:"topCategories"`
	PointsBalance int             `json:"pointsBalance"`
	Segment       string          `json:"segment"`
	LastOrderAt   *time.Time      `json:"lastOrderAt"`
}

func (s *Store) Summary(ctx context.Context, customerID int) (Summary, error) {
	conn, err := s.Pool.Acquire(ctx)
	if err != nil {
		return Summary{}, err
	}
	defer conn.Release()

	var out Summary
	out.CustomerID = customerID
	row := conn.QueryRow(ctx,
		`SELECT t.name FROM customer c JOIN customer_tier t ON t.id = c.tier_id
		  WHERE c.id = $1`, customerID)
	if err := row.Scan(&out.Tier); err != nil {
		return Summary{}, ErrNotFound
	}

	rows, err := conn.Query(ctx,
		`SELECT id, total_cents, created_at FROM "order"
		  WHERE customer_id = $1 ORDER BY created_at DESC LIMIT 50`, customerID)
	if err != nil {
		return Summary{}, err
	}
	ids := make([]int64, 0, 50)
	for rows.Next() {
		var id int64
		var total int
		var at time.Time
		if err := rows.Scan(&id, &total, &at); err != nil {
			rows.Close()
			return Summary{}, err
		}
		ids = append(ids, id)
		out.LifetimeCents += total
		if out.LastOrderAt == nil {
			t := at.UTC()
			out.LastOrderAt = &t
		}
	}
	rows.Close()
	if err := rows.Err(); err != nil {
		return Summary{}, err
	}
	out.OrderCount = len(ids)
	if out.OrderCount > 0 {
		out.AvgOrderCents = out.LifetimeCents / out.OrderCount
	}

	byCat := make(map[string]int, 12)
	if len(ids) > 0 {
		rows, err = conn.Query(ctx,
			`SELECT category, net_cents FROM order_item WHERE order_id = ANY($1)`, ids)
		if err != nil {
			return Summary{}, err
		}
		for rows.Next() {
			var c string
			var n int
			if err := rows.Scan(&c, &n); err != nil {
				rows.Close()
				return Summary{}, err
			}
			byCat[c] += n
		}
		rows.Close()
		if err := rows.Err(); err != nil {
			return Summary{}, err
		}
	}
	cats := make([]CategorySpend, 0, len(byCat))
	for c, n := range byCat {
		cats = append(cats, CategorySpend{c, n})
	}
	sort.Slice(cats, func(i, j int) bool {
		if cats[i].NetCents != cats[j].NetCents {
			return cats[i].NetCents > cats[j].NetCents
		}
		return cats[i].Category < cats[j].Category
	})
	if len(cats) > 5 {
		cats = cats[:5]
	}
	out.TopCategories = cats

	rows, err = conn.Query(ctx,
		`SELECT points FROM loyalty_transaction WHERE customer_id = $1
		  ORDER BY created_at DESC LIMIT 100`, customerID)
	if err != nil {
		return Summary{}, err
	}
	for rows.Next() {
		var p int
		if err := rows.Scan(&p); err != nil {
			rows.Close()
			return Summary{}, err
		}
		out.PointsBalance += p
	}
	rows.Close()
	if err := rows.Err(); err != nil {
		return Summary{}, err
	}

	switch {
	case out.LifetimeCents >= 500000 && out.OrderCount >= 20:
		out.Segment = "champion"
	case out.OrderCount >= 10:
		out.Segment = "loyal"
	case out.OrderCount >= 3:
		out.Segment = "promising"
	default:
		out.Segment = "new"
	}
	return out, nil
}
