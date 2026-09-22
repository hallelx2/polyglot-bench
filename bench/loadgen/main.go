// Load generator for the polyglot benchmark.
//
// Two modes:
//
//	closed — N connections, each sending the next request as soon as the
//	         previous one returns. Measures peak throughput.
//	open   — requests are *scheduled* at a fixed arrival rate; latency is
//	         measured from the intended send time, not the actual one, so a
//	         server that falls behind is penalised (no coordinated omission).
package main

import (
	"bytes"
	"context"
	"crypto/sha256"
	"encoding/json"
	"flag"
	"fmt"
	"io"
	"math"
	"net"
	"net/http"
	"os"
	"runtime"
	"sort"
	"strconv"
	"strings"
	"sync"
	"sync/atomic"
	"time"
)

type corpus struct {
	Price   []json.RawMessage `json:"price"`
	Summary []int             `json:"summary"`
}

type sample struct {
	lat    time.Duration
	status int
	bytes  int
	at     time.Duration // offset from measurement start
}

type Percentiles struct {
	Min  float64 `json:"minMs"`
	P50  float64 `json:"p50Ms"`
	P75  float64 `json:"p75Ms"`
	P90  float64 `json:"p90Ms"`
	P95  float64 `json:"p95Ms"`
	P99  float64 `json:"p99Ms"`
	P999 float64 `json:"p999Ms"`
	Max  float64 `json:"maxMs"`
	Mean float64 `json:"meanMs"`
	Std  float64 `json:"stddevMs"`
}

type Bucket struct {
	T      int     `json:"t"`
	RPS    float64 `json:"rps"`
	P50    float64 `json:"p50Ms"`
	P99    float64 `json:"p99Ms"`
	Errors int     `json:"errors"`
}

type Resource struct {
	CPUSecondsUser float64 `json:"cpuSecondsUser"`
	CPUSecondsSys  float64 `json:"cpuSecondsSys"`
	CPUPercentCore float64 `json:"cpuPercentOfOneCore"`
	PeakRssMB      float64 `json:"peakRssMb"`
	AvgRssMB       float64 `json:"avgRssMb"`
	Threads        int     `json:"threads"`
}

type Result struct {
	Stack       string         `json:"stack"`
	ProbeMs     float64        `json:"machineProbeMs"`
	Scenario    string         `json:"scenario"`
	Mode        string         `json:"mode"`
	Rep         int            `json:"rep"`
	Conns       int            `json:"conns"`
	TargetRate  int            `json:"targetRate"`
	DurationSec float64        `json:"durationSec"`
	WarmupSec   float64        `json:"warmupSec"`
	StartedAt   string         `json:"startedAt"`
	Requests    int            `json:"requests"`
	OK          int            `json:"ok"`
	Errors      int            `json:"errors"`
	StatusCount map[string]int `json:"statusCount"`
	RPS         float64        `json:"rps"`
	Throughput  float64        `json:"bytesPerSec"`
	Latency     Percentiles    `json:"latency"`
	Timeseries  []Bucket       `json:"timeseries"`
	Resource    *Resource      `json:"resource,omitempty"`
	Host        map[string]any `json:"host"`
}

var (
	base     = flag.String("base", "http://127.0.0.1:8080", "service base URL")
	stack    = flag.String("stack", "unknown", "stack id")
	scenario = flag.String("scenario", "quote", "quote|checkout|summary")
	mode     = flag.String("mode", "closed", "closed|open")
	conns    = flag.Int("conns", 64, "concurrent connections")
	rate     = flag.Int("rate", 0, "target arrival rate for open mode (req/s)")
	dur      = flag.Duration("duration", 20*time.Second, "measured duration")
	warmup   = flag.Duration("warmup", 5*time.Second, "warmup, excluded from stats")
	corpusP  = flag.String("corpus", "bench/corpus.json", "corpus path")
	outP     = flag.String("out", "", "output json path ('-' for stdout)")
	rep      = flag.Int("rep", 0, "repetition index")
	svcPid   = flag.Int("pid", 0, "service pid to sample CPU/RSS from")
)

