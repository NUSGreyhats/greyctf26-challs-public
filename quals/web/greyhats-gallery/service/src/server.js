const fs = require("fs");
const fsp = require("fs/promises");
const path = require("path");
const { execFile } = require("child_process");
const { promisify } = require("util");

const express = require("express");
const multer = require("multer");

const app = express();
const PORT = process.env.PORT || 3000;
const HOST = process.env.HOST || "0.0.0.0";
const execFileAsync = promisify(execFile);

const ROOT_DIR = path.join(__dirname, "..");
const VIEWS_DIR = path.join(ROOT_DIR, "views");
const UPLOADS_DIR = path.join(ROOT_DIR, "uploads");
const PHOTO_DIR = UPLOADS_DIR;

const PHOTO_EXTENSIONS = new Set([
  ".jpg",
  ".jpeg",
  ".png",
  ".gif",
  ".webp",
  ".bmp",
  ".heic",
  ".heif"
]);

const ZIP_EXTENSION = ".zip";
const ALLOWED_UPLOAD_EXTENSIONS = new Set([...PHOTO_EXTENSIONS, ZIP_EXTENSION]);

function sanitizeUploadFilename(originalName) {
  return originalName
    .replace(/[\/\\:\0<>|"'`$&;(){}[\]*?~!#%\s]+/g, "")
    .replace(/\.+/g, ".")
    .replace(/^\.+|\.+$/g, "")
    .slice(0, 120) || "upload";
}

const upload = multer({
  storage: multer.diskStorage({
    destination: (req, file, cb) => {
      fs.mkdir(PHOTO_DIR, { recursive: true }, (error) => cb(error, PHOTO_DIR));
    },
    filename: (req, file, cb) => {
      cb(null, sanitizeUploadFilename(file.originalname));
    }
  }),
  limits: {
    fileSize: 20 * 1024 * 1024
  },
  fileFilter: (req, file, cb) => {
    const extension = path.extname(sanitizeUploadFilename(file.originalname)).toLowerCase();
    if (!ALLOWED_UPLOAD_EXTENSIONS.has(extension)) {
      cb(new Error("Please upload a photo or .zip file."));
      return;
    }

    cb(null, true);
  }
});

app.set("view engine", "ejs");
app.set("views", VIEWS_DIR);

app.use(express.urlencoded({ extended: false }));

async function ensureStorage() {
  await fsp.mkdir(PHOTO_DIR, { recursive: true });
}

function imageContentType(header) {
  if (header.length >= 3 && header[0] === 0xff && header[1] === 0xd8 && header[2] === 0xff) {
    return "image/jpeg";
  }

  if (header.subarray(0, 8).equals(Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]))) {
    return "image/png";
  }

  const gif = header.subarray(0, 6).toString("ascii");
  if (gif === "GIF87a" || gif === "GIF89a") {
    return "image/gif";
  }

  if (header.length >= 12 && header.subarray(0, 4).toString("ascii") === "RIFF" && header.subarray(8, 12).toString("ascii") === "WEBP") {
    return "image/webp";
  }

  if (header.length >= 2 && header[0] === 0x42 && header[1] === 0x4d) {
    return "image/bmp";
  }

  const heifBrand = header.length >= 12 ? header.subarray(4, 12).toString("ascii") : "";
  if (heifBrand.startsWith("ftyp") && /^(heic|heix|hevc|hevx|mif1|msf1)/.test(heifBrand.slice(4))) {
    return "image/heif";
  }

  return null;
}

function resolvePhotoPath(relativePath) {
  if (!isSafeRelativePath(relativePath)) {
    return null;
  }

  const filePath = path.resolve(PHOTO_DIR, relativePath);
  const relative = path.relative(PHOTO_DIR, filePath);
  if (!relative || relative.startsWith("..") || path.isAbsolute(relative)) {
    return null;
  }

  return filePath;
}

async function readHeader(filePath) {
  const file = await fsp.open(filePath, "r");
  try {
    const header = Buffer.alloc(16);
    const result = await file.read(header, 0, header.length, 0);
    return header.subarray(0, result.bytesRead);
  } finally {
    await file.close();
  }
}

async function extractPhotosFromZip(zipPath) {
  const before = new Set((await listPhotos()).map((photo) => photo.relativePath));
  await execFileAsync("unzip", ["-o", zipPath, "-d", PHOTO_DIR], {
    maxBuffer: 10 * 1024 * 1024
  });

  const after = await listPhotos();
  const extracted = after
    .map((photo) => photo.relativePath)
    .filter((relativePath) => !before.has(relativePath));

  return { extracted };
}

async function handleUploadedFiles(files) {
  let imported = 0;

  for (const file of files) {
    const extension = path.extname(file.originalname).toLowerCase();

    if (extension === ZIP_EXTENSION) {
      const result = await extractPhotosFromZip(file.path);
      imported += result.extracted.length;
      await fsp.rm(file.path, { force: true });
      continue;
    }

    if (PHOTO_EXTENSIONS.has(extension)) {
      imported += 1;
    }
  }

  return imported;
}

