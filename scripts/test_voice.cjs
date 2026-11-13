/**
 * Unit tests for the voice capture primitives (no browser needed).
 * Run: node scripts/test_voice.cjs
 */
const path = require("path");

// Minimal DOM-free shims so we can import the pure logic from voice.js.
globalThis.window = { location: { protocol: "http:", host: "localhost:5174" } };
globalThis.navigator = { mediaDevices: undefined };

async function main() {
  // Import the module (it only touches window/navigator inside functions).
  const mod = await import(
    "file://" + path.join(__dirname, "..", "frontend", "src", "lib", "voice.js").replace(/\\/g, "/")
  );
  const { Pcm16Downsampler, toInt16 } = mod;

  let failures = 0;
  const check = (name, cond, detail = "") => {
    if (cond) {
      console.log(`PASS  ${name}${detail ? "  (" + detail + ")" : ""}`);
    } else {
      console.log(`FAIL  ${name}  ${detail}`);
      failures++;
    }
  };

  /* ---- 1. 48 kHz -> 16 kHz decimation: count ratio ---- */
  const SRC = 48000;
  const DST = 16000;
  const ds = new Pcm16Downsampler(SRC, DST);
  const input = new Float32Array(SRC); // exactly 1 second
  for (let i = 0; i < SRC; i++) input[i] = Math.sin((2 * Math.PI * 440 * i) / SRC);
  const out = ds.process(input);
  check(
    "48k->16k produces 16000 samples per second of input",
    out.length === 16000,
    `got ${out.length}, expected 16000`
  );

  /* ---- 2. amplitude is preserved (box filter, not naive copy) ---- */
  let peak = 0;
  for (const s of out) peak = Math.max(peak, Math.abs(s));
  check(
    "440Hz tone keeps its amplitude through decimation",
    peak > 0.95 && peak <= 1.0,
    `peak=${peak.toFixed(4)} (source peak 1.0)`
  );

  /* ---- 3. the frequency survives (count zero crossings) ---- */
  let crossings = 0;
  for (let i = 1; i < out.length; i++) {
    if (out[i - 1] < 0 && out[i] >= 0) crossings++;
  }
  check(
    "440Hz tone still measures 440Hz at 16kHz (no 3x slowdown)",
    Math.abs(crossings - 440) <= 2,
    `crossings=${crossings}, expected ~440 (a naive copy would give ~147)`
  );

  /* ---- 4. streaming across chunk boundaries keeps the rate ---- */
  const ds2 = new Pcm16Downsampler(SRC, DST);
  let total = 0;
  for (let c = 0; c < 50; c++) {
    const chunk = new Float32Array(1024);
    for (let i = 0; i < 1024; i++) chunk[i] = Math.sin((2 * Math.PI * 440 * (c * 1024 + i)) / SRC);
    total += ds2.process(chunk).length;
  }
  const expected = Math.floor((50 * 1024 * DST) / SRC);
  check(
    "streaming in 1024-sample chunks keeps the exact output rate",
    Math.abs(total - expected) <= 1,
    `got ${total}, expected ~${expected}`
  );

  /* ---- 5. 44.1 kHz (another common hardware rate) ---- */
  const ds3 = new Pcm16Downsampler(44100, DST);
  const in44 = new Float32Array(44100);
  for (let i = 0; i < 44100; i++) in44[i] = Math.sin((2 * Math.PI * 440 * i) / 44100);
  const out44 = ds3.process(in44);
  check(
    "44.1k->16k produces ~16000 samples",
    Math.abs(out44.length - 16000) <= 1,
    `got ${out44.length}`
  );

  /* ---- 6. Float32 -> Int16 PCM conversion ---- */
  const pcm = toInt16([0, 1, -1, 0.5, -0.5]);
  check(
    "Float32 -> Int16 clamps and scales correctly",
    pcm[0] === 0 &&
      pcm[1] === 32767 &&
      pcm[2] === -32767 &&
      Math.abs(pcm[3] - 16384) <= 1 &&
      Math.abs(pcm[4] + 16384) <= 1,
    `[${Array.from(pcm).join(", ")}]`
  );

  /* ---- 7. silence remains zero-amplitude in PCM conversion ---- */
  const silence = toInt16(new Array(1024).fill(0));
  let sp = 0;
  for (const s of silence) sp = Math.max(sp, Math.abs(s));
  check("all-zero samples stay at zero amplitude", sp === 0, `peak=${sp}`);

  console.log("");
  if (failures === 0) {
    console.log("ALL VOICE UNIT TESTS PASSED");
  } else {
    console.log(`${failures} TEST(S) FAILED`);
    process.exitCode = 1;
  }
}

main();
