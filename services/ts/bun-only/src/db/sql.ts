/**
 * Postgres through Bun's built-in SQL client. No npm driver: `Bun.sql` speaks
 * the wire protocol itself, so this service installs nothing.
 */
import { SQL } from "bun";

export const sql = new SQL({
  url: Bun.env.DATABASE_URL!,
  max: Number(Bun.env.DB_POOL_SIZE ?? 20),
  idleTimeout: 0,
  bigint: false,
});

/** Postgres hands back int8 and numeric as strings; ids here are far below 2^53. */
export const n = (v: unknown): number => typeof v === "number" ? v : Number(v);

export const day = (v: unknown): string =>
  v instanceof Date ? v.toISOString().slice(0, 10) : String(v).slice(0, 10);

export class NotFound extends Error { constructor() { super("not_found"); } }
export class StockError extends Error {
  sku: string;
  constructor(sku: string) { super("insufficient_stock"); this.sku = sku; }
}
