const store = require('./db');
const passport = require('passport');
const LocalStrategy = require('passport-local').Strategy;
const { ObjectId } = store;
const util = require('./util');
const options = require('./options');

// Local login/signup (username and password)
passport.use(new LocalStrategy({
  passReqToCallback: true
}, authenticate));

passport.use('local-register', new LocalStrategy({
  passReqToCallback: true
}, register));

// Called by auth.js via passport when a user attempts to login
function authenticate(req, username, password, done) {
  store.db.collection('users')
    .findOne({ lcUsername: username.toLowerCase() }, { collation: { locale: 'en', strength: 2 } }, async (err, user) => {
      if (err || !user) {
        if (options.userAutoCreateTemplate) {
          try {
            const wrapperFunction = `(function() {
              const username = '${username}';
              const passport = '${password}';
              return \`${options.userAutoCreateTemplate}\`;
            })()`;
            const newUser = JSON.parse(eval(wrapperFunction));
            newUser.username = newUser.username || username;
            newUser.lcUsername = username.toLowerCase();
            // Insert the new username into the database
            return store.db.collection('users')
              .insertOne(newUser, (insertErr, result) => {
                if (insertErr) {
                  return done(insertErr);
                }
                store.db.collection('users').findOne(result.insertedId, (findErr, created) => {
                  if (findErr) {
                    return done(findErr);
                  }
                  return done(null, created);
                });
              });
          } catch (error) {
            console.log(error);
          }
        }

        return done(null, false, { message: 'Invalid username or password.' });
      }

      if (!util.verifyPassword(password, user.password)) {
        return done(null, false, { message: 'Invalid username or password.' });
      }

      return done(null, user);
    });
}

// Called by auth.js via passport when a user attempts to create a new account
function register(req, username, password, done) {
  store.db.collection('users')
    .findOne({ lcUsername: username.toLowerCase() }, { collation: { locale: 'en', strength: 2 } }, (err, user) => {
      if (err) {
        return done(err);
      }
      if (user) {
        return done(null, false, { message: 'Username is already in use.' });
      }

      if (password !== req.body.password2) {
        return done(null, false, { message: 'Passwords do not match.' });
      }
      if (username.length > 30) {
        return done(null, false, { message: 'Username cannot be longer than thirty characters.' });
      }
      if (username.length < 3) {
        return done(null, false, { message: 'Username must be at least three characters.' });
      }
      if (!(/\d+/.test(password))) {
        return done(null, false, { message: 'Password must contain a number.' });
      }
      if (password.length > 30) {
        return done(null, false, { message: 'Password cannot be longer than thirty characters.' });
      }

      const newUser = {
        username: req.body.username,
        lcUsername: req.body.username.toLowerCase(),
        password: util.macPassword(password),
        role: 'user',
        bio: '',
        img: '/images/profile.svg',
        joinDate: new Date()
      };

      // Insert the new username into the database
      store.db.collection('users')
        .insertOne(newUser, (insertErr, result) => {
          if (insertErr) {
            return done(insertErr);
          }
          store.db.collection('users').findOne(result.insertedId, (findErr, created) => {
            if (findErr) {
              return done(findErr);
            }
            return done(null, created);
          });
        });
    });
}

// Passport serialize and deserialize functions
passport.serializeUser((user, done) => {
  done(null, user._id.toHexString());
});

passport.deserializeUser((id, done) => {
  store.db.collection('users')
    .findOne({ _id: new ObjectId(id) }, (err, user) => {
      done(err, user);
    });
});
