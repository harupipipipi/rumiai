# Search Home Pack

`search_home_pack` is a Startup Profile surface pack that gives Rumi a local
search-first home screen while reusing `defaultspack` for AI classification,
chat responses, and web search.

## What It Owns

- localhost browser UI
- deterministic URL safety checks
- route selection for URL, Google, AI, and AI-with-search
- cross-pack function bridge to `defaultspack`

## What It Does Not Own

- model runtime settings
- provider configuration
- model routing internals
- provider key storage
- web search implementation

Those stay inside `defaultspack`, which remains the source of truth.

## Local Endpoints

- `GET /health`
- `GET /api/health`
- `POST /api/route`
- `POST /api/ask`

## Webapp

The editable React source lives in [webapp](./webapp). The desktop app serves
the compiled assets from [ui](./ui).

To rebuild the UI bundle:

```bash
cd rumi_ai_1_10/ecosystem/search_home_pack/webapp
npm install
npm run build
```
