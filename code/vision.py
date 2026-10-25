"""Image + scanned-PDF fact extraction via the LLM backend.

Each media file is sent once; the extracted records are cached as committed JSON
under code/vision_data/<file_id>.json (a committed data folder that ships in
code.zip), so the main pipeline reads the cache and
never needs the API at run time. Records use the same schema as evidence.py.

Run once after setting GEMINI_API_KEY:  python code/vision.py
"""
import csv
import json
from pathlib import Path

from loaders import REPO, DATASET, norm_email, _digits, Identity
import evidence
import llm

CACHE_DIR = REPO / "code" / "vision_data"
_IMG = {".png", ".jpg", ".jpeg"}
_SCANNED_PDF = {"evidence_18", "evidence_58"}  # business artifacts, not the policy PDFs

_PROMPT = """Transcribe the customer-data records VISIBLE in this screenshot or scanned
document (a data-deletion audit artifact). Only report text you can actually read in
the image. Never output an example or placeholder; if you cannot read a value, use null.
If the image shows no customer-data record or identifier, return exactly [].

A resource id, when visible, is a word like account_, search_, analytics_, support_,
export_, data_flow_, backup_, audit_record_, tombstone_, marketing_, or object_
followed by the exact digits shown. Copy the digits exactly; do not guess them.

Return ONLY a JSON array. Each element, using only values literally shown:
{"resource_id": <string or null>, "email": <string or null>, "phone": <string or null>,
 "name": <string or null>, "user_id": <string or null>,
 "present": <true if the record/account exists, false if marked deleted/not found, else true>,
 "enabled": <true/false for a data flow/connector, else null>,
 "restore_allowed": <true/false for a backup/restore entry, else null>,
 "identifiable": <true if direct identifiers (email/phone/name) are shown, false if
   anonymized/redacted, else null>}"""


def _targets():
    for row in evidence.load_manifest():
        suf = Path(row["file_path"]).suffix.lower()
        if suf in _IMG or row["file_id"] in _SCANNED_PDF:
            yield row


def _media_bytes(path):
    """Bytes + mime to send for one media file. A scanned PDF has no text layer for the
    model to read as a file, so render every page to PNG at 200 DPI and stack them
    vertically into ONE image — keeping each page's text (a resource_id is often on a
    later page than the identity) together in a single request so one record can carry
    both. PyMuPDF/Pillow are imported lazily here only, so the offline pipeline
    (load_vision_records) never needs them."""
    suf = path.suffix.lower()
    if suf != ".pdf":
        return path.read_bytes(), ("image/jpeg" if suf in (".jpg", ".jpeg") else "image/png")
    import io
    import pymupdf
    from PIL import Image
    pages = []
    for page in pymupdf.open(path):
        pages.append(Image.open(io.BytesIO(page.get_pixmap(dpi=200).tobytes("png"))).convert("RGB"))
    combined = Image.new("RGB", (max(p.width for p in pages), sum(p.height for p in pages)), "white")
    y = 0
    for p in pages:
        combined.paste(p, (0, y))
        y += p.height
    buf = io.BytesIO()
    combined.save(buf, format="PNG")
    return buf.getvalue(), "image/png"


def extract_all(backend):
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    for row in _targets():
        fid = row["file_id"]
        cache = CACHE_DIR / f"{fid}.json"
        if cache.exists():
            continue
        path = DATASET / row["file_path"]
        if not path.exists():
            continue
        img, mime = _media_bytes(path)
        text = backend.generate(_PROMPT, image_bytes=img, mime=mime, kind="vision")
        if text is None:  # API error -> skip (don't cache), retry on a later run
            print(f"  {fid}: skipped (API unavailable)")
            continue
        recs = _parse(text)
        cache.write_text(json.dumps(recs, indent=2), encoding="utf-8")
        print(f"  {fid}: {len(recs)} records")


def _parse(text):
    text = text.strip()
    if text.startswith("```"):
        text = text.split("```")[1].lstrip("json").strip()
    try:
        return json.loads(text)
    except Exception:
        return []


def _dataset_resource_ids():
    """Every resource_id the dataset actually references (global activity stream)."""
    rids = set()
    with open(DATASET / "system_activity.csv", newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if row.get("resource_id"):
                rids.add(row["resource_id"])
    return rids


def load_vision_records():
    """Cached vision facts as evidence-schema records (offline, no API).

    Strict validation: a record is kept only if its resource_id is a real dataset
    resource; each identifier is kept only if it resolves to a known user, else it
    is dropped. This prevents model hallucinations from creating false links."""
    out = []
    if not CACHE_DIR.exists():
        return out
    known_rids = _dataset_resource_ids()
    idn = Identity()
    known_names = {v["name"].lower() for v in idn.users.values() if v.get("name")}
    meta = {r["file_id"]: r["captured_at"] for r in evidence.load_manifest()}
    for cache in CACHE_DIR.glob("*.json"):
        fid = cache.stem
        for item in json.loads(cache.read_text(encoding="utf-8")):
            rid = item.get("resource_id")
            if not rid or rid not in known_rids:  # drop hallucinated/irrelevant resources
                continue
            rec = evidence._blank_record(fid, meta.get(fid, ""), rid)
            if item.get("email"):
                e = norm_email(item["email"])
                if idn.resolve(e):  # keep only an email that maps to a real user
                    rec["email"] = e
            if item.get("phone"):
                p = _digits(str(item["phone"]))
                if p and idn.phone_to_user.get(p):
                    rec["phone"] = p
            if item.get("name"):
                n = str(item["name"]).strip().lower()
                if n in known_names:
                    rec["name"] = n
            if item.get("user_id") and item["user_id"] in idn.users:
                rec["user_id"] = item["user_id"]
            if item.get("present") is False:
                rec["exists"] = False
            rec["enabled"] = item.get("enabled")
            rec["restore_allowed"] = item.get("restore_allowed")
            rec["identifiable"] = item.get("identifiable")
            out.append(rec)
    return out


if __name__ == "__main__":
    backend = llm.get_backend()
    if backend is None:
        print("No GEMINI_API_KEY configured (.env). Skipping vision extraction.")
    else:
        print(f"Extracting with {backend.provider}/{backend.model} ...")
        extract_all(backend)
        print(f"Cache: {CACHE_DIR}")
