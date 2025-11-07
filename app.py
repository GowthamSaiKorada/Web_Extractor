# app.py
import streamlit as st
import pandas as pd
import json
import os
import sqlite3
from dotenv import load_dotenv
from extractor import (
    fetch_html,
    snapshot_to_db,
    extract_from_html,
    llm_infer_selectors,
    GEMINI_API_KEY
)

# Load environment variables (Gemini key, etc.)
load_dotenv()

DB_PATH = "snapshots.db"
SNAPSHOT_DIR = "snapshots"

# ------------------- Streamlit Page Config -------------------
st.set_page_config(
    page_title="Safe Web Data Extractor",
    layout="wide",
    page_icon="🕸️"
)

st.title("🕸️ Web Scraper & Data Extractor (Safe, Reproducible)")
st.markdown("""
This tool extracts **structured product data** (title, price, availability) from pages or snapshots.

**Features:**
- 📥 Accept URLs or HTML files  
- 🧠 Auto-detect CSS selectors with *Gemini AI* (optional)  
- ⚙️ Manual selector override  
- 💾 SQLite snapshot storage for reproducibility  
- 📤 Export to JSON / CSV
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
    "Enter one or more URLs (one per line):",
    placeholder="https://example.com/product1\nhttps://example.com/product2",
    height=120
)

uploaded_files = st.file_uploader(
    "Or upload HTML snapshots (.html, .htm)",
    accept_multiple_files=True,
    type=["html", "htm"]
)

# ------------------- CSS Selector Mapping -------------------
st.subheader("🎯 CSS Selectors (Optional Manual Override)")
st.caption("Leave blank to let Gemini or built-in heuristics infer automatically.")

col1, col2, col3 = st.columns(3)
mapping_input = {
    "title": col1.text_input("Title Selector", value=""),
    "price": col2.text_input("Price Selector", value=""),
    "availability": col3.text_input("Availability Selector", value="")
}

# ------------------- Snapshot Selector -------------------
os.makedirs(SNAPSHOT_DIR, exist_ok=True)
snapshots = [f for f in os.listdir(SNAPSHOT_DIR) if f.endswith((".html", ".htm"))]
chosen_snapshot = None
if snapshots:
    chosen_snapshot = st.selectbox("Or select a saved snapshot from folder:", ["(none)"] + snapshots)

# ------------------- Run Extraction Button -------------------
run = st.button("🚀 Run Extraction")
st.markdown("---")

if run:
    st.info("Running extraction... please wait.")
    inputs = []

    # Collect URLs
    if urls_text.strip():
        for line in urls_text.splitlines():
            line = line.strip()
            if line:
                inputs.append(("url", line))

    # Collect uploaded files
    if uploaded_files:
        for file in uploaded_files:
            html = file.read().decode("utf-8", errors="replace")
            inputs.append(("upload", (file.name, html)))

    # Collect chosen snapshot
    if chosen_snapshot and chosen_snapshot != "(none)":
        path = os.path.join(SNAPSHOT_DIR, chosen_snapshot)
        with open(path, "r", encoding="utf-8") as f:
            html = f.read()
        inputs.append(("snapshot", (chosen_snapshot, html)))

    if not inputs:
        st.warning("Please provide at least one URL, upload, or snapshot.")
    else:
        results = []
        for typ, payload in inputs:
            html = ""
            src = ""

            # --------------- Fetch or Load HTML ---------------
            if typ == "url":
                url = payload
                if not use_live:
                    st.warning(f"Skipping live fetch (disabled): {url}")
                    continue
                try:
                    final_url, html = fetch_html(url)
                    src = final_url
                    if db_save:
                        snapshot_to_db(DB_PATH, final_url, html)
                    if show_raw_html:
                        with st.expander(f"Raw HTML for {final_url}"):
                            st.code(html[:3000])
                except Exception as e:
                    st.error(f"❌ Failed to fetch {url}: {e}")
                    continue
            elif typ in ("upload", "snapshot"):
                name, html = payload
                src = name

            # --------------- Optional LLM Inference ---------------
            mapping = mapping_input.copy()
            if use_llm_inference and GEMINI_API_KEY:
                st.info(f"🤖 Using Gemini AI to infer selectors for {src} ...")
                inferred = llm_infer_selectors(html, GEMINI_API_KEY)
                if inferred:
                    for key in ["title", "price", "availability"]:
                        if inferred.get(key):
                            mapping[key] = inferred[key]
                    st.success(f"Gemini suggested selectors: {inferred}")
                else:
                    st.warning("Gemini could not infer selectors. Falling back to heuristics.")

            # --------------- Extract Data ---------------
            try:
                extracted = extract_from_html(html, mapping)
                extracted["_source"] = src
                results.append(extracted)
            except Exception as e:
                st.error(f"Extraction error for {src}: {e}")

        # --------------- Display Results ---------------
        if results:
            df = pd.json_normalize(results)
            st.success(f"✅ Extracted {len(results)} records successfully.")
            st.dataframe(df)

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

            # Single record viewer
            st.markdown("---")
            st.subheader("🔍 Inspect Single Record")
            idx = st.number_input("Select record index", 0, len(results) - 1, 0)
            st.json(results[int(idx)])

# ------------------- Sidebar Snapshot DB Viewer -------------------
with st.sidebar:
    st.markdown("---")
    if st.button("📜 Show Last 20 Snapshots (SQLite)"):
        try:
            conn = sqlite3.connect(DB_PATH)
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS snapshots (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    url TEXT,
                    domain TEXT,
                    fetched_at TEXT,
                    html TEXT
                )
                """
            )
            conn.commit()
            df_snap = pd.read_sql_query(
                "SELECT id, url, domain, fetched_at FROM snapshots ORDER BY id DESC LIMIT 20",
                conn
            )
            st.dataframe(df_snap)
            conn.close()
        except Exception as e:
            st.error(f"Error loading snapshots: {e}")

# ------------------- Footer -------------------
st.markdown("---")
st.markdown("""
### 🧭 Notes & Best Practices
- Always check `robots.txt` and website TOS before scraping.  
- Store and reuse snapshots for reproducible results.  
- For production, add rate limiting, retry logic, and proxy rotation.  
- Use Gemini AI only for research or permitted extraction.  
""")
