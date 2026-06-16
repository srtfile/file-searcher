# Advanced File Search Web

This is a Flask web version of the PyQt local file searcher.

## Important

A Render-hosted app can search only files that exist inside the Render server/container, for example files committed to this repo under `search_root` or files written to an attached Render disk.

It cannot directly search `C:\Users\AC\...` on your Windows computer because Render runs in the cloud, not on your PC.

To search your own Windows computer from a webpage, run this project locally using `run_local.bat`, then open:

```text
http://127.0.0.1:5000
```

Default local token in `run_local.bat`:

```text
local123
```

## Deploy to Render from GitHub

1. Upload these files to a GitHub repository.
2. Put any searchable demo/server files inside `search_root`.
3. In Render, click **New +** → **Blueprint** or **Web Service**.
4. Select the GitHub repo.
5. If using `render.yaml`, Render will create `AUTH_TOKEN` automatically.
6. Open the Render URL and enter the generated `AUTH_TOKEN` from Render environment variables.

## Manual Render settings

- Build command:

```bash
pip install -r requirements.txt
```

- Start command:

```bash
gunicorn app:app
```

- Environment variables:

```text
AUTH_TOKEN=<make a strong secret>
SEARCH_ROOT=/opt/render/project/src/search_root
```

## Features

- Exact text search
- Regex search
- URL search
- Extension filters
- Case-sensitive option
- Maximum file size limit
- Maximum result limit
- File download link for matched server/local files
- Directory listing inside the safe `SEARCH_ROOT`

## Security note

Do not set `SEARCH_ROOT` to your entire computer drive when exposing this app publicly. Keep the token secret.
