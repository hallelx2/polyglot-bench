// Package gormstore is the same business logic reached through an ORM, so the
// benchmark can separate "Go" from "Go the way most product teams write it".
package gormstore

import (
	"context"
	"os"
	"sort"
	"strconv"
	"time"

	"bench/internal/domain"
	"bench/internal/store"

	"gorm.io/driver/postgres"
	"gorm.io/gorm"
	"gorm.io/gorm/logger"
)

type Tier struct {
	ID                         int `gorm:"primaryKey"`
	Name                       string
	PointsMultiplier           int
	FreeShippingThresholdCents int
	BonusPoints                int
}

func (Tier) TableName() string { return "customer_tier" }

type Customer struct {
	ID       int `gorm:"primaryKey"`
	Email    string
	FullName string
	Region   string
	TierID   int
	Tier     Tier `gorm:"foreignKey:TierID;references:ID"`
}

func (Customer) TableName() string { return "customer" }

type Product struct {
	ID             int    `gorm:"primaryKey"`
	SKU            string `gorm:"column:sku"`
	Name           string
	Category       string
	UnitPriceCents int
	WeightGrams    int
	TaxExempt      bool
}

func (Product) TableName() string { return "product" }

type Inventory struct {
	WarehouseID int `gorm:"primaryKey"`
	ProductID   int `gorm:"primaryKey"`
	OnHand      int
	Reserved    int
}

func (Inventory) TableName() string { return "inventory" }

type DiscountRule struct {
	ID               int `gorm:"primaryKey"`
	Scope            string
	TierID           *int
	Category         *string
	MinQty           *int
	SKU              *string `gorm:"column:sku"`
	PercentBP        int     `gorm:"column:percent_bp"`
	MaxDiscountCents *int
	Stackable        bool
	ActiveFrom       time.Time
	ActiveTo         time.Time
}

func (DiscountRule) TableName() string { return "discount_rule" }

type TaxRate struct {
	ID       int `gorm:"primaryKey"`
	Region   string
	Category *string
	RateBP   int `gorm:"column:rate_bp"`
}

func (TaxRate) TableName() string { return "tax_rate" }

type Coupon struct {
	ID               int `gorm:"primaryKey"`
	Code             string
	PercentBP        int `gorm:"column:percent_bp"`
	MaxDiscountCents int
	MinSpendCents    int
	MaxUses          int
	TimesUsed        int
	ExpiresOn        time.Time
}

func (Coupon) TableName() string { return "coupon" }

type Order struct {
	ID                  int64 `gorm:"primaryKey"`
	CustomerID          int
	WarehouseID         int
	SubtotalCents       int
	CouponID            *int
	CouponDiscountCents int
	TaxTotalCents       int
	ShippingCents       int
	TotalCents          int
	PointsEarned        int
	CreatedAt           time.Time
}

func (Order) TableName() string { return `"order"` }

type OrderItem struct {
	ID             int64 `gorm:"primaryKey"`
	OrderID        int64
	ProductID      int
	SKU            string `gorm:"column:sku"`
	Category       string
	Qty            int
	UnitPriceCents int
	DiscountCents  int
	NetCents       int
	TaxCents       int
}

func (OrderItem) TableName() string { return "order_item" }

type LedgerEntry struct {
	ID          int64 `gorm:"primaryKey"`
	OrderID     int64
	Account     string
	DebitCents  int
	CreditCents int
	CreatedAt   time.Time
}

func (LedgerEntry) TableName() string { return "ledger_entry" }

type LoyaltyTransaction struct {
	ID         int64 `gorm:"primaryKey"`
	CustomerID int
	OrderID    *int64
	Points     int
	Kind       string
	CreatedAt  time.Time
}

func (LoyaltyTransaction) TableName() string { return "loyalty_transaction" }

type Store struct{ DB *gorm.DB }

func New() (*Store, error) {
	db, err := gorm.Open(postgres.Open(os.Getenv("DATABASE_URL")), &gorm.Config{
		Logger:                 logger.Discard,
		SkipDefaultTransaction: true,
		PrepareStmt:            true,
	})
	if err != nil {
		return nil, err
	}
	sqlDB, err := db.DB()
	if err != nil {
		return nil, err
	}
	n, _ := strconv.Atoi(os.Getenv("DB_POOL_SIZE"))
	if n == 0 {
		n = 20
	}
	sqlDB.SetMaxOpenConns(n)
	sqlDB.SetMaxIdleConns(n)
	sqlDB.SetConnMaxLifetime(time.Hour)
	return &Store{DB: db}, sqlDB.Ping()
}

