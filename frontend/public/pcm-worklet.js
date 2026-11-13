/**
 * AudioWorklet capture node for ASHA SWAR NIRANTAR.
 *
 * Served verbatim from `public/` so it is loaded as a classic worker script
 * (Vite would otherwise transform it into an ES module, which
 * `audioWorklet.addModule()` cannot load).
 *
 * The node:
 *   - receives the microphone's Float32 samples at the hardware rate
 *   - box-filters them down to 16 kHz mono (Gnani Prisma's expected format)
 *   - converts to 16-bit PCM
 *   - posts the Int16 frame plus the RMS level back to the main thread
 *
 * `createScriptProcessor` is deprecated and can silently deliver zeros for a
 * MediaStream source, which made every recording look empty. AudioWorklet
 * runs on the audio thread and is reliable.
 */
class PcmCaptureProcessor extends AudioWorkletProcessor {
  constructor(options) {
    super();
    const opts = (options && options.processorOptions) || {};
    this.targetRate = opts.targetSampleRate || 16000;
    this.sum = 0;
    this.count = 0;
    this.carry = 0;
    this.rmsSum = 0;
    this.rmsCount = 0;
  }

  process(inputs) {
    const channel = inputs[0] && inputs[0][0];
    if (!channel || channel.length === 0) return true;

    // RMS for the level meter.
    let sq = 0;
    for (let i = 0; i < channel.length; i++) sq += channel[i] * channel[i];
    this.rmsSum += sq;
    this.rmsCount += channel.length;

    // Box-filter downsample to the target rate.
    const out = [];
    for (let i = 0; i < channel.length; i++) {
      this.sum += channel[i];
      this.count += 1;
      this.carry += this.targetRate;
      if (this.carry >= sampleRate) {
        this.carry -= sampleRate;
        out.push(this.sum / this.count);
        this.sum = 0;
        this.count = 0;
      }
    }

    if (out.length > 0) {
      const pcm = new Int16Array(out.length);
      for (let i = 0; i < out.length; i++) {
        const v = out[i] < -1 ? -1 : out[i] > 1 ? 1 : out[i];
        pcm[i] = Math.round(v * 32767);
      }
      const rms = Math.sqrt(this.rmsSum / Math.max(1, this.rmsCount));
      this.rmsSum = 0;
      this.rmsCount = 0;
      this.port.postMessage({ pcm: pcm.buffer, rms: rms }, [pcm.buffer]);
    }
    return true;
  }
}

registerProcessor("pcm-capture", PcmCaptureProcessor);
