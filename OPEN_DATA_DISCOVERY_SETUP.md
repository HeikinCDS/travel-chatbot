# JomVoyage free open-data discovery

Maya can discover attractions without a paid API key. The live provider uses:

- Wikidata for structured attraction facts and source links.
- OpenStreetMap Overpass for tourism places and recorded accessibility tags.
- Wikimedia Commons for real photographs, licences and attribution.
- Openverse as an openly licensed image-search fallback.
- LM Studio only when you optionally enable local language understanding.

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

## Optional LM Studio language understanding

LM Studio is not needed for discovery, recommendation ranking or photographs.
When enabled, it helps Maya interpret flexible travel language and rewrites
source facts into concise visitor-friendly descriptions. Description generation
is performed in one validated batch and is not allowed to invent prices,
opening hours, accessibility claims, ratings or named facilities.

1. Install LM Studio and download `Qwen3.5-4B-GGUF` (`Q4_K_M`).
2. Start **Local Model API** at `http://127.0.0.1:1234/v1`.
3. Run JomVoyage. It automatically looks for `qwen3.5-4b` at the local API:

```powershell
python app.py
```

`LM_STUDIO_MODEL` and `LM_STUDIO_URL` can still be set when a different local
model name or server address is required.

Keep LM Studio open while JomVoyage is running. If LM Studio is stopped,
unavailable or returns invalid data, Maya automatically uses the existing
spaCy classifier and rule-based entity extractor.

For responsiveness, ordinary recognised messages such as a state name, budget
or known interest do not call the local model. LM Studio is used as a fallback
only when the existing NLP is uncertain or initially considers the message out
of scope. New attraction descriptions may still take longer on their first
request; the generated versions are then cached.

## Responsible public-service use

- JomVoyage sends Wikidata and OpenStreetMap requests sequentially.
- Search results are cached for seven days.
- The application identifies itself with a User-Agent.
- OpenStreetMap and Wikimedia attribution remains visible to users.
- Missing prices and visit-duration details are not invented by the local
  model. Unsupported states, interests and invalid numbers are discarded.

For a deployed or heavily used application, use hosted or self-managed data
services rather than depending indefinitely on public community servers.
