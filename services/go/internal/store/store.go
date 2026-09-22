package store

import (
	"context"
	"errors"
	"fmt"
	"os"
	"sort"
	"strconv"
	"time"

	"bench/internal/domain"

	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"
)

type Store struct{ Pool *pgxpool.Pool }

var ErrNotFound = errors.New("not_found")

type StockError struct{ SKU string }

func (e *StockError) Error() string { return "insufficient_stock:" + e.SKU }

func New(ctx context.Context) (*Store, error) {
	dsn := os.Getenv("DATABASE_URL")
	cfg, err := pgxpool.ParseConfig(dsn)
	if err != nil {
		return nil, err
	}
	n, _ := strconv.Atoi(os.Getenv("DB_POOL_SIZE"))
	if n == 0 {
		n = 20
	}
	cfg.MaxConns = int32(n)
	cfg.MinConns = int32(n)
	cfg.MaxConnLifetime = time.Hour
	p, err := pgxpool.NewWithConfig(ctx, cfg)
	if err != nil {
		return nil, err
	}
	return &Store{Pool: p}, p.Ping(ctx)
}

type refData struct {
	cust     domain.Customer
	tier     domain.Tier
	products map[string]domain.Product
	rules    []domain.Rule
	taxes    []domain.TaxRate
	coupon   *domain.Coupon
}

const qCustomer = `SELECT c.id, c.region, c.tier_id, t.name, t.points_multiplier,
       t.free_shipping_threshold_cents, t.bonus_points
  FROM customer c JOIN customer_tier t ON t.id = c.tier_id WHERE c.id = $1`

const qProducts = `SELECT id, sku, category, unit_price_cents, weight_grams, tax_exempt
  FROM product WHERE sku = ANY($1)`

const qRules = `SELECT id, scope, tier_id, category, min_qty, sku, percent_bp,
       max_discount_cents, stackable
  FROM discount_rule WHERE active_from <= $1 AND active_to >= $1`

const qTaxes = `SELECT id, category, rate_bp FROM tax_rate WHERE region = $1`

const qCoupon = `SELECT id, code, percent_bp, max_discount_cents, min_spend_cents,
       max_uses, times_used, expires_on FROM coupon WHERE code = $1`

