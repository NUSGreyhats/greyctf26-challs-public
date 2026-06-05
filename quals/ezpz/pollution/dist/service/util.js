const crypto = require('crypto');
const secrets = require('./secrets');

function macPassword(password) {
  return crypto
    .createHmac('sha256', secrets.password_pepper)
    .update(password)
    .digest('hex');
}

function verifyPassword(password, storedMac) {
  const computed = macPassword(password);
  if (computed.length !== storedMac.length) {
    return false;
  }
  return crypto.timingSafeEqual(Buffer.from(computed), Buffer.from(storedMac));
}

module.exports = {
  macPassword,
  verifyPassword
};
