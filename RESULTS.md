# Full results

`final` profile — 450 runs, 5 repetitions of
10s after 3s warmup, run order shuffled per
repetition, database restored to seeded state before every run. Zero non-2xx
responses across the suite.

CV is the coefficient of variation of throughput across the repetitions of that
cell. Machine probe: median 62.3 ms against a
best-decile of 58.1 ms;
58 of 450 runs were taken while
the machine was more than 25% off its best speed. Excluding them moves the
medians by 0.0% median.

## quote — saturated, 64 connections

| stack | req/s | p50 | p90 | p99 | p99.9 | CPU ms/call | peak RSS | CV |
|---|--:|--:|--:|--:|--:|--:|--:|--:|
| `rust-axum` | 3,919 | 16.11 | 18.27 | 21.63 | 25.11 | 0.281 | 7.9 MB | 8.2% |
| `rust-actix` | 3,867 | 16.35 | 18.48 | 21.36 | 23.70 | 0.317 | 8.9 MB | 3.9% |
| `rust-hyper` | 3,680 | 17.06 | 20.22 | 24.33 | 27.78 | 0.271 | 7.7 MB | 12.9% |
| `go-fiber` | 3,637 | 17.39 | 19.88 | 23.13 | 26.01 | 0.409 | 22.1 MB | 8.0% |
| `go-nethttp` | 3,546 | 17.82 | 20.54 | 23.64 | 26.47 | 0.444 | 22.7 MB | 5.1% |
| `go-gin` | 3,495 | 18.04 | 21.02 | 24.77 | 27.74 | 0.457 | 31.5 MB | 9.0% |
| `go-gin-gorm` | 2,271 | 27.12 | 38.79 | 50.82 | 62.38 | 1.125 | 35.3 MB | 12.0% |
| `ts-bun-only` | 2,243 | 28.13 | 31.85 | 37.00 | 41.49 | 0.401 | 78.7 MB | 7.3% |
| `ts-bun-hono` | 1,850 | 33.91 | 39.85 | 43.97 | 46.29 | 0.518 | 92.4 MB | 8.9% |
| `ts-node-fastify` | 1,385 | 46.00 | 50.86 | 57.44 | 62.78 | 0.730 | 242.9 MB | 4.9% |

## quote — fixed 300 req/s offered

| stack | req/s | p50 | p90 | p99 | p99.9 | CPU ms/call | peak RSS | CV |
|---|--:|--:|--:|--:|--:|--:|--:|--:|
| `rust-axum` | 300 | 1.83 | 2.34 | 2.84 | 3.53 | 0.217 | 7.7 MB | 0.0% |
| `rust-hyper` | 300 | 1.85 | 2.32 | 3.00 | 3.75 | 0.213 | 7.5 MB | 0.0% |
| `ts-bun-only` | 300 | 1.83 | 2.26 | 2.66 | 3.25 | 0.440 | 76.6 MB | 0.0% |
| `go-nethttp` | 300 | 1.81 | 2.26 | 2.64 | 2.95 | 0.437 | 21.0 MB | 0.0% |
| `go-gin` | 300 | 1.82 | 2.29 | 2.71 | 3.87 | 0.443 | 29.6 MB | 0.0% |
| `go-fiber` | 300 | 1.74 | 2.25 | 3.18 | 3.83 | 0.390 | 21.0 MB | 0.0% |
| `go-gin-gorm` | 300 | 2.10 | 2.64 | 3.10 | 3.46 | 0.863 | 32.4 MB | 0.0% |
| `rust-actix` | 300 | 2.00 | 2.53 | 3.00 | 3.32 | 0.260 | 8.9 MB | 0.0% |
| `ts-bun-hono` | 300 | 2.36 | 2.98 | 3.60 | 4.60 | 0.497 | 90.9 MB | 0.0% |
| `ts-node-fastify` | 300 | 2.51 | 3.07 | 3.58 | 5.64 | 0.593 | 238.8 MB | 0.0% |

## quote — fixed 900 req/s offered

