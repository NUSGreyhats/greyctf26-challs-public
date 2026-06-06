import { spawn } from "node:child_process";
import { resolve } from "node:path";

const DEFAULT_CHUNK_SIZE = 160;

export async function attachVideoFrameImages(events, options = {}) {
  const videoPath = options.videoPath ? resolve(options.videoPath) : "";
  if (!videoPath) {
    return {
      events,
      videoSource: null,
    };
  }

  const videoEvents = events.filter((event) => event.message?.type === "video_frame");
  if (videoEvents.length === 0) {
    return {
      events,
      videoSource: null,
    };
  }

  const metadata = await probeVideo(videoPath);
  const frameRefs = videoEvents.map((event) => ({
    event,
    frameIndex: sourceFrameIndex(event.message.sourceAtMs, {
      fps: metadata.fps,
      cropStartMs: options.videoCropStartMs,
    }),
  }));
  const frameIndices = [...new Set(frameRefs.map((ref) => ref.frameIndex))]
    .filter((value) => Number.isFinite(value) && value >= 0)
    .sort((left, right) => left - right);
  const extracted = await extractVideoFrames(videoPath, frameIndices, {
    chunkSize: options.videoExtractChunkSize,
  });

  let framesWithImages = 0;
  const hydratedEvents = events.map((event) => {
    if (event.message?.type !== "video_frame") {
      return event;
    }

    const frameIndex = sourceFrameIndex(event.message.sourceAtMs, {
      fps: metadata.fps,
      cropStartMs: options.videoCropStartMs,
    });
    const image = extracted.get(frameIndex) || extracted.get(nearestFrameIndex(frameIndices, frameIndex));
    if (!image) {
      return event;
    }

    framesWithImages += 1;
    return {
      ...event,
      message: {
        ...event.message,
        image: stampJpegDataUrl(image, {
          clientId: options.clientId ?? 0,
          sequence: event.message.sequence ?? framesWithImages,
        }),
      },
    };
  });

  return {
    events: hydratedEvents,
    videoSource: {
      path: videoPath,
      cropStartMs: positiveNumber(options.videoCropStartMs) ?? 0,
      fps: metadata.fps,
      width: metadata.width,
      height: metadata.height,
      sourceFrames: extracted.size,
      framesWithImages,
    },
  };
}

async function probeVideo(videoPath) {
  const output = await runProcess("ffprobe", [
    "-v",
    "error",
    "-select_streams",
    "v:0",
    "-show_entries",
    "stream=avg_frame_rate,r_frame_rate,width,height",
    "-of",
    "json",
    videoPath,
  ]);
  const parsed = JSON.parse(output.toString("utf8"));
  const stream = parsed.streams?.[0] || {};
  const fps = parseRate(stream.avg_frame_rate) || parseRate(stream.r_frame_rate);
  if (!Number.isFinite(fps) || fps <= 0) {
    throw new Error(`Could not determine video frame rate for ${videoPath}`);
  }
  return {
    fps,
    width: Number(stream.width) || null,
    height: Number(stream.height) || null,
  };
}

async function extractVideoFrames(videoPath, frameIndices, options = {}) {
  const images = new Map();
  const chunkSize = positiveNumber(options.chunkSize) ?? DEFAULT_CHUNK_SIZE;
  for (let start = 0; start < frameIndices.length; start += chunkSize) {
    const chunk = frameIndices.slice(start, start + chunkSize);
    const filter = `select=${chunk.map((index) => `eq(n\\,${index})`).join("+")},scale=480:-2`;
    const output = await runProcess("ffmpeg", [
      "-v",
      "error",
      "-i",
      videoPath,
      "-vf",
      filter,
      "-vsync",
      "0",
      "-f",
      "image2pipe",
      "-vcodec",
      "mjpeg",
      "-q:v",
      "3",
      "pipe:1",
    ]);
    const dataUrls = splitJpegs(output).map(
      (bytes) => `data:image/jpeg;base64,${bytes.toString("base64")}`,
    );
    for (let index = 0; index < dataUrls.length && index < chunk.length; index += 1) {
      images.set(chunk[index], dataUrls[index]);
    }
  }
  return images;
}

function sourceFrameIndex(sourceAtMs, { fps, cropStartMs }) {
  const sourceMs = (positiveNumber(cropStartMs) ?? 0) + (Number(sourceAtMs) || 0);
  return Math.max(0, Math.round((sourceMs / 1000) * fps));
}

function nearestFrameIndex(indices, target) {
  let best = null;
  let bestDistance = Infinity;
  for (const index of indices) {
    const distance = Math.abs(index - target);
    if (distance < bestDistance) {
      best = index;
      bestDistance = distance;
    }
  }
  return best;
}

function splitJpegs(buffer) {
  const images = [];
  let start = -1;
  for (let index = 0; index < buffer.length - 1; index += 1) {
    if (start < 0 && buffer[index] === 0xff && buffer[index + 1] === 0xd8) {
      start = index;
      index += 1;
      continue;
    }
    if (start >= 0 && buffer[index] === 0xff && buffer[index + 1] === 0xd9) {
      images.push(buffer.subarray(start, index + 2));
      start = -1;
      index += 1;
    }
  }
  return images;
}

function stampJpegDataUrl(dataUrl, { clientId, sequence }) {
  const match = dataUrl.match(/^data:image\/jpe?g;base64,([A-Za-z0-9+/=]+)$/);
  if (!match) {
    return dataUrl;
  }
  const bytes = Buffer.from(match[1], "base64");
  if (bytes.length < 4 || bytes[0] !== 0xff || bytes[1] !== 0xd8) {
    return dataUrl;
  }

  const payload = Buffer.from(`load-test:${clientId}:${sequence}`, "utf8");
  const comment = Buffer.alloc(payload.length + 4);
  comment[0] = 0xff;
  comment[1] = 0xfe;
  comment.writeUInt16BE(payload.length + 2, 2);
  payload.copy(comment, 4);

  const stamped = Buffer.concat([bytes.subarray(0, 2), comment, bytes.subarray(2)]);
  return `data:image/jpeg;base64,${stamped.toString("base64")}`;
}

function parseRate(value) {
  if (typeof value !== "string" || !value || value === "0/0") {
    return null;
  }
  const [numerator, denominator] = value.split("/").map(Number);
  if (Number.isFinite(numerator) && Number.isFinite(denominator) && denominator !== 0) {
    return numerator / denominator;
  }
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function positiveNumber(value) {
  const number = Number(value);
  return Number.isFinite(number) && number > 0 ? number : null;
}

function runProcess(command, args) {
  return new Promise((resolvePromise, reject) => {
    const child = spawn(command, args, {
      stdio: ["ignore", "pipe", "pipe"],
    });
    const stdout = [];
    const stderr = [];
    child.stdout.on("data", (chunk) => stdout.push(chunk));
    child.stderr.on("data", (chunk) => stderr.push(chunk));
    child.on("error", reject);
    child.on("close", (code) => {
      if (code === 0) {
        resolvePromise(Buffer.concat(stdout));
        return;
      }
      reject(
        new Error(
          `${command} exited with code ${code}: ${Buffer.concat(stderr).toString("utf8").trim()}`,
        ),
      );
    });
  });
}