func today() time.Time { return time.Date(2026, 9, 21, 0, 0, 0, 0, time.UTC) }

type ref struct {
	cust     domain.Customer
	tier     domain.Tier
	products map[string]domain.Product
	rules    []domain.Rule
	taxes    []domain.TaxRate
	coupon   *domain.Coupon
	ids      []int
}

func loadRef(tx *gorm.DB, req domain.Request) (*ref, error) {
	var c Customer
	if err := tx.Preload("Tier").First(&c, req.CustomerID).Error; err != nil {
		return nil, store.ErrNotFound
	}
	skus := make([]string, len(req.Items))
	for i, it := range req.Items {
		skus[i] = it.SKU
	}
	var prods []Product
	if err := tx.Where("sku IN ?", skus).Find(&prods).Error; err != nil {
		return nil, err
	}
	r := &ref{products: make(map[string]domain.Product, len(prods))}
	for _, p := range prods {
		r.products[p.SKU] = domain.Product{ID: p.ID, SKU: p.SKU, Category: p.Category,
			UnitPriceCents: p.UnitPriceCents, WeightGrams: p.WeightGrams, TaxExempt: p.TaxExempt}
		r.ids = append(r.ids, p.ID)
	}
	for _, it := range req.Items {
		if _, ok := r.products[it.SKU]; !ok {
			return nil, store.ErrNotFound
		}
	}
	sort.Ints(r.ids)

	r.cust = domain.Customer{ID: c.ID, Region: c.Region, TierID: c.TierID}
	r.tier = domain.Tier{ID: c.Tier.ID, Name: c.Tier.Name,
		PointsMultiplier:  c.Tier.PointsMultiplier,
		FreeShipThreshold: c.Tier.FreeShippingThresholdCents,
		BonusPoints:       c.Tier.BonusPoints}

	var rules []DiscountRule
	if err := tx.Where("active_from <= ? AND active_to >= ?", today(), today()).
		Find(&rules).Error; err != nil {
		return nil, err
	}
	for _, x := range rules {
		r.rules = append(r.rules, domain.Rule{ID: x.ID, Scope: x.Scope, TierID: x.TierID,
			Category: x.Category, MinQty: x.MinQty, SKU: x.SKU, PercentBP: x.PercentBP,
			MaxDiscountCents: x.MaxDiscountCents, Stackable: x.Stackable})
	}
	var taxes []TaxRate
	if err := tx.Where("region = ?", c.Region).Find(&taxes).Error; err != nil {
		return nil, err
	}
	for _, x := range taxes {
		r.taxes = append(r.taxes, domain.TaxRate{ID: x.ID, Category: x.Category, RateBP: x.RateBP})
	}
	if req.CouponCode != nil {
		var cp Coupon
		if err := tx.Where("code = ?", *req.CouponCode).First(&cp).Error; err == nil {
			r.coupon = &domain.Coupon{ID: cp.ID, Code: cp.Code, PercentBP: cp.PercentBP,
				MaxDiscountCents: cp.MaxDiscountCents, MinSpendCents: cp.MinSpendCents,
				MaxUses: cp.MaxUses, TimesUsed: cp.TimesUsed, ExpiresOn: cp.ExpiresOn}
		}
	}
	return r, nil
}

func (s *Store) Quote(ctx context.Context, req domain.Request) (domain.Invoice, error) {
	tx := s.DB.WithContext(ctx)
	r, err := loadRef(tx, req)
	if err != nil {
		return domain.Invoice{}, err
	}
	var inv []Inventory
	if err := tx.Where("warehouse_id = ? AND product_id IN ?", req.WarehouseID, r.ids).
		Order("product_id").Find(&inv).Error; err != nil {
		return domain.Invoice{}, err
	}
	return domain.Price(r.cust, r.tier, req.Items, r.products, r.rules, r.taxes,
		r.coupon, today()), nil
}