| stack | req/s | p50 | p90 | p99 | p99.9 | CPU ms/call | peak RSS | CV |
|---|--:|--:|--:|--:|--:|--:|--:|--:|
| `go-nethttp` | 900 | 1.50 | 2.05 | 2.48 | 3.01 | 0.388 | 23.1 MB | 0.0% |
| `go-fiber` | 900 | 1.43 | 1.94 | 2.39 | 4.06 | 0.314 | 23.5 MB | 0.0% |
| `go-gin` | 900 | 1.53 | 2.12 | 2.67 | 3.23 | 0.409 | 31.6 MB | 0.0% |
| `rust-axum` | 900 | 1.48 | 2.03 | 2.37 | 2.70 | 0.196 | 9.8 MB | 0.0% |
| `ts-bun-only` | 900 | 1.57 | 2.20 | 2.82 | 3.69 | 0.453 | 75.9 MB | 0.0% |
| `rust-hyper` | 900 | 1.47 | 2.03 | 2.40 | 2.82 | 0.184 | 9.4 MB | 0.0% |
| `ts-bun-hono` | 900 | 2.24 | 2.82 | 3.49 | 5.50 | 0.456 | 93.2 MB | 0.0% |
| `go-gin-gorm` | 900 | 2.07 | 2.68 | 3.60 | 4.46 | 0.940 | 35.2 MB | 0.0% |
| `rust-actix` | 900 | 1.50 | 2.08 | 2.54 | 2.99 | 0.226 | 10.6 MB | 0.0% |
| `ts-node-fastify` | 900 | 2.60 | 3.29 | 5.51 | 10.57 | 0.657 | 243.1 MB | 0.0% |

## checkout — saturated, 64 connections

| stack | req/s | p50 | p90 | p99 | p99.9 | CPU ms/call | peak RSS | CV |
|---|--:|--:|--:|--:|--:|--:|--:|--:|
| `go-fiber` | 1,597 | 39.57 | 45.33 | 51.84 | 58.83 | 0.736 | 22.3 MB | 3.3% |
| `go-nethttp` | 1,572 | 40.07 | 46.08 | 55.71 | 70.37 | 0.804 | 22.8 MB | 3.8% |
| `go-gin` | 1,495 | 42.34 | 50.45 | 62.00 | 68.00 | 0.828 | 31.4 MB | 4.9% |
| `rust-hyper` | 1,438 | 43.71 | 51.27 | 59.38 | 66.29 | 0.582 | 7.8 MB | 8.5% |
| `rust-actix` | 1,382 | 45.38 | 53.59 | 62.43 | 71.50 | 0.749 | 9.4 MB | 1.4% |
| `rust-axum` | 1,366 | 45.99 | 54.24 | 63.53 | 71.92 | 0.612 | 8.1 MB | 14.7% |
| `ts-bun-only` | 1,048 | 59.93 | 70.96 | 83.32 | 92.48 | 0.884 | 82.4 MB | 6.8% |
| `ts-bun-hono` | 786 | 79.79 | 94.89 | 110.76 | 126.03 | 1.154 | 91.8 MB | 9.9% |
| `ts-node-fastify` | 615 | 101.98 | 121.39 | 143.63 | 163.73 | 1.517 | 236.8 MB | 9.2% |
| `go-gin-gorm` | 565 | 90.42 | 209.36 | 389.05 | 593.69 | 2.866 | 34.8 MB | 7.6% |

## checkout — fixed 300 req/s offered

| stack | req/s | p50 | p90 | p99 | p99.9 | CPU ms/call | peak RSS | CV |
|---|--:|--:|--:|--:|--:|--:|--:|--:|
| `go-fiber` | 300 | 2.43 | 3.11 | 3.82 | 4.69 | 0.563 | 21.7 MB | 0.0% |
| `rust-axum` | 300 | 2.75 | 3.78 | 4.86 | 5.76 | 0.383 | 7.9 MB | 0.0% |
| `go-gin` | 300 | 2.50 | 3.18 | 3.76 | 4.25 | 0.630 | 29.8 MB | 0.0% |
| `go-nethttp` | 300 | 2.39 | 3.06 | 3.74 | 4.35 | 0.593 | 21.3 MB | 0.0% |
| `ts-bun-only` | 300 | 2.88 | 3.95 | 4.99 | 5.71 | 0.860 | 77.7 MB | 0.0% |
| `rust-hyper` | 300 | 2.80 | 3.77 | 4.64 | 5.23 | 0.383 | 7.7 MB | 0.0% |
| `rust-actix` | 300 | 2.93 | 4.04 | 5.07 | 6.16 | 0.487 | 9.2 MB | 0.0% |
| `ts-bun-hono` | 300 | 4.36 | 5.99 | 7.60 | 11.71 | 0.977 | 91.6 MB | 0.0% |
| `ts-node-fastify` | 300 | 4.68 | 6.42 | 7.91 | 9.89 | 1.133 | 236.4 MB | 0.0% |
| `go-gin-gorm` | 300 | 8.37 | 10.37 | 12.28 | 14.82 | 2.797 | 32.2 MB | 0.0% |

## checkout — fixed 900 req/s offered

