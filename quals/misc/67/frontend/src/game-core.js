export const GAME_CONSTANTS = Object.freeze({
  width: 960,
  height: 540,
  birdX: 240,
  birdRadius: 18,
  gravity: 1180,
  flapImpulse: -405,
  pipeSpeed: 255,
  pipeWidth: 74,
  pipeGap: 168,
  pipeInterval: 1.42,
  pipeSpawnX: 1040,
  initialPipeX: 1220,
  pipeSpacing: 362.1,
  floorY: 492,
  winScore: 67,
});

export const WIN_SCORE = GAME_CONSTANTS.winScore;

export function createGameState(overrides = {}, constants = GAME_CONSTANTS) {
  const state = {
    birdY: 230,
    velocity: 0,
    score: 0,
    elapsed: 0,
    spawnTimer: 0,
    gameOver: false,
    awaitingStart: true,
    pipes: [],
    nextPipeId: 1,
    ...overrides,
  };

  if (overrides.pipes) {
    state.pipes = overrides.pipes.map((pipe) => ({ ...pipe }));
  } else {
    seedInitialPipes(state, constants);
  }

  return state;
}

export function cloneGameState(state) {
  return {
    ...state,
    pipes: state.pipes.map((pipe) => ({ ...pipe })),
  };
}

export function seedInitialPipes(state, constants = GAME_CONSTANTS) {
  state.pipes = [];
  state.nextPipeId = 1;
  for (let index = 0; index < 4; index += 1) {
    spawnPipe(state, constants, constants.initialPipeX + index * constants.pipeSpacing);
  }
  return state;
}

export function canSpawnPipe(state, constants = GAME_CONSTANTS) {
  if (state.pipes.length === 0) {
    return true;
  }

  const rightmostPipeX = state.pipes.reduce(
    (rightmostX, pipe) => Math.max(rightmostX, pipe.x),
    -Infinity,
  );
  return rightmostPipeX <= constants.pipeSpawnX - constants.pipeSpacing;
}

export function spawnPipe(state, constants = GAME_CONSTANTS, x = constants.pipeSpawnX) {
  const wave = Math.sin((state.elapsed + state.nextPipeId) * 1.37);
  const jitter = Math.sin(state.elapsed * 2.9 + state.nextPipeId * 6.1) * 58;
  const gapY = clamp(190 + wave * 88 + jitter, 128, constants.floorY - constants.pipeGap - 44);
  state.pipes.push({
    id: state.nextPipeId,
    x,
    gapY,
    scored: false,
  });
  state.nextPipeId += 1;
  return state;
}

export function applyFlap(state, constants = GAME_CONSTANTS) {
  state.awaitingStart = false;
  state.velocity = constants.flapImpulse;
  return state;
}

export function stepGameState(state, dt, constants = GAME_CONSTANTS, options = {}) {
  if (state.gameOver || state.awaitingStart) {
    return state;
  }

  state.elapsed += dt;
  state.velocity += constants.gravity * dt;
  state.birdY += state.velocity * dt;
  state.spawnTimer += dt;

  if (state.spawnTimer >= constants.pipeInterval && canSpawnPipe(state, constants)) {
    state.spawnTimer = 0;
    spawnPipe(state, constants);
  }

  for (const pipe of state.pipes) {
    pipe.x -= constants.pipeSpeed * dt;
    if (!pipe.scored && pipe.x + constants.pipeWidth < constants.birdX) {
      pipe.scored = true;
      state.score += 1;
    }
  }

  state.pipes = state.pipes.filter((pipe) => pipe.x + constants.pipeWidth > -24);

  const skipBounds = options.skipBounds === true;
  const pipeHit = collidesWithPipe(state, constants, options);
  if ((!skipBounds && birdOutOfBounds(state, constants)) || pipeHit) {
    state.gameOver = true;
  }

  return state;
}

/**
 * @param {object} [options]
 * @param {boolean} [options.skipCollisions] - pass through all pipe solids (god mode)
 * @param {boolean} [options.passPipeGap] - pass through pipe column only while overlapping gap Y; still hit caps + frame
 */
export function collidesWithPipe(state, constants = GAME_CONSTANTS, options = {}) {
  if (options.skipCollisions === true) {
    return false;
  }

  const radius = constants.birdRadius;
  const birdLeft = constants.birdX - radius;
  const birdRight = constants.birdX + radius;
  const birdTop = state.birdY - radius;
  const birdBottom = state.birdY + radius;

  return state.pipes.some((pipe) => {
    const withinX = birdRight > pipe.x && birdLeft < pipe.x + constants.pipeWidth;
    if (!withinX) {
      return false;
    }

    const gapTop = pipe.gapY;
    const gapBottom = pipe.gapY + constants.pipeGap;

    if (options.passPipeGap === true) {
      const overlapsGap = birdBottom > gapTop && birdTop < gapBottom;
      return !overlapsGap;
    }

    const fullyInGap = birdTop > gapTop && birdBottom < gapBottom;
    return !fullyInGap;
  });
}

export function birdOutOfBounds(state, constants = GAME_CONSTANTS) {
  return (
    state.birdY < constants.birdRadius ||
    state.birdY > constants.floorY - constants.birdRadius
  );
}

function clamp(value, min, max) {
  return Math.min(max, Math.max(min, value));
}
