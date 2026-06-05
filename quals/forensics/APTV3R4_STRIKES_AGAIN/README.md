# WIP EVEN THIS README FILE IS NOT PROPER

# Name
Vera's Super Secret File Vaults

# Description
A forenshits challenge, WIP, only got the website running

# Author
Verity, Hexerberg

# Flag
`grey{placeholder_flag}`

# Challenge
Only users with the correct 67-character token can access Vera's vault. Participants have to analyse the PCAP, to get the token as well as the filename of the memory dump to analyse. Following the download, the participant analyses the memory dump to extract 1. flag.enc and 2. the smb keyfile . They can then decrypt smb traffic in the PCAP, to get the decryption key for flag.enc.

# Local Verification

Run the stack:

```bash
docker compose up --build
```

Open:

```text
http://127.0.0.1:34667
```

Verify the seeded dummy file:

```bash
curl -i "http://127.0.0.1:34667/api/vault?download=test.txt&token=PV6QKm8XtToPXK4G4u9uatWRX9GQlERnawgC31Uj5qb8KypnHVzPpNusmb84GdDvJZq"
```

# Development

Backend:

```powershell
cd backend
py -m pip install -r requirements.txt
py -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Frontend:

```powershell
cd frontend
npm install
npm run dev
```

Open `http://127.0.0.1:5173`.

Landing-page URL formats:

```text
<site>/?upload=<filename>&token=<token>
<site>/?download=<filename>&token=<token>
```

## Token

The vault token must be exactly 67 characters.

Set it explicitly:

```powershell
$env:VAULT_TOKEN = "replace-with-a-67-character-token................................"
```

If `VAULT_TOKEN` is not set, the backend creates `backend/.vault_token` the first time it starts.

## API

The vault includes a seeded `test.txt` file containing:

```text
test
```

Upload:

```text
GET or POST /api/vault?upload=<anything>&token=<67-character-token>
multipart field: file
```

Uploads are UNDER maintenance and DO NOT work. Valid upload attempts return `200 OK` with the text `upload successful` without checking the filename or storing a file.

Download:

```text
GET /api/vault?download=<filename>&token=<67-character-token>
```

Visiting the frontend with `?download=<filename>&token=<token>` immediately starts the download instead of showing a separate download mode.

Server-side behavior:

- Missing or incorrect token returns `400`.
- Upload requests with the correct token return `200`, even if the filename is missing or malformed.
- Download requests with the correct token and a missing or wrong filename return `404`.