| stack | req/s | p50 | p90 | p99 | p99.9 | CPU ms/call | peak RSS | CV |
|---|--:|--:|--:|--:|--:|--:|--:|--:|
| `go-fiber` | 900 | 2.72 | 3.59 | 5.03 | 7.15 | 0.624 | 23.9 MB | 0.0% |
| `go-nethttp` | 900 | 2.95 | 3.97 | 5.26 | 7.12 | 0.737 | 24.0 MB | 0.0% |
| `go-gin` | 900 | 2.95 | 3.95 | 5.50 | 12.39 | 0.737 | 32.5 MB | 0.0% |
| `rust-actix` | 900 | 3.54 | 5.06 | 6.72 | 8.44 | 0.642 | 11.2 MB | 0.0% |
| `rust-hyper` | 900 | 4.33 | 7.07 | 10.99 | 15.21 | 0.560 | 9.3 MB | 0.0% |
| `ts-bun-only` | 900 | 4.82 | 7.14 | 12.57 | 17.61 | 0.962 | 84.7 MB | 2.0% |
| `rust-axum` | 900 | 3.08 | 4.44 | 5.72 | 7.34 | 0.461 | 10.2 MB | 10.5% |
| `ts-bun-hono` | 827 | 521.08 | 829.11 | 886.81 | 900.61 | 1.137 | 93.8 MB | 2.1% |
| `ts-node-fastify` | 686 | 1,684.24 | 2,889.85 | 3,105.49 | 3,126.72 | 1.390 | 239.9 MB | 11.8% |
| `go-gin-gorm` | 560 | 3,235.02 | 5,528.72 | 6,092.09 | 6,307.92 | 2.887 | 38.8 MB | 8.3% |

## summary — saturated, 64 connections

| stack | req/s | p50 | p90 | p99 | p99.9 | CPU ms/call | peak RSS | CV |
|---|--:|--:|--:|--:|--:|--:|--:|--:|
| `rust-axum` | 5,474 | 11.53 | 13.27 | 15.67 | 22.24 | 0.162 | 7.3 MB | 8.9% |
| `go-fiber` | 5,313 | 11.85 | 13.69 | 16.07 | 18.08 | 0.218 | 20.8 MB | 8.3% |
| `rust-hyper` | 5,268 | 11.94 | 14.01 | 16.47 | 18.78 | 0.157 | 7.1 MB | 6.8% |
| `rust-actix` | 5,257 | 11.72 | 14.33 | 16.99 | 19.30 | 0.199 | 8.3 MB | 5.5% |
| `go-gin` | 5,127 | 12.26 | 14.26 | 17.06 | 19.66 | 0.255 | 29.9 MB | 5.6% |
| `go-nethttp` | 5,031 | 12.44 | 14.70 | 17.36 | 20.43 | 0.257 | 21.7 MB | 9.4% |
| `ts-bun-only` | 3,699 | 16.90 | 19.65 | 22.88 | 24.64 | 0.235 | 71.4 MB | 4.4% |
| `go-gin-gorm` | 3,203 | 18.99 | 28.34 | 39.97 | 48.10 | 0.705 | 34.6 MB | 13.9% |
| `ts-bun-hono` | 2,913 | 21.74 | 25.33 | 29.32 | 33.36 | 0.312 | 75.6 MB | 6.7% |
| `ts-node-fastify` | 2,286 | 27.37 | 32.37 | 37.47 | 46.17 | 0.428 | 240.9 MB | 6.1% |

## summary — fixed 300 req/s offered

| stack | req/s | p50 | p90 | p99 | p99.9 | CPU ms/call | peak RSS | CV |
|---|--:|--:|--:|--:|--:|--:|--:|--:|
| `go-fiber` | 300 | 1.48 | 1.93 | 2.21 | 3.10 | 0.260 | 20.6 MB | 0.0% |
| `rust-hyper` | 300 | 1.58 | 2.03 | 2.41 | 2.66 | 0.120 | 6.9 MB | 0.0% |
| `go-nethttp` | 300 | 1.50 | 1.96 | 2.40 | 2.78 | 0.310 | 21.0 MB | 0.0% |
| `go-gin` | 300 | 1.58 | 2.11 | 3.03 | 3.41 | 0.343 | 29.2 MB | 0.0% |
| `rust-axum` | 300 | 1.57 | 2.08 | 2.50 | 2.81 | 0.143 | 7.3 MB | 0.0% |
| `ts-bun-only` | 300 | 1.55 | 2.01 | 2.49 | 3.34 | 0.337 | 71.3 MB | 0.0% |
| `rust-actix` | 300 | 1.76 | 2.24 | 2.67 | 3.11 | 0.193 | 8.2 MB | 0.0% |
| `go-gin-gorm` | 300 | 1.80 | 2.28 | 2.63 | 3.11 | 0.637 | 31.8 MB | 0.0% |
| `ts-bun-hono` | 300 | 1.96 | 2.43 | 2.75 | 3.44 | 0.320 | 75.8 MB | 0.0% |
| `ts-node-fastify` | 300 | 2.05 | 2.67 | 3.20 | 3.97 | 0.423 | 211.2 MB | 0.0% |