func (s *Store) loadRef(ctx context.Context, q pgx.Tx, conn *pgxpool.Conn,
	req domain.Request, today time.Time) (*refData, error) {

	exec := func(sql string, args ...any) (pgx.Rows, error) {
		if q != nil {
			return q.Query(ctx, sql, args...)
		}
		return conn.Query(ctx, sql, args...)
	}

	d := &refData{products: make(map[string]domain.Product, len(req.Items))}

	rows, err := exec(qCustomer, req.CustomerID)
	if err != nil {
		return nil, err
	}
	found := false
	for rows.Next() {
		found = true
		if err := rows.Scan(&d.cust.ID, &d.cust.Region, &d.cust.TierID, &d.tier.Name,
			&d.tier.PointsMultiplier, &d.tier.FreeShipThreshold, &d.tier.BonusPoints); err != nil {
			rows.Close()
			return nil, err
		}
	}
	rows.Close()
	if err := rows.Err(); err != nil {
		return nil, err
	}
	if !found {
		return nil, ErrNotFound
	}
	d.tier.ID = d.cust.TierID

	skus := make([]string, len(req.Items))
	for i, it := range req.Items {
		skus[i] = it.SKU
	}
	rows, err = exec(qProducts, skus)
	if err != nil {
		return nil, err
	}
	for rows.Next() {
		var p domain.Product
		if err := rows.Scan(&p.ID, &p.SKU, &p.Category, &p.UnitPriceCents,
			&p.WeightGrams, &p.TaxExempt); err != nil {
			rows.Close()
			return nil, err
		}
		d.products[p.SKU] = p
	}
	rows.Close()
	if err := rows.Err(); err != nil {
		return nil, err
	}
	for _, it := range req.Items {
		if _, ok := d.products[it.SKU]; !ok {
			return nil, ErrNotFound
		}
	}

	rows, err = exec(qRules, today)
	if err != nil {
		return nil, err
	}
	for rows.Next() {
		var r domain.Rule
		if err := rows.Scan(&r.ID, &r.Scope, &r.TierID, &r.Category, &r.MinQty,
			&r.SKU, &r.PercentBP, &r.MaxDiscountCents, &r.Stackable); err != nil {
			rows.Close()
			return nil, err
		}
		d.rules = append(d.rules, r)
	}
	rows.Close()
	if err := rows.Err(); err != nil {
		return nil, err
	}

	rows, err = exec(qTaxes, d.cust.Region)
	if err != nil {
		return nil, err
	}
	for rows.Next() {
		var t domain.TaxRate
		if err := rows.Scan(&t.ID, &t.Category, &t.RateBP); err != nil {
			rows.Close()
			return nil, err
		}
		d.taxes = append(d.taxes, t)
	}
	rows.Close()
	if err := rows.Err(); err != nil {
		return nil, err
	}

	if req.CouponCode != nil {
		rows, err = exec(qCoupon, *req.CouponCode)
		if err != nil {
			return nil, err
		}
		for rows.Next() {
			var c domain.Coupon
			if err := rows.Scan(&c.ID, &c.Code, &c.PercentBP, &c.MaxDiscountCents,
				&c.MinSpendCents, &c.MaxUses, &c.TimesUsed, &c.ExpiresOn); err != nil {
				rows.Close()
				return nil, err
			}
			d.coupon = &c
		}
		rows.Close()
		if err := rows.Err(); err != nil {
			return nil, err
		}
	}
	return d, nil
}

func today() time.Time { return time.Date(2026, 9, 21, 0, 0, 0, 0, time.UTC) }

// Quote is the read-only path.
func (s *Store) Quote(ctx context.Context, req domain.Request) (domain.Invoice, error) {
	conn, err := s.Pool.Acquire(ctx)
	if err != nil {
		return domain.Invoice{}, err
	}
	defer conn.Release()

	d, err := s.loadRef(ctx, nil, conn, req, today())
	if err != nil {
		return domain.Invoice{}, err
	}
	// inventory read (not locked on this path)
	ids := make([]int, 0, len(req.Items))
	for _, it := range req.Items {
		ids = append(ids, d.products[it.SKU].ID)
	}
	sort.Ints(ids)
	rows, err := conn.Query(ctx,
		`SELECT product_id, on_hand, reserved FROM inventory
		  WHERE warehouse_id = $1 AND product_id = ANY($2) ORDER BY product_id`,
		req.WarehouseID, ids)
	if err != nil {
		return domain.Invoice{}, err
	}
	for rows.Next() {
		var pid, oh, rv int
		if err := rows.Scan(&pid, &oh, &rv); err != nil {
			rows.Close()
			return domain.Invoice{}, err
		}
	}
	rows.Close()
	if err := rows.Err(); err != nil {
		return domain.Invoice{}, err
	}

	return domain.Price(d.cust, d.tier, req.Items, d.products, d.rules, d.taxes,
		d.coupon, today()), nil
}

