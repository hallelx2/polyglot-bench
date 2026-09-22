// Package domain holds the pricing engine described in spec/SPEC.md.
// It is pure: no IO, no clock, no allocation of database handles.
package domain

import (
	"sort"
	"strconv"
	"time"
)

type Tier struct {
	ID                int
	Name              string
	PointsMultiplier  int
	FreeShipThreshold int
	BonusPoints       int
}

type Customer struct {
	ID     int
	Region string
	TierID int
}

type Product struct {
	ID             int
	SKU            string
	Category       string
	UnitPriceCents int
	WeightGrams    int
	TaxExempt      bool
}

type Rule struct {
	ID               int
	Scope            string
	TierID           *int
	Category         *string
	MinQty           *int
	SKU              *string
	PercentBP        int
	MaxDiscountCents *int
	Stackable        bool
}

type TaxRate struct {
	ID       int
	Category *string // nil = region default
	RateBP   int
}

type Coupon struct {
	ID               int
	Code             string
	PercentBP        int
	MaxDiscountCents int
	MinSpendCents    int
	MaxUses          int
	TimesUsed        int
	ExpiresOn        time.Time
}

type ReqItem struct {
	SKU string `json:"sku"`
	Qty int    `json:"qty"`
}

type Request struct {
	CustomerID  int       `json:"customerId"`
	WarehouseID int       `json:"warehouseId"`
	Items       []ReqItem `json:"items"`
	CouponCode  *string   `json:"couponCode"`
}

type Line struct {
	SKU            string   `json:"sku"`
	ProductID      int      `json:"-"`
	Qty            int      `json:"qty"`
	UnitPriceCents int      `json:"unitPriceCents"`
	BaseCents      int      `json:"baseCents"`
	DiscountCents  int      `json:"discountCents"`
	NetCents       int      `json:"netCents"`
	TaxCents       int      `json:"taxCents"`
	PointsEarned   int      `json:"pointsEarned"`
	AppliedRules   []string `json:"appliedRules"`
	Category       string   `json:"-"`
}

type Invoice struct {
	OrderID              int64   `json:"orderId"`
	CustomerID           int     `json:"customerId"`
	Tier                 string  `json:"tier"`
	Lines                []Line  `json:"lines"`
	SubtotalCents        int     `json:"subtotalCents"`
	CouponApplied        bool    `json:"couponApplied"`
	CouponCode           *string `json:"couponCode"`
	CouponRejectedReason *string `json:"couponRejectedReason"`
	CouponDiscountCents  int     `json:"couponDiscountCents"`
	TaxTotalCents        int     `json:"taxTotalCents"`
	ShippingCents        int     `json:"shippingCents"`
	TotalCents           int     `json:"totalCents"`
	PointsEarned         int     `json:"pointsEarned"`
	TotalWeightGrams     int     `json:"totalWeightGrams"`
	CouponID             *int    `json:"-"`
}

// mulBP multiplies by basis points, rounding half-up on the final cent.
func mulBP(base, bp int) int { return (base*bp + 5000) / 10000 }

func ruleMatches(r Rule, tierID int, p Product, qty int) bool {
	switch r.Scope {
	case "tier":
		return r.TierID != nil && *r.TierID == tierID
	case "category":
		return r.Category != nil && *r.Category == p.Category
	case "volume":
		return r.MinQty != nil && qty >= *r.MinQty
	case "sku":
		return r.SKU != nil && *r.SKU == p.SKU
	}
	return false
}

func rateFor(taxes []TaxRate, p Product) int {
	if p.TaxExempt {
		return 0
	}
	def := 0
	for _, t := range taxes {
		if t.Category != nil && *t.Category == p.Category {
			return t.RateBP
		}
		if t.Category == nil {
			def = t.RateBP
		}
	}
	return def
}

func shippingFor(weight int) int {
	switch {
	case weight <= 500:
		return 499
	case weight <= 2000:
		return 899
	case weight <= 10000:
		return 1499
	default:
		return 2499
	}
}

