const canvas = document.getElementById("game");
const ctx = canvas.getContext("2d");
const overlay = document.getElementById("overlay");
const scoreEl = document.getElementById("score");
const highScoreEl = document.getElementById("highScore");
const stateLabelEl = document.getElementById("stateLabel");
const hintLabelEl = document.getElementById("hintLabel");

const STORAGE_KEY = "desert-debugger-high-score";
const DEBUG_KEY = "desert-debugger-cache";

const CAT_RENDER = {
  frameWidth: 32,
  frameHeight: 30,
  width: 58,
  height: 54,
  idleFrame: 0,
  runFrames: [0, 1, 2, 3],
  frames: [
    { x: 0, y: 0, w: 32, h: 30, duration: 200 },
    { x: 32, y: 0, w: 32, h: 30, duration: 200 },
    { x: 0, y: 30, w: 32, h: 30, duration: 200 },
    { x: 32, y: 0, w: 32, h: 30, duration: 200 },
  ],
};

const catImage = new Image();
catImage.src = "cat.png";

const challengeState = {
  flags: [
    "grey{you_better_run_bruno_cat}",
  ],
  frameChecksum: "bg:7f3a1",
  fastPhaseScore: 2250,
  session: null,
  bootstrapHints: [],
  lastReportTick: -24,
  unlocked: false,
};

const game = {
  width: canvas.width,
  height: canvas.height,
  groundY: 286,
  gravity: 0.82,
  speed: 7,
  maxSpeed: 28,
  running: false,
  gameOver: false,
  started: false,
  tick: 0,
  score: 0,
  highScore: Number(localStorage.getItem(STORAGE_KEY) || 0),
  hintIndex: 0,
  obstacleTimer: 0,
  cloudTimer: 0,
  bgOffset: 0,
  revealCooldown: 0,
  spectralFragments: [],
  clouds: [],
  obstacles: [],
  particles: [],
  player: {
    x: 88,
    y: 0,
    w: 44,
    h: 48,
    vy: 0,
    jumping: false,
    frame: 0,
  },
};

game.player.y = game.groundY - game.player.h;

window.runnerChallenge = {
  state: {
    flags: challengeState.flags,
    frameChecksum: challengeState.frameChecksum,
    fastPhaseScore: challengeState.fastPhaseScore,
  },
  inspectBackground(index) {
    return game.spectralFragments[index] || null;
  },
  checksum() {
    return `${challengeState.frameChecksum}:${game.tick}`;
  },
  telemetry() {
    return game.spectralFragments.map((fragment) => ({
      text: fragment.text,
      seenAtScore: fragment.seenAtScore,
      speed: Number(fragment.speed.toFixed(2)),
    }));
  },
  async replay(view = "summary") {
    const response = await fetch(`/api/replay?view=${encodeURIComponent(view)}`, {
      cache: "no-store",
    });
    return response.json();
  },
};

function decodeStamp(stamp, traceId) {
  try {
    const encoded = atob(stamp);
    const parts = String(traceId || "").split("-");
    const seed = parts.length >= 3 ? parts[1] : "";
    const index = Number(parts.length >= 3 ? parts[2] : 0) - 1;
    const keyBase = seed.split("").reduce((sum, ch) => sum + ch.charCodeAt(0), 0) + Math.max(0, index) * 17;
    let output = "";

    for (let i = 0; i < encoded.length; i += 1) {
      const code = encoded.charCodeAt(i) ^ ((keyBase + i * 13) & 0xff);
      output += String.fromCharCode(code);
    }

    return output;
  } catch (error) {
    return null;
  }
}

localStorage.setItem(
  DEBUG_KEY,
  JSON.stringify({
    skylineNoise: [
      "scanline",
      "packet",
      "replay",
      "fragment:transit_",
      "grey{never_back_down_never_WHAT}",
    ],
    checksum: challengeState.frameChecksum,
  }),
);

function isFastPhase() {
  return Math.floor(game.score) >= challengeState.fastPhaseScore;
}

async function bootstrapChallenge() {
  try {
    const response = await fetch("/api/bootstrap", { cache: "no-store" });
    const data = await response.json();
    challengeState.fastPhaseScore = data.fastPhaseScore || challengeState.fastPhaseScore;
    challengeState.session = data.session || null;
    challengeState.bootstrapHints = data.hints || [];
    window.runnerChallenge.state.fastPhaseScore = challengeState.fastPhaseScore;
    window.runnerChallenge.state.session = challengeState.session;
  } catch (error) {
    console.error("bootstrap failed", error);
  }
}

