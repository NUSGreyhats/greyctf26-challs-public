module.exports = {
  session_secret: process.env.SESSION_SECRET || 'pollution-dev-session-secret',
  password_pepper: process.env.PASSWORD_MAC_KEY || 'pollution-dev-mac-key',
  flag: 'grey{placeholder}'
};
