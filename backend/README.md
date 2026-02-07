# Backend — Local development

## One-time setup

From the **backend** directory:

```bash
cd backend
python -m venv .venv
.venv/bin/pip install -r requirements.txt
```

(Or use `make install` from `backend/`.)

## Run the server

**Important:** (Optional) If you use Docker, stop it first so it doesn’t use port 8001:

```bash
# (If you use Docker: docker compose down  or  docker-compose down)
```

Then from the **backend** directory:

```bash
./run.sh
```

Or:

```bash
make run
```

The API will be at:

- http://127.0.0.1:8001/
- http://127.0.0.1:8001/api/health
- http://127.0.0.1:8001/api/locations (GET and POST)

Check with:

```bash
curl -s http://127.0.0.1:8001/api/health
curl -s http://127.0.0.1:8001/api/locations
```

## If you get 404 on `/api/locations`

1. **See what is using port 8001:** `lsof -i :8001` — you should see one `python`/`uvicorn` when the backend is running.
2. Stop any other process on 8001, then start the backend with `./run.sh` from `backend/`.
3. Run the `curl` commands above from a new terminal. If it still 404s, paste the startup log and `lsof -i :8001` output.