async function revealFlagFragment() {
  try {
    const lane = game.spectralFragments.length % 2;
    const response = await fetch(
      `/api/ghost?score=${encodeURIComponent(Math.floor(game.score))}&lane=${lane}`,
      {
        cache: "no-store",
        headers: {
          "X-Runner-Debug": "trace",
        },
      },
    );
    const payload = await response.json();
    if (!payload.stamp) {
      return;
    }

    const resolvedText = decodeStamp(payload.stamp, payload.traceId);
    if (!resolvedText) {
      return;
    }

    game.spectralFragments.push({
      text: resolvedText,
      ttl: payload.ttl || 22,
      x: game.width + 12,
      y: 84 + lane * 26,
      speed: game.speed,
      seenAtScore: Math.floor(game.score),
    });
  } catch (error) {
    console.error("fragment fetch failed", error);
  }
}

async function reportRunProgress(state = "running") {
  try {
    const response = await fetch(
      `/api/run?score=${encodeURIComponent(Math.floor(game.score))}&tick=${encodeURIComponent(game.tick)}&state=${encodeURIComponent(state)}`,
      {
        cache: "no-store",
      },
    );
    const payload = await response.json();
    challengeState.unlocked = Boolean(payload.unlocked);
  } catch (error) {
    console.error("run report failed", error);
  }
}

function updateHud() {
  scoreEl.textContent = String(Math.floor(game.score)).padStart(5, "0");
  highScoreEl.textContent = String(Math.floor(game.highScore)).padStart(5, "0");
  stateLabelEl.textContent = game.gameOver
    ? "CRASHED"
    : game.running
      ? "RUNNING"
      : game.started
        ? "PAUSED"
        : "IDLE";
  hintLabelEl.textContent = "";
}

function resetGame() {
  game.running = false;
  game.gameOver = false;
  game.started = false;
  game.tick = 0;
  game.score = 0;
  game.speed = 7;
  game.obstacleTimer = 0;
  game.cloudTimer = 0;
  game.bgOffset = 0;
  game.revealCooldown = 0;
  challengeState.lastReportTick = -24;
  challengeState.unlocked = false;
  game.spectralFragments = [];
  game.clouds = [];
  game.obstacles = [];
  game.particles = [];
  game.player = {
    x: 88,
    y: game.groundY - 48,
    w: 44,
    h: 48,
    vy: 0,
    jumping: false,
    frame: 0,
  };
  overlay.classList.remove("hidden");
  overlay.querySelector(".overlay-title").textContent = "Press space to run";
  overlay.querySelector(".overlay-subtitle").textContent = "";
  updateHud();
}

function spawnCloud() {
  const altitude = 36 + Math.random() * 96;
  const speed = 0.35 + Math.random() * 0.45;
  const width = 56 + Math.random() * 80;
  game.clouds.push({
    x: game.width + width,
    y: altitude,
    w: width,
    h: 22 + Math.random() * 16,
    speed,
    opacity: 0.08 + Math.random() * 0.06,
  });
}

function spawnObstacle() {
  const tall = Math.random() > 0.45;
  const kind = tall ? "cactus" : "crate";
  const w = tall ? 26 + Math.random() * 10 : 34 + Math.random() * 14;
  const h = tall ? 46 + Math.random() * 22 : 24 + Math.random() * 14;
  game.obstacles.push({
    kind,
    x: game.width + w,
    y: game.groundY - h,
    w,
    h,
    tag: challengeState.flags[Math.floor(Math.random() * challengeState.flags.length)],
  });
}

function startRun() {
  if (game.gameOver) {
    resetGame();
  }
  game.running = true;
  game.started = true;
  overlay.classList.add("hidden");
  reportRunProgress("running");
}

function jump() {
  if (!game.started) {
    startRun();
  }
  if (!game.running || game.player.jumping) {
    return;
  }
  game.player.vy = -13.7;
  game.player.jumping = true;
}

function createDust(x, y) {
  game.particles.push({
    x,
    y,
    vx: -1 - Math.random() * 2,
    vy: -0.4 - Math.random(),
    life: 18 + Math.random() * 18,
  });
}

function intersects(a, b) {
  return a.x < b.x + b.w && a.x + a.w > b.x && a.y < b.y + b.h && a.y + a.h > b.y;
}