func main() {
	flag.Parse()

	raw, err := os.ReadFile(*corpusP)
	if err != nil {
		fatal(err)
	}
	var c corpus
	if err := json.Unmarshal(raw, &c); err != nil {
		fatal(err)
	}

	// Pre-build every request body/URL once so the generator does no work
	// on the hot path beyond issuing the request.
	type req struct {
		url  string
		body []byte
	}
	var reqs []req
	switch *scenario {
	case "quote", "checkout":
		path := "/api/" + *scenario
		for _, b := range c.Price {
			reqs = append(reqs, req{*base + path, []byte(b)})
		}
	case "summary":
		for _, id := range c.Summary {
			reqs = append(reqs, req{*base + "/api/customers/" + strconv.Itoa(id) + "/summary", nil})
		}
	default:
		fatal(fmt.Errorf("unknown scenario %q", *scenario))
	}

	transport := &http.Transport{
		Proxy:               nil,
		MaxIdleConns:        *conns * 2,
		MaxIdleConnsPerHost: *conns * 2,
		MaxConnsPerHost:     *conns * 2,
		IdleConnTimeout:     90 * time.Second,
		DisableCompression:  true,
		ForceAttemptHTTP2:   false,
		DialContext: (&net.Dialer{
			Timeout:   5 * time.Second,
			KeepAlive: 60 * time.Second,
		}).DialContext,
	}
	client := &http.Client{Transport: transport, Timeout: 30 * time.Second}

	var cursor atomic.Uint64
	next := func() req { return reqs[int(cursor.Add(1)-1)%len(reqs)] }

	do := func(r req) (int, int, error) {
		var body io.Reader
		if r.body != nil {
			body = bytes.NewReader(r.body)
		}
		method := http.MethodGet
		if r.body != nil {
			method = http.MethodPost
		}
		hr, err := http.NewRequest(method, r.url, body)
		if err != nil {
			return 0, 0, err
		}
		if r.body != nil {
			hr.Header.Set("Content-Type", "application/json")
		}
		resp, err := client.Do(hr)
		if err != nil {
			return 0, 0, err
		}
		n, _ := io.Copy(io.Discard, resp.Body)
		resp.Body.Close()
		return resp.StatusCode, int(n), nil
	}

	// ---- machine probe ------------------------------------------------
	// Fixed CPU work, timed. The number is meaningless on its own; across runs
	// it reads how fast this machine was at that moment, so a run degraded by
	// a noisy neighbour or a throttled clock is visible in the results rather
	// than silently folded into the stack's score.
	probe := machineProbe()

	// ---- warmup ------------------------------------------------------
	if *warmup > 0 {
		var wg sync.WaitGroup
		stop := time.Now().Add(*warmup)
		for i := 0; i < *conns; i++ {
			wg.Add(1)
			go func() {
				defer wg.Done()
				for time.Now().Before(stop) {
					_, _, _ = do(next())
				}
			}()
		}
		wg.Wait()
	}

	// ---- measurement -------------------------------------------------
	ctx, cancel := context.WithCancel(context.Background())
	resCh := make(chan *Resource, 1)
	if *svcPid > 0 {
		go sampleResource(ctx, *svcPid, resCh)
	}

	start := time.Now()
	perWorker := make([][]sample, *conns)
	var wg sync.WaitGroup

	if *mode == "open" {
		if *rate <= 0 {
			fatal(fmt.Errorf("-rate is required in open mode"))
		}
		total := int(float64(*rate) * dur.Seconds())
		interval := time.Duration(float64(time.Second) / float64(*rate))
		sched := make(chan time.Time, *rate*2)
		go func() {
			defer close(sched)
			for i := 0; i < total; i++ {
				due := start.Add(time.Duration(i) * interval)
				if d := time.Until(due); d > 0 {
					time.Sleep(d)
				}
				sched <- due
			}
		}()
		for w := 0; w < *conns; w++ {
			wg.Add(1)
			go func(w int) {
				defer wg.Done()
				buf := make([]sample, 0, total / *conns + 16)
				for due := range sched {
					st, n, err := do(next())
					done := time.Now()
					if err != nil {
						st = 0
					}
					// latency from the *intended* send time
					buf = append(buf, sample{lat: done.Sub(due), status: st,
						bytes: n, at: done.Sub(start)})
				}
				perWorker[w] = buf
			}(w)
		}
	} else {
		stop := start.Add(*dur)
		for w := 0; w < *conns; w++ {
			wg.Add(1)
			go func(w int) {
				defer wg.Done()
				buf := make([]sample, 0, 4096)
				for {
					now := time.Now()
					if !now.Before(stop) {
						break
					}
					st, n, err := do(next())
					done := time.Now()
					if err != nil {
						st = 0
					}
					buf = append(buf, sample{lat: done.Sub(now), status: st,
						bytes: n, at: done.Sub(start)})
				}
				perWorker[w] = buf
			}(w)
		}
	}
	wg.Wait()
	elapsed := time.Since(start)
	cancel()

	var res *Resource
	if *svcPid > 0 {
		select {
		case r := <-resCh:
			res = r
		case <-time.After(2 * time.Second):
		}
	}

	// ---- aggregate ---------------------------------------------------
	all := make([]sample, 0, 1<<16)
	for _, b := range perWorker {
		all = append(all, b...)
	}
	out := Result{
		Stack: *stack, ProbeMs: probe, Scenario: *scenario, Mode: *mode, Rep: *rep,
		Conns: *conns, TargetRate: *rate,
		DurationSec: elapsed.Seconds(), WarmupSec: warmup.Seconds(),
		StartedAt:   start.UTC().Format(time.RFC3339Nano),
		StatusCount: map[string]int{},
		Host: map[string]any{
			"cores": runtime.NumCPU(), "go": runtime.Version(),
		},
		Resource: res,
	}
	lat := make([]float64, 0, len(all))
	var totalBytes int64
	for _, s := range all {
		out.Requests++
		key := strconv.Itoa(s.status)
		if s.status == 0 {
			key = "transport_error"
		}
		out.StatusCount[key]++
		if s.status >= 200 && s.status < 300 {
			out.OK++
		} else {
			out.Errors++
		}
		totalBytes += int64(s.bytes)
		lat = append(lat, float64(s.lat.Nanoseconds())/1e6)
	}
	sort.Float64s(lat)
	out.RPS = float64(out.Requests) / elapsed.Seconds()
	out.Throughput = float64(totalBytes) / elapsed.Seconds()
	out.Latency = pct(lat)
	out.Timeseries = buckets(all, elapsed)

	enc, _ := json.MarshalIndent(out, "", "  ")
	if *outP == "" || *outP == "-" {
		os.Stdout.Write(append(enc, '\n'))
	} else {
		if err := os.WriteFile(*outP, enc, 0o644); err != nil {
			fatal(err)
		}
		fmt.Printf("%-16s %-9s %-6s rep%d  %8.0f rps  p50 %6.2fms  p99 %7.2fms  err %d\n",
			*stack, *scenario, *mode, *rep, out.RPS, out.Latency.P50, out.Latency.P99, out.Errors)
	}
}