## summary — fixed 900 req/s offered

| stack | req/s | p50 | p90 | p99 | p99.9 | CPU ms/call | peak RSS | CV |
|---|--:|--:|--:|--:|--:|--:|--:|--:|
| `ts-bun-only` | 900 | 1.34 | 1.84 | 2.16 | 3.67 | 0.299 | 70.3 MB | 0.0% |
| `go-gin` | 900 | 1.20 | 1.69 | 1.98 | 2.34 | 0.238 | 32.2 MB | 0.0% |
| `go-nethttp` | 900 | 1.20 | 1.67 | 1.97 | 2.29 | 0.237 | 24.0 MB | 0.0% |
| `ts-bun-hono` | 900 | 1.58 | 2.18 | 2.99 | 8.34 | 0.274 | 77.7 MB | 0.1% |
| `go-fiber` | 900 | 1.21 | 1.70 | 2.05 | 2.52 | 0.206 | 22.8 MB | 0.0% |
| `rust-actix` | 900 | 1.26 | 1.78 | 2.14 | 2.45 | 0.138 | 9.8 MB | 0.0% |
| `go-gin-gorm` | 900 | 1.58 | 2.18 | 2.71 | 3.27 | 0.611 | 34.5 MB | 0.0% |
| `rust-axum` | 900 | 1.25 | 1.74 | 2.06 | 2.46 | 0.103 | 9.1 MB | 0.0% |
| `ts-node-fastify` | 900 | 1.68 | 2.21 | 2.60 | 3.87 | 0.340 | 229.8 MB | 0.0% |
| `rust-hyper` | 900 | 1.27 | 1.77 | 2.09 | 2.93 | 0.103 | 8.5 MB | 0.0% |

## Planned contrasts

| contrast | question | ratio | 95% CI | p (Holm) | significant |
|---|---|--:|--:|--:|:-:|
| `ts-bun-only` vs `ts-node-fastify` | Bun vs Node, both TypeScript | 1.72x | 1.51–1.83 | 1.7e-05 | yes |
| `go-gin` vs `go-gin-gorm` | Cost of the ORM, router held constant | 1.84x | 1.54–2.56 | 1.7e-05 | yes |
| `ts-bun-only` vs `ts-bun-hono` | Zero-dependency Bun vs Hono + node-postgres | 1.33x | 1.18–1.42 | 2.2e-05 | yes |
| `rust-axum` vs `ts-bun-only` | Best Rust vs best TypeScript | 1.45x | 1.30–1.64 | 4.7e-05 | yes |
| `rust-axum` vs `go-fiber` | Best Rust vs best Go | 0.99x | 0.86–1.07 | 7.1e-01 | no |

## Friedman / Nemenyi average ranks


**p99 latency (ms)** — chi-square 56.7, p 5.81e-09, N=9 tasks, critical difference 4.52

| stack | average rank |
|---|--:|
| `go-nethttp` | 2.56 |
| `go-fiber` | 2.67 |
| `rust-axum` | 3.56 |
| `rust-hyper` | 4.22 |
| `go-gin` | 4.44 |
| `rust-actix` | 5.00 |
| `ts-bun-only` | 6.00 |
| `ts-bun-hono` | 8.44 |
| `go-gin-gorm` | 8.89 |
| `ts-node-fastify` | 9.22 |

**CPU ms per request** — chi-square 77.4, p 5.19e-13, N=9 tasks, critical difference 4.52

| stack | average rank |
|---|--:|
| `rust-hyper` | 1.22 |
| `rust-axum` | 1.78 |
| `rust-actix` | 3.22 |
| `go-fiber` | 3.89 |
| `go-nethttp` | 5.39 |
| `go-gin` | 6.39 |
| `ts-bun-only` | 6.44 |
| `ts-bun-hono` | 7.67 |
| `ts-node-fastify` | 9.00 |
| `go-gin-gorm` | 10.00 |

**peak RSS (MB)** — chi-square 80.6, p 1.25e-13, N=9 tasks, critical difference 4.52

| stack | average rank |
|---|--:|
| `rust-hyper` | 1.00 |
| `rust-axum` | 2.00 |
| `rust-actix` | 3.00 |
| `go-fiber` | 4.33 |
| `go-nethttp` | 4.67 |
| `go-gin` | 6.00 |
| `go-gin-gorm` | 7.00 |
| `ts-bun-only` | 8.00 |
| `ts-bun-hono` | 9.00 |
| `ts-node-fastify` | 10.00 |