function isSafeRelativePath(relativePath) {
  return Boolean(relativePath) && !path.isAbsolute(relativePath) && !relativePath.split(path.sep).includes("..");
}

async function collectPhotos(directory, baseDirectory = directory) {
  const entries = await fsp.readdir(directory, { withFileTypes: true });
  const photos = [];

  for (const entry of entries) {
    const filePath = path.join(directory, entry.name);

    if (entry.isDirectory()) {
      photos.push(...(await collectPhotos(filePath, baseDirectory)));
      continue;
    }

    const extension = path.extname(entry.name).toLowerCase();
    if (!PHOTO_EXTENSIONS.has(extension)) {
      continue;
    }

    const stats = await fsp.stat(filePath);
    photos.push({
      filename: entry.name,
      relativePath: path.relative(baseDirectory, filePath),
      url: `/photos/${path.relative(baseDirectory, filePath).split(path.sep).map(encodeURIComponent).join("/")}`,
      size: stats.size,
      uploadedAt: stats.birthtime
    });
  }

  return photos;
}

async function listPhotos() {
  const photos = await collectPhotos(PHOTO_DIR);
  photos.sort((a, b) => b.uploadedAt - a.uploadedAt);
  return photos;
}

async function templateLocals(req, title) {
  return {
    title,
    photos: await listPhotos(),
    message: req.query.message || null,
    error: req.query.error || null,
    query: req.query
  };
}

async function templateExists(template) {
  try {
    await fsp.access(path.join(VIEWS_DIR, `${template}.ejs`), fs.constants.R_OK);
    return true;
  } catch (error) {
    return false;
  }
}

app.get("/", async (req, res, next) => {
  try {
    res.render("index", await templateLocals(req, "Greyhats Gallery"));
  } catch (error) {
    next(error);
  }
});

app.post("/upload", upload.array("photos", 20), async (req, res, next) => {
  if (!req.files || req.files.length === 0) {
    res.status(400).render("upload", {
      title: "Upload to Greyhats Gallery",
      error: "Choose at least one photo or ZIP file to upload."
    });
    return;
  }

  try {
    const imported = await handleUploadedFiles(req.files);
    const message = `Imported ${imported} photo${imported === 1 ? "" : "s"}.`;
    res.redirect(`/?message=${encodeURIComponent(message)}`);
  } catch (error) {
    next(error);
  }
});

app.get("/photos/*", async (req, res, next) => {
  try {
    const relativePath = req.params[0];
    const filePath = resolvePhotoPath(relativePath);

    if (!filePath || !PHOTO_EXTENSIONS.has(path.extname(filePath).toLowerCase())) {
      res.sendStatus(404);
      return;
    }

    const contentType = imageContentType(await readHeader(filePath));
    if (!contentType) {
      res.sendStatus(415);
      return;
    }

    res.type(contentType);
    res.sendFile(filePath);
  } catch (error) {
    if (error.code === "ENOENT" || error.code === "EISDIR") {
      res.sendStatus(404);
      return;
    }

    next(error);
  }
});

app.post("/photos/delete", async (req, res, next) => {
  try {
    const relativePath = req.body.path;

    if (!isSafeRelativePath(relativePath) || !PHOTO_EXTENSIONS.has(path.extname(relativePath).toLowerCase())) {
      res.status(400).redirect("/?error=Invalid%20photo%20name.");
      return;
    }

    const filePath = path.join(PHOTO_DIR, relativePath);
    await fsp.rm(filePath, { force: true });
    res.redirect("/?message=Photo%20deleted.");
  } catch (error) {
    next(error);
  }
});

app.get("/*", async (req, res, next) => {
  const template = req.path.replace(/\//g, "") || "index";
  const title = template === "upload" ? "Upload to Greyhats Gallery" : template;

  try {
    if (!(await templateExists(template))) {
      res.status(404).render("error", {
        title: "Not Found",
        error: "Page not found."
      });
      return;
    }

    res.render(template, await templateLocals(req, title));
  } catch (error) {
    next(error);
  }
});

app.use((error, req, res, next) => {
  if (error instanceof multer.MulterError) {
    res.status(400).render("upload", {
      title: "Upload to Greyhats Gallery",
      error: error.message
    });
    return;
  }

  if (error.message === "Please upload a photo or .zip file.") {
    res.status(400).render("upload", {
      title: "Upload to Greyhats Gallery",
      error: error.message
    });
    return;
  }

  next(error);
});

app.use((error, req, res, next) => {
  console.error(error);
  res.status(500).render("error", {
    title: "Server Error",
    error: "Something went wrong."
  });
});

ensureStorage().then(() => {
  app.listen(PORT, HOST, () => {
    console.log(`Greyhats Gallery listening at http://${HOST}:${PORT}`);
  });
});