// Checkout is the full write transaction.
func (s *Store) Checkout(ctx context.Context, req domain.Request) (domain.Invoice, error) {
	tx, err := s.Pool.Begin(ctx)
	if err != nil {
		return domain.Invoice{}, err
	}
	defer tx.Rollback(ctx)

	d, err := s.loadRef(ctx, tx, nil, req, today())
	if err != nil {
		return domain.Invoice{}, err
	}

	want := make(map[int]int, len(req.Items))
	skuOf := make(map[int]string, len(req.Items))
	ids := make([]int, 0, len(req.Items))
	for _, it := range req.Items {
		p := d.products[it.SKU]
		want[p.ID] += it.Qty
		skuOf[p.ID] = p.SKU
		ids = append(ids, p.ID)
	}
	sort.Ints(ids)

	rows, err := tx.Query(ctx,
		`SELECT product_id, on_hand, reserved FROM inventory
		  WHERE warehouse_id = $1 AND product_id = ANY($2)
		  ORDER BY product_id FOR UPDATE`, req.WarehouseID, ids)
	if err != nil {
		return domain.Invoice{}, err
	}
	avail := make(map[int]int, len(ids))
	for rows.Next() {
		var pid, oh, rv int
		if err := rows.Scan(&pid, &oh, &rv); err != nil {
			rows.Close()
			return domain.Invoice{}, err
		}
		avail[pid] = oh - rv
	}
	rows.Close()
	if err := rows.Err(); err != nil {
		return domain.Invoice{}, err
	}
	for _, pid := range ids {
		if avail[pid] < want[pid] {
			return domain.Invoice{}, &StockError{SKU: skuOf[pid]}
		}
	}

	inv := domain.Price(d.cust, d.tier, req.Items, d.products, d.rules, d.taxes,
		d.coupon, today())

	var orderID int64
	if err := tx.QueryRow(ctx,
		`INSERT INTO "order" (customer_id, warehouse_id, subtotal_cents, coupon_id,
		   coupon_discount_cents, tax_total_cents, shipping_cents, total_cents, points_earned)
		 VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9) RETURNING id`,
		req.CustomerID, req.WarehouseID, inv.SubtotalCents, inv.CouponID,
		inv.CouponDiscountCents, inv.TaxTotalCents, inv.ShippingCents,
		inv.TotalCents, inv.PointsEarned).Scan(&orderID); err != nil {
		return domain.Invoice{}, err
	}
	inv.OrderID = orderID

	sqlStr := `INSERT INTO order_item (order_id, product_id, sku, category, qty,
	   unit_price_cents, discount_cents, net_cents, tax_cents) VALUES `
	args := make([]any, 0, len(inv.Lines)*9)
	for i, l := range inv.Lines {
		if i > 0 {
			sqlStr += ","
		}
		b := i * 9
		sqlStr += fmt.Sprintf("($%d,$%d,$%d,$%d,$%d,$%d,$%d,$%d,$%d)",
			b+1, b+2, b+3, b+4, b+5, b+6, b+7, b+8, b+9)
		args = append(args, orderID, l.ProductID, l.SKU, l.Category, l.Qty,
			l.UnitPriceCents, l.DiscountCents, l.NetCents, l.TaxCents)
	}
	if _, err := tx.Exec(ctx, sqlStr, args...); err != nil {
		return domain.Invoice{}, err
	}

	batch := &pgx.Batch{}
	for _, pid := range ids {
		batch.Queue(`UPDATE inventory SET reserved = reserved + $1
		              WHERE warehouse_id = $2 AND product_id = $3`,
			want[pid], req.WarehouseID, pid)
	}
	batch.Queue(`INSERT INTO ledger_entry (order_id, account, debit_cents, credit_cents)
	             VALUES ($1,'revenue',$2,0), ($1,'tax_payable',0,$3)`,
		orderID, inv.SubtotalCents-inv.CouponDiscountCents, inv.TaxTotalCents)
	if inv.CouponID != nil {
		batch.Queue(`UPDATE coupon SET times_used = times_used + 1 WHERE id = $1`, *inv.CouponID)
	}
	batch.Queue(`INSERT INTO loyalty_transaction (customer_id, order_id, points, kind)
	             VALUES ($1,$2,$3,'earn')`, req.CustomerID, orderID, inv.PointsEarned)
	br := tx.SendBatch(ctx, batch)
	if err := br.Close(); err != nil {
		return domain.Invoice{}, err
	}

	if err := tx.Commit(ctx); err != nil {
		return domain.Invoice{}, err
	}
	return inv, nil
}