func pct(sorted []float64) Percentiles {
	if len(sorted) == 0 {
		return Percentiles{}
	}
	at := func(q float64) float64 {
		i := int(q * float64(len(sorted)-1))
		return sorted[i]
	}
	var sum float64
	for _, v := range sorted {
		sum += v
	}
	mean := sum / float64(len(sorted))
	var sq float64
	for _, v := range sorted {
		sq += (v - mean) * (v - mean)
	}
	return Percentiles{
		Min: sorted[0], P50: at(0.50), P75: at(0.75), P90: at(0.90),
		P95: at(0.95), P99: at(0.99), P999: at(0.999),
		Max: sorted[len(sorted)-1], Mean: mean,
		Std: math.Sqrt(sq / float64(len(sorted))),
	}
}

func buckets(all []sample, elapsed time.Duration) []Bucket {
	n := int(elapsed.Seconds()) + 1
	if n < 1 {
		return nil
	}
	lats := make([][]float64, n)
	errs := make([]int, n)
	for _, s := range all {
		i := int(s.at.Seconds())
		if i < 0 || i >= n {
			continue
		}
		lats[i] = append(lats[i], float64(s.lat.Nanoseconds())/1e6)
		if s.status < 200 || s.status >= 300 {
			errs[i]++
		}
	}
	out := make([]Bucket, 0, n)
	for i := 0; i < n; i++ {
		sort.Float64s(lats[i])
		b := Bucket{T: i, RPS: float64(len(lats[i])), Errors: errs[i]}
		if len(lats[i]) > 0 {
			b.P50 = lats[i][len(lats[i])*50/100]
			b.P99 = lats[i][min(len(lats[i])-1, len(lats[i])*99/100)]
		}
		out = append(out, b)
	}
	return out
}