// Price runs the full engine. products is keyed by SKU.
func Price(cust Customer, tier Tier, items []ReqItem, products map[string]Product,
	rules []Rule, taxes []TaxRate, coupon *Coupon, today time.Time) Invoice {

	lines := make([]Line, 0, len(items))
	subtotal, weight, points := 0, 0, 0

	for _, it := range items {
		p := products[it.SKU]
		base := p.UnitPriceCents * it.Qty

		bestFixed, bestFixedID := 0, -1
		stackSum := 0
		contributed := make([]int, 0, 4)
		stackIDs := make([]int, 0, 4)
		scopeByID := make(map[int]string, 4)

		for _, r := range rules {
			if !ruleMatches(r, cust.TierID, p, it.Qty) {
				continue
			}
			amt := mulBP(base, r.PercentBP)
			if r.MaxDiscountCents != nil && amt > *r.MaxDiscountCents {
				amt = *r.MaxDiscountCents
			}
			if r.Stackable {
				stackSum += amt
				stackIDs = append(stackIDs, r.ID)
				scopeByID[r.ID] = r.Scope
			} else if amt > bestFixed || (amt == bestFixed && bestFixedID == -1) {
				bestFixed, bestFixedID = amt, r.ID
				scopeByID[r.ID] = r.Scope
			}
		}
		if bestFixedID >= 0 {
			contributed = append(contributed, bestFixedID)
		}
		contributed = append(contributed, stackIDs...)

		disc := bestFixed + stackSum
		if cap := mulBP(base, 6000); disc > cap {
			disc = cap
		}
		net := base - disc

		sort.Ints(contributed)
		applied := make([]string, len(contributed))
		for i, id := range contributed {
			applied[i] = scopeByID[id] + ":" + strconv.Itoa(id)
		}

		pts := (net / 100) * tier.PointsMultiplier
		lines = append(lines, Line{
			SKU: p.SKU, ProductID: p.ID, Qty: it.Qty, UnitPriceCents: p.UnitPriceCents,
			BaseCents: base, DiscountCents: disc, NetCents: net,
			PointsEarned: pts, AppliedRules: applied, Category: p.Category,
		})
		subtotal += net
		weight += p.WeightGrams * it.Qty
		points += pts
	}

	// ---- coupon -------------------------------------------------------
	var couponID *int
	var couponCode *string
	var reject *string
	couponDiscount := 0
	applied := false

	if coupon != nil {
		couponCode = &coupon.Code
		switch {
		case today.After(coupon.ExpiresOn):
			r := "expired"
			reject = &r
		case coupon.TimesUsed >= coupon.MaxUses:
			r := "exhausted"
			reject = &r
		case subtotal < coupon.MinSpendCents:
			r := "min_spend_not_met"
			reject = &r
		default:
			applied = true
			couponDiscount = mulBP(subtotal, coupon.PercentBP)
			if couponDiscount > coupon.MaxDiscountCents {
				couponDiscount = coupon.MaxDiscountCents
			}
			couponID = &coupon.ID
		}
	}

	// pro-rata split, remainder to the largest line
	shares := make([]int, len(lines))
	if applied && couponDiscount > 0 && subtotal > 0 {
		sum, maxIdx, maxNet := 0, 0, -1
		for i, l := range lines {
			shares[i] = couponDiscount * l.NetCents / subtotal
			sum += shares[i]
			if l.NetCents > maxNet {
				maxNet, maxIdx = l.NetCents, i
			}
		}
		shares[maxIdx] += couponDiscount - sum
	}

	taxTotal := 0
	for i := range lines {
		taxable := lines[i].NetCents - shares[i]
		lines[i].TaxCents = mulBP(taxable, rateFor(taxes, products[lines[i].SKU]))
		taxTotal += lines[i].TaxCents
	}

	shipping := shippingFor(weight)
	if subtotal-couponDiscount >= tier.FreeShipThreshold {
		shipping = 0
	}
	total := subtotal - couponDiscount + taxTotal + shipping
	if total >= 50000 {
		points += tier.BonusPoints
	}

	return Invoice{
		CustomerID: cust.ID, Tier: tier.Name, Lines: lines,
		SubtotalCents: subtotal, CouponApplied: applied, CouponCode: couponCode,
		CouponRejectedReason: reject, CouponDiscountCents: couponDiscount,
		TaxTotalCents: taxTotal, ShippingCents: shipping, TotalCents: total,
		PointsEarned: points, TotalWeightGrams: weight, CouponID: couponID,
	}
}
