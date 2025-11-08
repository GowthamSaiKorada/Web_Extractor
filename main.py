from fastapi import FastAPI
from pydantic import BaseModel
from extractor import fetch_html, extract_from_html
from typing import Optional, Dict

app = FastAPI(title="Safe Web Data Extractor API")


class ExtractRequest(BaseModel):
    url: Optional[str] = None
    html: Optional[str] = None
    use_llm: Optional[bool] = False
    mapping: Optional[Dict[str, str]] = {}


@app.post("/extract")
def extract(req: ExtractRequest):
    try:
        html = req.html
        if req.url and not html:
            final_url, html = fetch_html(req.url)
        if not html:
            return {"status": "error", "message": "No HTML or URL provided"}
        data = extract_from_html(html, req.mapping or {})
        return {"status": "ok", "data": data}
    except Exception as e:
        return {"status": "error", "message": str(e)}
