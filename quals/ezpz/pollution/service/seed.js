const db = require('./db');
const util = require('./util');

const ADMIN_USERNAME = process.env.ADMIN_USERNAME || 'admin';
const ADMIN_PASSWORD = process.env.ADMIN_PASSWORD || 'admin_secret_password';

const dummyUsers = [
  { username: 'alice', password: 'alice123', bio: 'Just another user.', role: 'user' },
  { username: 'bob', password: 'bob4567', bio: 'Likes minimal UIs.', role: 'user' },
  { username: 'carol', password: 'carol890', bio: 'Here for the CTF.', role: 'user' }
];

function buildUser({ username, password, bio, role }) {
  return {
    username,
    lcUsername: username.toLowerCase(),
    password: util.macPassword(password),
    role,
    bio,
    img: '/images/profile.svg',
    joinDate: new Date()
  };
}

async function seed() {
  await db.connect();
  const users = db.db.collection('users');

  const missingLc = await users.find({ lcUsername: { $exists: false } }).toArray();
  for (const user of missingLc) {
    await users.updateOne(
      { _id: user._id },
      {
        $set: {
          lcUsername: user.username.toLowerCase(),
          role: user.role || 'user',
          bio: user.bio || '',
          img: user.img || '/images/profile.svg'
        }
      }
    );
  }

  const records = [
    buildUser({
      username: ADMIN_USERNAME,
      password: ADMIN_PASSWORD,
      bio: 'Site administrator.',
      role: 'admin'
    }),
    ...dummyUsers.map(buildUser)
  ];

  for (const record of records) {
    const exists = await users.findOne({
      $or: [{ lcUsername: record.lcUsername }, { username: record.username }]
    });
    if (exists) {
      await users.updateOne(
        { _id: exists._id },
        {
          $set: {
            username: record.username,
            lcUsername: record.lcUsername,
            password: record.password,
            role: record.role,
            bio: record.bio,
            img: record.img || exists.img || '/images/profile.svg'
          }
        }
      );
    } else {
      await users.insertOne(record);
    }
  }

  console.log('Seeded users:', records.map((u) => u.username).join(', '));
  process.exit(0);
}

seed().catch((err) => {
  console.error(err);
  process.exit(1);
});
