const express = require('express');
const bodyParser = require('body-parser');
const session = require('express-session');
const passport = require('passport');
const flash = require('connect-flash');
const db = require('./db');
const options = require('./options');
const secrets = require('./secrets');

require('./passport');

const app = express();

app.locals.partials = {
  navbar: 'partials/navbar',
  head: 'partials/head'
};

app
  .set('view engine', 'hjs')
  .use(express.static(__dirname + '/public'))
  .use(bodyParser.json())
  .use(bodyParser.urlencoded({ extended: false }))
  .use(session({
    secret: secrets.session_secret,
    resave: false,
    saveUninitialized: false
  }))
  .use(passport.initialize())
  .use(passport.session())
  .use(flash())
  .use((req, res, next) => {
    app.locals.user = req.user || null;
    app.locals.authenticated = req.isAuthenticated();
    next();
  })
  .get('/', (req, res) => {
    res.render('home', {
      error: req.flash('error'),
      success: req.flash('success')
    });
  })
  .get('/register', (req, res) => {
    res.render('register', { message: req.flash('error') });
  })
  .get('/login', (req, res) => {
    res.render('login', { message: req.flash('error') });
  })
  .use(require('./routes/user'))
  .use(require('./routes/auth'));

async function start() {
  await db.connect();
  app.listen(options.port, () => {
    console.log(`Listening on port ${options.port}`);
  });
}

start().catch((err) => {
  console.error(err);
  process.exit(1);
});
