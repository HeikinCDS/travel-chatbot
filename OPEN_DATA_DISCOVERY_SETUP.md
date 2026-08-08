# JomVoyage free open-data discovery

Maya can discover attractions without a paid API key. The live provider uses:

- Wikidata for structured attraction facts and source links.
- OpenStreetMap Overpass for tourism places and recorded accessibility tags.
- Wikimedia Commons for real photographs, licences and attribution.
- Ollama only when you optionally enable a local language model.

The existing SQLite collection remains the fallback if the internet or a public
service is unavailable.

## Normal use: no key and no additional installation

Activate the virtual environment and run JomVoyage normally:

```powershell
python app.py
```

The first new preference combination may take longer because Maya contacts the
public sources. Results are cached in `instance/travel_recommender.db` for seven
days. Repeated requests use the cache and do not contact the public services.

## Optional local Ollama descriptions

Ollama is not needed for discovery, recommendation ranking or photographs. It
only rewrites an existing sourced description into a friendlier sentence.

1. Install Ollama from https://ollama.com/download/windows.
2. In PowerShell, download a model supported by your computer:

```powershell
ollama pull qwen3:4b
```

3. Enable that model for the current PowerShell window:

```powershell
$env:OLLAMA_MODEL="qwen3:4b"
python app.py
```

If Ollama is stopped or unavailable, Maya uses the original open-data
description automatically.

## Responsible public-service use

- JomVoyage sends Wikidata and OpenStreetMap requests sequentially.
- Search results are cached for seven days.
- The application identifies itself with a User-Agent.
- OpenStreetMap and Wikimedia attribution remains visible to users.
- Missing prices, visit duration and elderly-accessibility details remain
  `Unknown`; they are not inferred by Ollama.

For a deployed or heavily used application, use hosted or self-managed data
services rather than depending indefinitely on public community servers.
