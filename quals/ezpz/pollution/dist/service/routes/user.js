const express = require('express');
const router = express.Router();
const fs = require('fs');
const path = require('path');
const multer = require('multer');
const store = require('../db');
const util = require('../util');
const options = require('../options');

const USER_FIELDS = ['username', 'lcUsername', 'password', 'role', 'bio', 'img', 'joinDate'];
const MAX_IMPORT_FILE_BYTES = 256 * 1024;
const MAX_IMPORTED_USERS = 100;
const MAX_IMPORTED_USER_BYTES = 32 * 1024;
const MAX_STORE_BYTES = Number(process.env.MAX_STORE_BYTES || 4 * 1024 * 1024);

const upload = multer({
  dest: 'public/images/profileImages',
  limits: { fileSize: 2000000 }
});

const uploadUsers = multer({
  storage: multer.memoryStorage(),
  limits: { fileSize: MAX_IMPORT_FILE_BYTES }
});

function isObject(item) {
  return item && typeof item === 'object' && !Array.isArray(item);
}

function merge(target, source) {
  Object.keys(source).forEach((key) => {
    if (isObject(source[key])) {
      if (!target[key]) {
        target[key] = {};
      }
      merge(target[key], source[key]);
    } else {
      target[key] = source[key];
    }
  });

  return target;
}

function pickUserUpdate(doc) {
  const update = {};
  USER_FIELDS.forEach((key) => {
    if (Object.prototype.hasOwnProperty.call(doc, key)) {
      update[key] = doc[key];
    }
  });
  return update;
}

function dbSizeBytes() {
  try {
    return fs.statSync(store.DATA_PATH).size;
  } catch (err) {
    return 0;
  }
}

function importSizeBytes(item) {
  return Buffer.byteLength(JSON.stringify(item));
}

function rejectImport(res, status, message) {
  return res.status(status).send(`Import rejected: ${message}`);
}

function hasImportIdentity(item) {
  return (typeof item.lcUsername === 'string' && item.lcUsername.trim()) ||
    (typeof item.username === 'string' && item.username.trim());
}

function handleImportUpload(req, res, next) {
  uploadUsers.single('upload-users')(req, res, (err) => {
    if (!err) {
      return next();
    }
    if (err instanceof multer.MulterError && err.code === 'LIMIT_FILE_SIZE') {
      return rejectImport(res, 413, 'the uploaded JSON file is larger than 256 KB.');
    }
    return next(err);
  });
}

function findUser(lcUsername) {
  return store.db.collection('users')
    .findOne({ lcUsername }, { collation: { locale: "en", strength: 2 } });
}

function updateUser(lcUsername, update) {
  return new Promise((resolve, reject) => {
    store.db.collection('users')
      .updateOne({ lcUsername }, { $set: update }, (err) => {
        if (err) {
          return reject(err);
        }
        resolve();
      });
  });
}

function insertUser(item) {
  return new Promise((resolve, reject) => {
    store.db.collection('users')
      .insertOne(item, (err) => {
        if (err) {
          return reject(err);
        }
        resolve();
      });
  });
}

function loginRequired(req, res, next) {
  if (!req.isAuthenticated()) {
    req.flash('info', 'You must be logged in to perform that action.');
    return res.redirect('/login');
  }
  next();
}

function adminRequired(req, res, next) {
  if (req.isAuthenticated()) {
    if (!req.user.admin) {
      req.flash('error', 'Only site administrators are permitted to visit that page.')
      return res.redirect('/login')
    }
    next()
  }else {
    req.flash('error', 'Only site administrators are permitted to visit that page.')
    return res.redirect('/login')
  }
}