function update() {
  if (!game.running || game.gameOver) {
    updateHud();
    return;
  }

  game.tick += 1;
  game.score += 0.24 * game.speed;
  game.speed = Math.min(game.maxSpeed, 7 + game.score / 180);
  game.bgOffset += game.speed * 0.25;

  if (game.tick - challengeState.lastReportTick >= 24) {
    challengeState.lastReportTick = game.tick;
    reportRunProgress("running");
  }

  const playerHeight = 48;
  game.player.h = playerHeight;
  game.player.w = 44;
  game.player.y += game.player.vy;
  game.player.vy += game.gravity;

  if (game.player.y >= game.groundY - playerHeight) {
    if (game.player.jumping) {
      for (let i = 0; i < 8; i += 1) {
        createDust(game.player.x + 14, game.groundY - 2);
      }
    }
    game.player.y = game.groundY - playerHeight;
    game.player.vy = 0;
    game.player.jumping = false;
  }

  game.obstacleTimer -= 1;
  if (game.obstacleTimer <= 0) {
    spawnObstacle();
    game.obstacleTimer = 48 + Math.random() * 68 - Math.min(22, game.score / 22);
  }

  game.cloudTimer -= 1;
  if (game.cloudTimer <= 0) {
    spawnCloud();
    game.cloudTimer = 65 + Math.random() * 115;
  }

  if (isFastPhase()) {
    game.revealCooldown -= 1;
    if (game.revealCooldown <= 0) {
      revealFlagFragment();
      game.revealCooldown = Math.max(8, 22 - Math.floor((game.speed - 19.5) * 1.5));
    }
  }

  for (const cloud of game.clouds) {
    cloud.x -= cloud.speed + game.speed * 0.18;
  }
  game.clouds = game.clouds.filter((cloud) => cloud.x + cloud.w > -80);

  for (const obstacle of game.obstacles) {
    obstacle.x -= game.speed;
  }
  game.obstacles = game.obstacles.filter((obstacle) => obstacle.x + obstacle.w > -50);

  for (const particle of game.particles) {
    particle.x += particle.vx;
    particle.y += particle.vy;
    particle.life -= 1;
  }
  game.particles = game.particles.filter((particle) => particle.life > 0);

  for (const fragment of game.spectralFragments) {
    fragment.x -= game.speed * 1.28;
    fragment.ttl -= 1;
  }
  game.spectralFragments = game.spectralFragments.filter(
    (fragment) => fragment.ttl > 0 && fragment.x > -180,
  );

  for (const obstacle of game.obstacles) {
    const hitbox = {
      x: game.player.x + 6,
      y: game.player.y + 6,
      w: game.player.w - 12,
      h: game.player.h - 8,
    };
    if (intersects(hitbox, obstacle)) {
      game.gameOver = true;
      game.running = false;
      reportRunProgress("crashed");
      game.highScore = Math.max(game.highScore, Math.floor(game.score));
      localStorage.setItem(STORAGE_KEY, String(game.highScore));
      overlay.classList.remove("hidden");
      overlay.querySelector(".overlay-title").textContent = "Oh no :(";
      overlay.querySelector(".overlay-subtitle").textContent = "Press R to rerun.";
      break;
    }
  }

  if (Math.floor(game.score) > game.highScore) {
    game.highScore = Math.floor(game.score);
    localStorage.setItem(STORAGE_KEY, String(game.highScore));
  }

  updateHud();
}

function drawSky() {
  const sky = ctx.createLinearGradient(0, 0, 0, game.height);
  sky.addColorStop(0, "#fbfbfb");
  sky.addColorStop(0.5, "#e4e6e8");
  sky.addColorStop(1, "#bcc3c8");
  ctx.fillStyle = sky;
  ctx.fillRect(0, 0, game.width, game.height);

  for (let i = 0; i < 5; i += 1) {
    const ridgeX = ((i * 240) - (game.bgOffset * (0.25 + i * 0.03))) % (game.width + 320) - 160;
    ctx.fillStyle = i % 2 === 0 ? "rgba(34, 39, 42, 0.12)" : "rgba(95, 104, 110, 0.1)";
    ctx.beginPath();
    ctx.moveTo(ridgeX, game.groundY);
    ctx.quadraticCurveTo(ridgeX + 110, 190 - i * 8, ridgeX + 220, game.groundY);
    ctx.closePath();
    ctx.fill();
  }

  const sunX = 760 - (game.bgOffset * 0.08) % 1000;
  ctx.fillStyle = "rgba(196, 255, 213, 0.42)";
  ctx.beginPath();
  ctx.arc(sunX, 78, 28, 0, Math.PI * 2);
  ctx.fill();
}

function drawCloud(cloud, index) {
  ctx.save();
  ctx.globalAlpha = 0.85;
  ctx.fillStyle = `rgba(252, 252, 252, ${0.72 + cloud.opacity})`;
  ctx.beginPath();
  ctx.ellipse(cloud.x, cloud.y + 10, cloud.w * 0.24, cloud.h * 0.45, 0, 0, Math.PI * 2);
  ctx.ellipse(cloud.x + cloud.w * 0.22, cloud.y, cloud.w * 0.2, cloud.h * 0.42, 0, 0, Math.PI * 2);
  ctx.ellipse(cloud.x + cloud.w * 0.46, cloud.y + 8, cloud.w * 0.26, cloud.h * 0.52, 0, 0, Math.PI * 2);
  ctx.fill();

  if (index % 3 === 0) {
    ctx.font = "8px monospace";
    ctx.fillStyle = `rgba(27, 27, 27, ${cloud.opacity * 0.55})`;
    ctx.fillText(challengeState.frameChecksum, cloud.x + 8, cloud.y + 5);
  }
  ctx.restore();
}

