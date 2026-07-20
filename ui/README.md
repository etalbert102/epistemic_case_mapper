# Inspection UI

The UI loads `data.json` in the browser, so serve the repository over HTTP
rather than opening `index.html` directly from GitHub or `file://`.

From the repository root:

```bash
./.venv/bin/python -m http.server 8000
```

Then open <http://127.0.0.1:8000/ui/>. The interface is an inspection surface;
canonical evidence and review decisions remain in the linked Markdown, JSON,
and CSV artifacts.