router
  // GET profile page
  .get('/profile', loginRequired, (req, res) => {
    res.render('profile', {
      user: req.user,
      error: req.flash('error'),
      success: req.flash('success')
    });
  })
  // POST new user bio
  .post('/updateBio', loginRequired, (req, res) => {
    store.db.collection('users')
      .updateOne({ lcUsername: req.user.lcUsername }, { $set: { bio: req.body.bio || '' } }, (err) => {
        if (err) {
          console.log(err);
        }
        req.flash('success', 'Your bio has been updated.');
        res.redirect('/profile');
      });
  })
  // POST new user password
  .post('/changePassword', loginRequired, (req, res) => {
    if (req.body.newPassword !== req.body.newPassword2) {
      req.flash('error', 'Passwords do not match.');
      return res.redirect('/profile');
    }

    store.db.collection('users')
      .findOne({ lcUsername: req.user.lcUsername }, (err, result) => {
        if (err) {
          console.log(err);
          return res.redirect('/profile');
        }

        if (!util.verifyPassword(req.body.password, result.password)) {
          req.flash('error', 'Incorrect current password.');
          return res.redirect('/profile');
        }

        store.db.collection('users')
          .updateOne(
            { lcUsername: req.user.lcUsername },
            { $set: { password: util.macPassword(req.body.newPassword) } },
            (updateErr) => {
              if (updateErr) {
                console.log(updateErr);
              }
              req.flash('success', 'Your password has been updated.');
              res.redirect('/profile');
            }
          );
      });
  })
  // POST route for profile picture upload
  .post('/upload', loginRequired, upload.single('avatar'), (req, res) => {
    if (!req.file) {
      req.flash('error', 'No file uploaded.');
      return res.redirect('/profile');
    }

    const destination = path.join(req.file.destination, req.user.username);
    fs.rename(req.file.path, destination, (err) => {
      if (err) {
        console.log(err);
        req.flash('error', 'Could not save profile picture.');
        return res.redirect('/profile');
      }

      const imgPath = `/images/profileImages/${req.user.username}`;
      store.db.collection('users')
        .updateOne({ lcUsername: req.user.lcUsername }, { $set: { img: imgPath } }, (updateErr) => {
          if (updateErr) {
            console.log(updateErr);
          }
          req.user.img = imgPath;
          req.flash('success', 'Profile picture updated.');
          res.redirect('/profile');
        });
    });
  })
  .post('/upload/users', handleImportUpload, async (req, res) => {
    try {
      if (!req.file) {
        return rejectImport(res, 400, 'no file was uploaded.');
      }
      if (dbSizeBytes() >= MAX_STORE_BYTES) {
        return rejectImport(res, 413, 'the user store is full. Start a fresh instance to reset challenge state, or upload fewer and smaller users.');
      }
      if (dbSizeBytes() + req.file.size > MAX_STORE_BYTES) {
        return rejectImport(res, 413, 'this import would exceed the user store limit. Upload fewer and smaller users, or start a fresh instance to reset challenge state.');
      }
      const newUsers = JSON.parse(req.file.buffer.toString());
      if (!Array.isArray(newUsers)) {
        return rejectImport(res, 400, 'expected a JSON array of users.');
      }
      if (newUsers.length > MAX_IMPORTED_USERS) {
        return rejectImport(res, 413, `too many users in one import. The limit is ${MAX_IMPORTED_USERS}.`);
      }
      if (newUsers.some((item) => !isObject(item) || importSizeBytes(item) > MAX_IMPORTED_USER_BYTES)) {
        return rejectImport(res, 413, 'each imported user must be an object no larger than 32 KB.');
      }
      if (newUsers.some((item) => !hasImportIdentity(item))) {
        return rejectImport(res, 400, 'each imported user must include a non-empty username or lcUsername.');
      }

      for (const item of newUsers) {
        if (typeof item.lcUsername === 'string' && item.lcUsername) {
          item.lcUsername = item.lcUsername.trim().toLowerCase();
        } else if (typeof item.username === 'string' && item.username) {
          item.lcUsername = item.username.trim().toLowerCase();
        }
        const user = await findUser(item.lcUsername);
        if (user) {
          delete item._id;
          const merged = merge(Object.assign({}, user), item);
          await updateUser(item.lcUsername, pickUserUpdate(merged));
          console.log('The user', item.lcUsername, 'is updated');
        } else {
          if (!item.img) {
            item.img = '/images/profile.svg';
          }
          if (!item.role) {
            item.role = 'user';
          }
          await insertUser(item);
          console.log('The user', item.lcUsername, 'is added');
        }
      }

      res.redirect('back')
    } catch (err) {
      console.log(err)
      if (err instanceof SyntaxError) {
        return rejectImport(res, 400, 'invalid JSON.');
      }
      if (/size limit/.test(err.message)) {
        return rejectImport(res, 413, 'the user store is full. Start a fresh instance to reset challenge state, or upload fewer and smaller users.');
      }
      res.status(500).send('Internal server error')
    }
  })

module.exports = router;
