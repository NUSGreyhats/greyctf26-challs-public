const express = require('express');
const router = express.Router();
require('../passport');
const passport = require('passport');

router
  // POST signup via passport local strategy
  .post('/signup', passport.authenticate('local-register', {
    successRedirect: '/',
    failureRedirect: '/register',
    failureFlash: true,
    successFlash: 'Account created!'
  }))
  // POST login via passport local strategy
  .post('/login', passport.authenticate('local', {
    successRedirect: 'back',
    failureRedirect: 'back',
    failureFlash: true
  }))
  // GET Logout and redirect
  .get('/logout', (req, res, next) => {
    req.logout((err) => {
      if (err) {
        return next(err);
      }
      res.redirect('/');
    });
  });

module.exports = router;