function drawGround() {
  ctx.fillStyle = "#2a2f32";
  ctx.fillRect(0, game.groundY + 18, game.width, game.height - game.groundY);

  ctx.strokeStyle = "rgba(8, 12, 10, 0.44)";
  ctx.lineWidth = 2;
  ctx.beginPath();
  ctx.moveTo(0, game.groundY + 0.5);
  for (let x = 0; x <= game.width; x += 24) {
    const wobble = Math.sin((x + game.bgOffset) * 0.024) * 2.4;
    ctx.lineTo(x, game.groundY + wobble);
  }
  ctx.stroke();

  ctx.fillStyle = "rgba(158, 245, 181, 0.32)";
  for (let x = -40; x < game.width + 40; x += 64) {
    const drift = (x - (game.bgOffset * 1.3)) % (game.width + 64);
    ctx.fillRect(drift, game.groundY + 12, 18, 3);
  }
}

function drawPlayer() {
  const p = game.player;
  const runCycle = Math.floor(game.tick / Math.max(4, 9 - game.speed * 0.18)) % CAT_RENDER.runFrames.length;
  const frameIndex = game.running
    ? CAT_RENDER.runFrames[runCycle]
    : CAT_RENDER.idleFrame;
  const frame = CAT_RENDER.frames[frameIndex];
  const bob = game.running ? Math.sin(game.tick * 0.7) * 1.4 : 0;
  const sway = game.running ? Math.sin(game.tick * 0.35) * 1.2 : 0;
  const x = p.x - 8 + sway;
  const y = p.y - 8 + bob;

  if (!catImage.complete) {
    ctx.fillStyle = "#111111";
    ctx.fillRect(p.x + 6, p.y + 6, p.w - 12, p.h - 8);
    return;
  }

  ctx.save();
  ctx.imageSmoothingEnabled = false;
  ctx.drawImage(
    catImage,
    frame.x,
    frame.y,
    frame.w,
    frame.h,
    x,
    y,
    CAT_RENDER.width,
    CAT_RENDER.height,
  );
  ctx.restore();
}

function drawObstacle(obstacle) {
  ctx.save();
  ctx.translate(obstacle.x, obstacle.y);
  ctx.fillStyle = "#2f8f4f";

  if (obstacle.kind === "cactus") {
    ctx.fillRect(10, 0, 10, obstacle.h);
    ctx.fillRect(0, 12, 9, 8);
    ctx.fillRect(18, 18, 8, 8);
    ctx.fillRect(2, 12, 4, 18);
    ctx.fillRect(20, 18, 4, 16);
  } else {
    ctx.fillStyle = "#3d4348";
    ctx.fillRect(0, 8, obstacle.w, obstacle.h - 8);
    ctx.fillStyle = "#8b9299";
    ctx.fillRect(4, 12, obstacle.w - 8, obstacle.h - 16);
  }

  ctx.fillStyle = "rgba(255,255,255,0.035)";
  ctx.font = "8px monospace";
  ctx.fillText(obstacle.tag, 1, -4);
  ctx.restore();
}

function drawParticles() {
  for (const particle of game.particles) {
    ctx.fillStyle = `rgba(213, 255, 225, ${particle.life / 36})`;
    ctx.fillRect(particle.x, particle.y, 3, 3);
  }
}

function drawSpectralFragments() {
  ctx.save();
  ctx.font = "12px monospace";
  for (const fragment of game.spectralFragments) {
    const alpha = Math.min(0.18, fragment.ttl / 140);
    ctx.fillStyle = `rgba(6, 38, 18, ${alpha})`;
    ctx.fillText(fragment.text, fragment.x, fragment.y);
  }
  ctx.restore();
}

function render() {
  drawSky();
  game.clouds.forEach(drawCloud);
  drawSpectralFragments();
  drawGround();
  game.obstacles.forEach(drawObstacle);
  drawParticles();
  drawPlayer();
}

function loop() {
  update();
  render();
  requestAnimationFrame(loop);
}

window.addEventListener("keydown", (event) => {
  if (event.code === "Space" || event.code === "ArrowUp") {
    event.preventDefault();
    if (!game.running && !game.gameOver) {
      startRun();
    }
    jump();
  } else if (event.key.toLowerCase() === "r") {
    resetGame();
  }
});

resetGame();
updateHud();
bootstrapChallenge();
loop();
