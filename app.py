# app.py
import streamlit as st
import pandas as pd
import json
import os
import requests
from dotenv import load_dotenv

# Load environment variables
load_dotenv()
API_URL = os.getenv("API_URL", "http://localhost:8000")

# ------------------- Streamlit Page Config -------------------
st.set_page_config(
    page_title="Safe Web Data Extractor",
    layout="wide",
    page_icon="🕸️"
)

st.title("🕸️ Web Scraper & Data Extractor (Safe, Reproducible)")
st.markdown("""
This tool extracts **title**, **price**, **availability**, and **specifications** from pages or HTML snapshots.
""")

# ------------------- Sidebar Options -------------------
with st.sidebar:
    st.header("⚙️ Options")
    use_live = st.checkbox("Enable live fetch (requests)", value=False)
    use_llm_inference = st.checkbox("Use Gemini AI for selector inference", value=False)
    db_save = st.checkbox("Save snapshots to SQLite", value=True)
    show_raw_html = st.checkbox("Show raw HTML (for debugging)", value=False)
    st.markdown("---")
    st.caption("If live fetch is disabled, use local HTML files or snapshots.")
    st.markdown("---")

# ------------------- Input Section -------------------
st.subheader("🧾 Input URLs or Upload Snapshots")
urls_text = st.text_area(
    "Enter one or more URLs (comma or newline separated):",
    placeholder="https://example.com/product1, https://example.com/product2",
    height=120
)

uploaded_files = st.file_uploader(
    "Or upload HTML snapshots (.html, .htm)",
    accept_multiple_files=True,
    type=["html", "htm"]
)

# NOTE: CSS selector manual override removed per request.
# We'll send an empty mapping to the backend so heuristics/Gemini handle selector logic.

# ------------------- Run Extraction -------------------
run = st.button("🚀 Run Extraction")
st.markdown("---")

if run:
    st.info("Running extraction via FastAPI backend... please wait.")
    results = []
    inputs = []

    # -------- URL Parsing (supports newline + comma mixed) --------
    if urls_text.strip():
        raw_parts = [p.strip() for part in urls_text.splitlines() for p in part.split(",")]
        clean_urls = [u for u in dict.fromkeys(raw_parts) if u]
        if clean_urls:
            st.info(f"Detected {len(clean_urls)} unique URLs to extract:")
            st.code("\n".join(clean_urls))
            for u in clean_urls:
                inputs.append(("url", u))

    # -------- Uploaded files --------
    if uploaded_files:
        for file in uploaded_files:
            html = file.read().decode("utf-8", errors="replace")
            inputs.append(("upload", (file.name, html)))

    if not inputs:
        st.warning("Please provide at least one URL or upload an HTML file.")
    else:
        for typ, payload in inputs:
            src = html = ""
            if typ == "url":
                src = payload
                html = None
            else:
                src, html = payload

            payload_data = {
                "url": src if typ == "url" and use_live else None,
                "html": html if typ != "url" else None,
                "use_llm": use_llm_inference,
                "mapping": {},  # no manual selectors provided
            }

            try:
                response = requests.post(f"{API_URL}/extract", json=payload_data, timeout=60)
                res = response.json()
                if res.get("status") == "ok":
                    data = res["data"]
                    data["_source"] = src
                    results.append(data)
                else:
                    st.error(f"❌ {res.get('message')}")
            except Exception as e:
                st.error(f"Backend error: {e}")

        if results:
            # Build DataFrame without flattening nested specs
            df = pd.DataFrame(results)

            # Combine specs dictionary into one readable cell
            def combine_specs(specs):
                if isinstance(specs, dict) and len(specs) > 0:
                    parts = [
                        f"{k}: {v}"
                        for k, v in specs.items()
                        if v and not str(v).lower().startswith("none")
                    ]
                    return ", ".join(parts)
                return ""

            if "specs" in df.columns:
                df["specs"] = df["specs"].apply(combine_specs)

                # Move 'specs' column to the end for neatness
                cols = [c for c in df.columns if c != "specs"] + ["specs"]
                df = df[cols]

            st.success(f"✅ Extracted {len(results)} records successfully.")
            st.dataframe(df, use_container_width=True)

            # Download buttons
            col1, col2 = st.columns(2)
            col1.download_button(
                label="💾 Download JSON",
                data=json.dumps(results, indent=2, ensure_ascii=False),
                file_name="extracted.json",
                mime="application/json"
            )
            col2.download_button(
                label="📊 Download CSV",
                data=df.to_csv(index=False).encode("utf-8"),
                file_name="extracted.csv",
                mime="text/csv"
            )

            # Inspect single record (JSON preview)
            st.markdown("---")
            st.subheader("🔍 Inspect Single Record")
            idx = st.number_input("Select record index", 0, len(results) - 1, 0)
            st.json(results[int(idx)])
        else:
            st.warning("No results extracted.")

# ------------------- Footer -------------------
st.markdown("---")
st.markdown("""
### 🧭 Notes & Best Practices
- Always check `robots.txt` and website TOS before scraping.  
- Store and reuse snapshots for reproducible results.  
- For production, add rate limiting, retry logic, and proxy rotation.  
- Use Gemini AI only for research or permitted extraction.  
""")
