# crxzipple frontend

Vite 4 + Vue 3 front-end for the `crxzipple` orchestration APIs.

## Development

```bash
cd frontend
npm install
npm run dev
```

The Vite dev server proxies:

- `/health`
- `/about`
- `/turns`
- `/conversations`

to `http://127.0.0.1:8000`.

Run the backend in another terminal:

```bash
PYTHONPATH=src python -m crxzipple.main serve
```

## Build

```bash
cd frontend
npm run build
```