func (s *Store) Checkout(ctx context.Context, req domain.Request) (domain.Invoice, error) {
	var out domain.Invoice
	err := s.DB.WithContext(ctx).Transaction(func(tx *gorm.DB) error {
		r, err := loadRef(tx, req)
		if err != nil {
			return err
		}
		want := map[int]int{}
		skuOf := map[int]string{}
		for _, it := range req.Items {
			p := r.products[it.SKU]
			want[p.ID] += it.Qty
			skuOf[p.ID] = p.SKU
		}
		var rows []Inventory
		if err := tx.Raw(`SELECT warehouse_id, product_id, on_hand, reserved FROM inventory
		    WHERE warehouse_id = ? AND product_id IN ? ORDER BY product_id FOR UPDATE`,
			req.WarehouseID, r.ids).Scan(&rows).Error; err != nil {
			return err
		}
		for _, iv := range rows {
			if iv.OnHand-iv.Reserved < want[iv.ProductID] {
				return &store.StockError{SKU: skuOf[iv.ProductID]}
			}
		}

		inv := domain.Price(r.cust, r.tier, req.Items, r.products, r.rules, r.taxes,
			r.coupon, today())

		o := Order{CustomerID: req.CustomerID, WarehouseID: req.WarehouseID,
			SubtotalCents: inv.SubtotalCents, CouponID: inv.CouponID,
			CouponDiscountCents: inv.CouponDiscountCents, TaxTotalCents: inv.TaxTotalCents,
			ShippingCents: inv.ShippingCents, TotalCents: inv.TotalCents,
			PointsEarned: inv.PointsEarned, CreatedAt: time.Now()}
		if err := tx.Create(&o).Error; err != nil {
			return err
		}
		inv.OrderID = o.ID

		items := make([]OrderItem, 0, len(inv.Lines))
		for _, l := range inv.Lines {
			items = append(items, OrderItem{OrderID: o.ID, ProductID: l.ProductID,
				SKU: l.SKU, Category: l.Category, Qty: l.Qty,
				UnitPriceCents: l.UnitPriceCents, DiscountCents: l.DiscountCents,
				NetCents: l.NetCents, TaxCents: l.TaxCents})
		}
		if err := tx.Create(&items).Error; err != nil {
			return err
		}
		for _, pid := range r.ids {
			if err := tx.Exec(`UPDATE inventory SET reserved = reserved + ?
			     WHERE warehouse_id = ? AND product_id = ?`,
				want[pid], req.WarehouseID, pid).Error; err != nil {
				return err
			}
		}
		led := []LedgerEntry{
			{OrderID: o.ID, Account: "revenue", DebitCents: inv.SubtotalCents - inv.CouponDiscountCents, CreatedAt: time.Now()},
			{OrderID: o.ID, Account: "tax_payable", CreditCents: inv.TaxTotalCents, CreatedAt: time.Now()},
		}
		if err := tx.Create(&led).Error; err != nil {
			return err
		}
		if inv.CouponID != nil {
			if err := tx.Exec(`UPDATE coupon SET times_used = times_used + 1 WHERE id = ?`,
				*inv.CouponID).Error; err != nil {
				return err
			}
		}
		lt := LoyaltyTransaction{CustomerID: req.CustomerID, OrderID: &o.ID,
			Points: inv.PointsEarned, Kind: "earn", CreatedAt: time.Now()}
		if err := tx.Create(&lt).Error; err != nil {
			return err
		}
		out = inv
		return nil
	})
	return out, err
}

func (s *Store) Summary(ctx context.Context, customerID int) (store.Summary, error) {
	tx := s.DB.WithContext(ctx)
	var c Customer
	if err := tx.Preload("Tier").First(&c, customerID).Error; err != nil {
		return store.Summary{}, store.ErrNotFound
	}
	out := store.Summary{CustomerID: customerID, Tier: c.Tier.Name}

	var orders []Order
	if err := tx.Where("customer_id = ?", customerID).
		Order("created_at DESC").Limit(50).Find(&orders).Error; err != nil {
		return out, err
	}
	ids := make([]int64, 0, len(orders))
	for i, o := range orders {
		ids = append(ids, o.ID)
		out.LifetimeCents += o.TotalCents
		if i == 0 {
			t := o.CreatedAt.UTC()
			out.LastOrderAt = &t
		}
	}
	out.OrderCount = len(orders)
	if out.OrderCount > 0 {
		out.AvgOrderCents = out.LifetimeCents / out.OrderCount
	}

	byCat := map[string]int{}
	if len(ids) > 0 {
		var items []OrderItem
		if err := tx.Where("order_id IN ?", ids).Find(&items).Error; err != nil {
			return out, err
		}
		for _, it := range items {
			byCat[it.Category] += it.NetCents
		}
	}
	cats := make([]store.CategorySpend, 0, len(byCat))
	for k, v := range byCat {
		cats = append(cats, store.CategorySpend{Category: k, NetCents: v})
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

	var lts []LoyaltyTransaction
	if err := tx.Where("customer_id = ?", customerID).
		Order("created_at DESC").Limit(100).Find(&lts).Error; err != nil {
		return out, err
	}
	for _, l := range lts {
		out.PointsBalance += l.Points
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
