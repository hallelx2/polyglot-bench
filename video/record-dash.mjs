// Render the scene frame by frame through one Chromium instance and hand the
// frames to ffmpeg. The scene is a pure function of time, so every frame is
// reproducible and the video can be regenerated from the result files.
import { chromium } from "/home/hallelx2/.local/share/mise/installs/npm-playwright/1.63.0/node_modules/.mise/playwright@1.63.0/node_modules/playwright/index.mjs";
import { mkdirSync, rmSync, readFileSync } from "node:fs";
import { execFileSync } from "node:child_process";
import { resolve } from "node:path";

const FPS = Number(process.env.FPS ?? 30);
const OUT = "video/frames2";
rmSync(OUT, { recursive: true, force: true });
mkdirSync(OUT, { recursive: true });

const data = JSON.parse(readFileSync("video/data.json", "utf8"));
const browser = await chromium.launch({
  executablePath: "/usr/bin/chromium",
  args: ["--no-sandbox", "--disable-gpu", "--hide-scrollbars", "--force-color-profile=srgb"],
});
const page = await browser.newPage({ viewport: { width: 1920, height: 1080 } });
await page.addInitScript((d) => { window.__DATA__ = d; }, data);
await page.goto("file://" + resolve("video/dashboard.html"));
await page.waitForFunction(() => document.fonts.status === "loaded" && !!window.renderAt);

const total = Math.round((await page.evaluate(() => window.DURATION)) * FPS);
process.stdout.write(`rendering ${total} frames at ${FPS}fps\n`);
for (let f = 0; f < total; f++) {
  await page.evaluate((t) => window.renderAt(t), f / FPS);
  await page.screenshot({ path: `${OUT}/${String(f).padStart(5, "0")}.png` });
  if (f % 90 === 0) process.stdout.write(`  ${f}/${total}\n`);
}
await browser.close();

execFileSync("ffmpeg", ["-y", "-framerate", String(FPS), "-i", `${OUT}/%05d.png`,
  "-c:v", "libx264", "-preset", "slow", "-crf", "18", "-pix_fmt", "yuv420p",
  "-movflags", "+faststart", "video/polyglot-bench-dashboard.mp4"], { stdio: "inherit" });
execFileSync("ffmpeg", ["-y", "-i", "video/polyglot-bench-dashboard.mp4",
  "-vf", "fps=15,scale=1280:-1:flags=lanczos,split[a][b];[a]palettegen[p];[b][p]paletteuse",
  "video/polyglot-bench-dashboard.gif"], { stdio: "inherit" });
process.stdout.write("done\n");
