const fs = require('fs');
const path = require('path');
const crypto = require('crypto');

const DATA_PATH = process.env.DATA_PATH || path.join(__dirname, 'uploads', 'db.json');
const MAX_STORE_BYTES = Number(process.env.MAX_STORE_BYTES || 4 * 1024 * 1024);

let state = { users: [] };

class ObjectId {
  constructor(id) {
    this.id = id || crypto.randomBytes(12).toString('hex');
  }

  toHexString() {
    return this.id;
  }

  toString() {
    return this.id;
  }

  toJSON() {
    return this.id;
  }
}

function ensureStore() {
  fs.mkdirSync(path.dirname(DATA_PATH), { recursive: true });
  if (!fs.existsSync(DATA_PATH) || fs.statSync(DATA_PATH).size === 0) {
    fs.writeFileSync(DATA_PATH, JSON.stringify(state, null, 2));
  }
}

function revive(doc) {
  if (!doc) {
    return null;
  }
  const revived = JSON.parse(JSON.stringify(doc));
  revived._id = new ObjectId(doc._id);
  return revived;
}

function writeState(nextState) {
  const serialized = JSON.stringify(nextState, null, 2);
  if (Buffer.byteLength(serialized) > MAX_STORE_BYTES) {
    throw new Error('Local user store size limit exceeded');
  }
  const tmpPath = `${DATA_PATH}.${process.pid}.${Date.now()}.tmp`;
  fs.writeFileSync(tmpPath, serialized);
  fs.renameSync(tmpPath, DATA_PATH);
  state = nextState;
}

function cloneState() {
  return JSON.parse(JSON.stringify(state));
}

function sameObjectId(left, right) {
  return String(left) === String(right);
}

function matches(doc, query) {
  if (query instanceof ObjectId || typeof query === 'string') {
    return sameObjectId(doc._id, query);
  }

  if (!query || typeof query !== 'object') {
    return false;
  }

  return Object.entries(query).every(([key, value]) => {
    if (key === '$or') {
      return value.some((clause) => matches(doc, clause));
    }
    if (key === '_id') {
      return sameObjectId(doc._id, value);
    }
    if (value && typeof value === 'object' && Object.prototype.hasOwnProperty.call(value, '$exists')) {
      return Object.prototype.hasOwnProperty.call(doc, key) === value.$exists;
    }
    return doc[key] === value;
  });
}

function callbackify(promise, callback) {
  if (typeof callback === 'function') {
    promise.then((result) => callback(null, result)).catch((err) => callback(err));
    return undefined;
  }
  return promise;
}

function collection(name) {
  if (!state[name]) {
    state[name] = [];
  }

  return {
    find(query) {
      return {
        async toArray() {
          return state[name].filter((doc) => matches(doc, query)).map(revive);
        }
      };
    },

    findOne(query, options, callback) {
      const cb = typeof options === 'function' ? options : callback;
      return callbackify(Promise.resolve(revive(state[name].find((doc) => matches(doc, query)))), cb);
    },

    insertOne(doc, callback) {
      return callbackify(Promise.resolve().then(() => {
        const nextState = cloneState();
        nextState[name] = nextState[name] || [];
        const stored = JSON.parse(JSON.stringify(doc));
        stored._id = stored._id || new ObjectId().toHexString();
        nextState[name].push(stored);
        writeState(nextState);
        return { insertedId: new ObjectId(stored._id) };
      }), callback);
    },

    updateOne(query, update, callback) {
      return callbackify(Promise.resolve().then(() => {
        const nextState = cloneState();
        nextState[name] = nextState[name] || [];
        const doc = nextState[name].find((candidate) => matches(candidate, query));
        if (!doc) {
          return { matchedCount: 0, modifiedCount: 0 };
        }
        if (update.$set) {
          Object.assign(doc, JSON.parse(JSON.stringify(update.$set)));
        }
        writeState(nextState);
        return { matchedCount: 1, modifiedCount: 1 };
      }), callback);
    }
  };
}

async function connect() {
  ensureStore();
  state = JSON.parse(fs.readFileSync(DATA_PATH, 'utf8'));
  state.users = state.users || [];
  module.exports.db = { collection };
  console.log(`Connected to local JSON store at ${DATA_PATH}.`);
  return module.exports.db;
}

module.exports.connect = connect;
module.exports.ObjectId = ObjectId;
module.exports.DATA_PATH = DATA_PATH;
module.exports.MAX_STORE_BYTES = MAX_STORE_BYTES;