// sampleResource polls /proc/<pid>/stat and /status for the service process.
func sampleResource(ctx context.Context, pid int, out chan<- *Resource) {
	clk := 100.0 // USER_HZ on Linux
	read := func() (utime, stime float64, rssMB float64, threads int, ok bool) {
		b, err := os.ReadFile(fmt.Sprintf("/proc/%d/stat", pid))
		if err != nil {
			return 0, 0, 0, 0, false
		}
		s := string(b)
		// fields after the (comm) blob
		i := strings.LastIndex(s, ")")
		if i < 0 {
			return 0, 0, 0, 0, false
		}
		f := strings.Fields(s[i+2:])
		if len(f) < 22 {
			return 0, 0, 0, 0, false
		}
		ut, _ := strconv.ParseFloat(f[11], 64) // utime  (field 14)
		st, _ := strconv.ParseFloat(f[12], 64) // stime  (field 15)
		th, _ := strconv.Atoi(f[17])           // num_threads (field 20)
		rss, _ := strconv.ParseFloat(f[21], 64)
		return ut / clk, st / clk, rss * 4096 / (1024 * 1024), th, true
	}
	u0, s0, _, _, ok := read()
	if !ok {
		out <- nil
		return
	}
	start := time.Now()
	var peak, sum float64
	var count int
	var maxThreads int
	t := time.NewTicker(250 * time.Millisecond)
	defer t.Stop()
	for {
		select {
		case <-ctx.Done():
			u1, s1, rss, th, ok := read()
			if !ok {
				out <- nil
				return
			}
			el := time.Since(start).Seconds()
			if rss > peak {
				peak = rss
			}
			sum += rss
			count++
			if th > maxThreads {
				maxThreads = th
			}
			cpu := (u1 - u0) + (s1 - s0)
			out <- &Resource{
				CPUSecondsUser: u1 - u0, CPUSecondsSys: s1 - s0,
				CPUPercentCore: cpu / el * 100, PeakRssMB: peak,
				AvgRssMB: sum / float64(max(count, 1)), Threads: maxThreads,
			}
			return
		case <-t.C:
			_, _, rss, th, ok := read()
			if !ok {
				continue
			}
			if rss > peak {
				peak = rss
			}
			if th > maxThreads {
				maxThreads = th
			}
			sum += rss
			count++
		}
	}
}

// machineProbe hashes a fixed buffer a fixed number of times and returns the
// wall-clock milliseconds it took. Deterministic work in, machine speed out.
func machineProbe() float64 {
	buf := make([]byte, 64*1024)
	for i := range buf {
		buf[i] = byte(i * 7)
	}
	start := time.Now()
	h := sha256.New()
	for i := 0; i < 400; i++ {
		h.Reset()
		h.Write(buf)
		_ = h.Sum(nil)
	}
	return float64(time.Since(start).Nanoseconds()) / 1e6
}

func fatal(err error) { fmt.Fprintln(os.Stderr, "loadgen:", err); os.Exit(1) }
