# JomVoyage local semantic retrieval

JomVoyage combines three retrieval signals:

1. SQLite filters enforce state, budget and accessibility requirements.
2. FTS5 ranks exact words in attraction names, tags and descriptions.
3. Sentence Transformers ranks related meanings using local embeddings.

The semantic layer does not generate text and does not call a paid API.

## Build the embedding index once

Activate the project virtual environment, then run:

```powershell
python scripts/build_semantic_index.py
```

The first run downloads `sentence-transformers/all-MiniLM-L6-v2` and stores
one normalized embedding for each curated attraction in SQLite. Later runs use
the cached model. Rebuild the index after changing attraction descriptions,
tags or accessibility notes.

## Run JomVoyage

Semantic retrieval is enabled by default when a valid index and locally cached
model are available:

```powershell
$env:ENABLE_LOCAL_LLM="false"
$env:ENABLE_LIVE_DISCOVERY="false"
$env:ENABLE_SEMANTIC_SEARCH="true"
$env:SEMANTIC_SEARCH_MODE="adaptive"
python app.py
```

`adaptive` is the recommended mode. Exact FTS5 matches return immediately;
semantic comparison runs only when the query wording has no useful keyword
match in the filtered candidates.

To compare the FTS5-only baseline:

```powershell
$env:ENABLE_SEMANTIC_SEARCH="false"
python app.py
```

For evaluation only, `SEMANTIC_SEARCH_MODE="always"` runs semantic comparison
for every recommendation request.

If the semantic model or index is unavailable, recommendations automatically
fall back to FTS5 and structured database filtering.
