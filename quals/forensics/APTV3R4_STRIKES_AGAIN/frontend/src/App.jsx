import { useEffect } from "react";
import { ShieldCheck } from "lucide-react";

const copy = {
  title: "Vera's Super Secret File Vaults",
  intro:
    "Hi, this is where I store my illegally pirated movies, games, and other cool stuff. I modeled this site after secure Swiss banks, so only someone with the correct token can access my stuff.",
  upload: {
    body: (
      <>
        The upload feature is <strong>UNDER MAINTENANCE</strong> and DOES NOT work.
      </>
    ),
    format: "<site>/?upload=<filename>&token=<token>",
  },
  download: {
    body: "To download a file, provide the filename in the download parameter and include the same 67-character token in the token parameter. A dummy file named test.txt is available for testing.",
    format: "<site>/?download=<filename>&token=<token>",
    fallbackFormat: "<site>/api/vault?download=<filename>&token=<token>",
  },
};

function GuideBlock({ title, body, format, example, fallbackFormat, fallbackExample }) {
  return (
    <div className="guide-block">
      <p>
        <strong>{title}:</strong> {body}
      </p>
      <code>{format}</code>
      <span>Example: {example}</span>
      {fallbackFormat ? (
        <>
          <strong>Use this fallback parameter if the format above doesn't work for downloads</strong>
          <code>{fallbackFormat}</code>
          <span>Fallback example: {fallbackExample}</span>
        </>
      ) : null}
    </div>
  );
}

export default function App() {
  const params = new URLSearchParams(window.location.search);
  const uploadFilename = params.get("upload");
  const downloadFilename = params.get("download");
  const token = params.get("token");

  const origin = window.location.origin + window.location.pathname;
  const siteOrigin = window.location.origin;
  const exampleUploadUrl = `${origin}?upload=movie-night.zip&token=YOUR_67_CHARACTER_TOKEN`;
  const exampleDownloadUrl = `${origin}?download=test.txt&token=YOUR_67_CHARACTER_TOKEN`;
  const fallbackDownloadUrl = `${siteOrigin}/api/vault?download=test.txt&token=YOUR_67_CHARACTER_TOKEN`;

  useEffect(() => {
    if (uploadFilename !== null) {
      const uploadUrl = `/api/vault?upload=${encodeURIComponent(uploadFilename)}&token=${encodeURIComponent(
        token ?? "",
      )}`;
      window.location.replace(uploadUrl);
      return;
    }

    if (downloadFilename === null) return;

    const downloadUrl = `/api/vault?download=${encodeURIComponent(downloadFilename)}&token=${encodeURIComponent(
      token ?? "",
    )}`;
    window.location.replace(downloadUrl);
  }, [uploadFilename, downloadFilename, token]);

  if (uploadFilename !== null || downloadFilename !== null) {
    return null;
  }

  return (
    <main className="app-shell landing">
      <section className="hero" aria-labelledby="site-title">
        <img src="/vault-hero.png" alt="" className="hero-image" />
        <div className="hero-scrim" />

        <div className="hero-content">
          <div className="brand-mark">
            <ShieldCheck size={20} />
            <span>Swiss-ish security</span>
          </div>

          <h1 id="site-title">{copy.title}</h1>
          <p className="intro">{copy.intro}</p>

          <div className="copy-stack">
            <GuideBlock title="To upload" {...copy.upload} example={exampleUploadUrl} />
            <GuideBlock
              title="To download"
              {...copy.download}
              example={exampleDownloadUrl}
              fallbackExample={fallbackDownloadUrl}
            />
          </div>
        </div>
      </section>
    </main>
  );
}
