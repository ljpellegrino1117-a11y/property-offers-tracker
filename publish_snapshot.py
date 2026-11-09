#!/usr/bin/env python3
"""Regenerate the public Property Offer Tracker snapshot (index.html) from a
raw `listproperties` export of the property-offer-tracker artifact, sanitize
it for public display, audit it, and optionally push it to the public GitHub
repo (Pages source: main branch, root).

Usage:
  python3 publish_snapshot.py <raw-listproperties.json> [--push]

The raw export is the JSON returned by the artifact action `listproperties`
(the full {"data": {...}} tool output or just the data object). It is NEVER
published: only the sanitized index.html leaves this machine.

Sanitization (Louis's display rule + public-page privacy):
  - Whitelist fields only. Dropped: agentName, agentPhone (personal contact
    details), lastContact, nextStep, standing, listingNote, cocSummary
    (internal narrative / process labels), offerCeiling (negotiating limit),
    uw* underwriting-input JSON, internal ids.
  - listingUrl query strings are stripped (one board URL embeds an MLS
    number in a uniqueListingId parameter).
  - Deadline rows keep propertyLabel/title/dueDate/status/workstream only;
    detail and owner are dropped.
  - A final regex audit fails the build if any phone number, email address,
    MLS number, file path, or message/run id pattern survives in the HTML.
"""
from __future__ import annotations

import html
import json
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

HERE = Path(__file__).resolve().parent
OWNER = "ljpellegrino1117-a11y"
REPO = "property-offers-tracker"
GH_API = Path.home() / "workspace/custom-connectors/custom.legacy-github/bin/gh-api"

STATUS_ORDER = ["offer_out", "under_contract", "decision_needed", "evaluating", "passed"]
STATUS_LABEL = {
    "offer_out": "Offers out",
    "under_contract": "Under contract",
    "decision_needed": "Decision needed",
    "evaluating": "Evaluating",
    "passed": "Passed / closed",
}
DL_LABEL = {"open": "Open", "gap": "Needs attention", "done": "Done"}

PHONE_RE = re.compile(r"\(?\d{3}\)?[\s.\-]\d{3}[\s.\-]\d{4}")
EMAIL_RE = re.compile(r"[\w.\-]+@[\w.\-]+\.[A-Za-z]{2,}")
MLS_RE = re.compile(r"\bMLS\b|\buniqueListingId\b")
PATH_RE = re.compile(r"/home/hatch|~/workspace|\.md\b|\.json\b")
ID_RE = re.compile(r"\b1a[0-9a-f]{10,}\b|\bmsg [0-9a-f\-]{8,}\b|routine_runs|cron")


def fail(msg: str) -> None:
    print(f"AUDIT FAILED: {msg}", file=sys.stderr)
    sys.exit(1)


def clean_url(url: str | None) -> str | None:
    if not url:
        return None
    return url.split("?")[0]


def money(v) -> str | None:
    if v is None:
        return None
    return f"${v:,.0f}"


def fmt_date(iso: str | None, with_time: bool = False) -> str | None:
    if not iso:
        return None
    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
    except ValueError:
        return iso
    et = dt.astimezone(ZoneInfo("America/New_York"))
    if with_time:
        return et.strftime("%b %-d, %Y · %-I:%M %p ET")
    return et.strftime("%b %-d, %Y")


def sanitize(data: dict) -> dict:
    props = []
    for p in data.get("properties", []):
        props.append({
            "address": p.get("address"),
            "city": p.get("city"),
            "status": p.get("status"),
            "rank": p.get("rank"),
            "askPrice": p.get("askPrice"),
            "offerPrice": p.get("offerPrice"),
            "unitsBeds": p.get("unitsBeds"),
            "bestUse": p.get("bestUse"),
            "cocInPlace": p.get("cocInPlace"),
            "cocMarket": p.get("cocMarket"),
            "cocLuxury": p.get("cocLuxury"),
            "returnsNote": p.get("returnsNote"),
            "rents": p.get("rents"),
            "taxes": p.get("taxes"),
            "earnest": p.get("earnest"),
            "sellerCredit": p.get("sellerCredit"),
            "terms": p.get("terms"),
            "expiresAt": p.get("expiresAt"),
            "closeDate": p.get("closeDate"),
            "listingUrl": clean_url(p.get("listingUrl")),
        })
    dls = []
    for d in data.get("deadlines", []):
        dls.append({
            "propertyLabel": d.get("propertyLabel"),
            "title": d.get("title"),
            "dueDate": d.get("dueDate"),
            "status": d.get("status"),
            "workstream": d.get("workstream"),
        })
    return {"properties": props, "deadlines": dls,
            "lastRefreshAt": data.get("lastRefreshAt")}


def audit(page: str) -> None:
    for name, rx in [("phone", PHONE_RE), ("email", EMAIL_RE), ("MLS", MLS_RE),
                     ("file path", PATH_RE), ("internal id", ID_RE)]:
        m = rx.search(page)
        if m:
            fail(f"{name} pattern survived in output: ...{page[max(0,m.start()-40):m.end()+40]!r}...")


def esc(v) -> str:
    return html.escape(str(v)) if v is not None else ""


def card(p: dict) -> str:
    rows = []
    ask, offer = money(p["askPrice"]), money(p["offerPrice"])
    if ask:
        rows.append(f"<div class='row'><span>Ask</span><b>{ask}</b></div>")
    if offer:
        rows.append(f"<div class='row'><span>Our offer</span><b>{offer}</b></div>")
    if p["unitsBeds"]:
        rows.append(f"<div class='row'><span>Units / beds</span><b>{esc(p['unitsBeds'])}</b></div>")
    exp = fmt_date(p["expiresAt"], with_time=True)
    if exp:
        label = "Offer expires" if p["status"] == "offer_out" else "Key date"
        rows.append(f"<div class='row'><span>{label}</span><b>{esc(exp)}</b></div>")
    cd = fmt_date(p["closeDate"])
    if cd:
        rows.append(f"<div class='row'><span>Closing</span><b>{esc(cd)}</b></div>")
    coc = []
    if p["cocInPlace"]:
        coc.append(f"<div class='coc'><span>In-place rent</span><p>{esc(p['cocInPlace'])}</p></div>")
    if p["cocMarket"]:
        coc.append(f"<div class='coc'><span>Market rent</span><p>{esc(p['cocMarket'])}</p></div>")
    if p["cocLuxury"]:
        coc.append(f"<div class='coc'><span>Luxury Lodging (STR)</span><p>{esc(p['cocLuxury'])}</p></div>")
    coc_html = f"<div class='cocgrid'>{''.join(coc)}</div>" if coc else ""
    extra = []
    for label, key in [("Rents", "rents"), ("Taxes", "taxes"), ("Earnest", "earnest"),
                       ("Seller credit", "sellerCredit"), ("Terms", "terms"),
                       ("Best use", "bestUse")]:
        if p[key]:
            extra.append(f"<p class='note'><b>{label}:</b> {esc(p[key])}</p>")
    if p["returnsNote"]:
        extra.append(f"<p class='note'><b>Returns:</b> {esc(p['returnsNote'])}</p>")
    link = ""
    if p["listingUrl"]:
        link = f"<p class='note'><a href='{esc(p['listingUrl'])}' rel='noopener'>Public listing</a></p>"
    rank = f" <span class='rank'>#{p['rank']}</span>" if p["rank"] else ""
    return (f"<article class='card'><h3>{esc(p['address'])}{rank}</h3>"
            f"<p class='city'>{esc(p['city'] or '')}</p>{''.join(rows)}{coc_html}"
            f"{''.join(extra)}{link}</article>")


def render(board: dict) -> str:
    props = board["properties"]
    counts = {s: sum(1 for p in props if p["status"] == s) for s in STATUS_ORDER}
    counts_line = " · ".join(
        f"{counts[s]} {STATUS_LABEL[s].lower()}" for s in STATUS_ORDER if counts[s])
    sections = []
    for s in STATUS_ORDER:
        group = [p for p in props if p["status"] == s]
        if not group:
            continue
        sections.append(
            f"<h2>{STATUS_LABEL[s]} ({counts[s]})</h2><div class='grid'>"
            + "".join(card(p) for p in group) + "</div>")
    open_dls = [d for d in board["deadlines"] if d["status"] != "done"]
    dl_rows = []
    for d in sorted(open_dls, key=lambda x: x["dueDate"] or "9999"):
        dl_rows.append(
            f"<tr><td>{esc(fmt_date(d['dueDate']) or '')}</td>"
            f"<td>{esc(d['propertyLabel'] or '')}</td><td>{esc(d['title'] or '')}</td>"
            f"<td>{esc(d['workstream'] or '')}</td>"
            f"<td>{esc(DL_LABEL.get(d['status'], d['status']))}</td></tr>")
    dl_html = ""
    if dl_rows:
        dl_html = ("<h2>Under-contract deadlines</h2><table><thead><tr><th>Due</th>"
                   "<th>Property</th><th>Item</th><th>Workstream</th><th>Status</th>"
                   "</tr></thead><tbody>" + "".join(dl_rows) + "</tbody></table>")
    refreshed = fmt_date(board.get("lastRefreshAt"), with_time=True) or ""
    now_et = datetime.now(ZoneInfo("America/New_York")).strftime("%b %-d, %Y · %-I:%M %p ET")
    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Property Offer Tracker</title>
<style>
body{{font-family:-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;margin:0;background:#f6f7f9;color:#1c2430}}
header{{background:#12314e;color:#fff;padding:22px 20px}}
header h1{{margin:0 0 6px;font-size:22px}} header p{{margin:2px 0;opacity:.85;font-size:14px}}
main{{max-width:1180px;margin:0 auto;padding:18px 16px 40px}}
h2{{font-size:17px;margin:26px 0 12px;color:#12314e}}
.grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(340px,1fr));gap:14px}}
.card{{background:#fff;border:1px solid #dde3ea;border-radius:10px;padding:14px 16px}}
.card h3{{margin:0;font-size:16px}} .rank{{color:#8a94a6;font-weight:600}}
.city{{margin:2px 0 10px;font-size:13px;color:#5b6678}}
.row{{display:flex;justify-content:space-between;border-top:1px solid #eef1f5;padding:6px 0;font-size:14px}}
.row span{{color:#5b6678}} .cocgrid{{margin-top:10px;display:grid;gap:8px}}
.coc{{background:#f0f4f8;border-radius:8px;padding:8px 10px}} .coc span{{font-size:12px;text-transform:uppercase;letter-spacing:.04em;color:#46617e}}
.coc p{{margin:3px 0 0;font-size:13.5px}}
.note{{font-size:13.5px;margin:8px 0 0}} a{{color:#1663b8}}
table{{width:100%;border-collapse:collapse;background:#fff;border:1px solid #dde3ea;border-radius:10px;overflow:hidden;font-size:14px}}
th,td{{text-align:left;padding:8px 10px;border-top:1px solid #eef1f5}} th{{background:#eef2f7;border-top:none}}
footer{{color:#5b6678;font-size:13px;text-align:center;padding:18px}}
</style></head><body>
<header><h1>Property Offer Tracker</h1>
<p>{esc(counts_line)} · {len(props)} properties total</p>
<p>Board data refreshed {esc(refreshed)} · Public snapshot generated {esc(now_et)}</p></header>
<main>{''.join(sections)}{dl_html}</main>
<footer>Illinois New Realty Holdings — acquisition pipeline snapshot. Figures are underwriting estimates, not guarantees.</footer>
</body></html>"""


def push(page: str) -> None:
    payload = {"index.html": page}
    for name, content in payload.items():
        body = {"message": f"Refresh tracker snapshot {datetime.now(ZoneInfo('America/New_York')).strftime('%Y-%m-%d %H:%M ET')}",
                "content": __import__("base64").b64encode(content.encode()).decode()}
        # include sha when the file already exists
        import os
        env = dict(os.environ, PYTHONPATH="/opt/muse/skills/custom-connector-setup/bin")
        chk = subprocess.run([sys.executable, str(GH_API), "GET",
                              f"repos/{OWNER}/{REPO}/contents/{name}"],
                             capture_output=True, text=True, env=env)
        if chk.returncode == 0:
            try:
                body["sha"] = json.loads(chk.stdout)["sha"]
            except Exception:
                pass
        tmp = HERE / ".push-body.json"
        tmp.write_text(json.dumps(body))
        out = subprocess.run([sys.executable, str(GH_API), "PUT",
                              f"repos/{OWNER}/{REPO}/contents/{name}",
                              "--data", f"@{tmp}"], capture_output=True, text=True, env=env)
        tmp.unlink(missing_ok=True)
        if out.returncode != 0:
            fail(f"push of {name} failed: {out.stdout} {out.stderr}")


def main() -> None:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    raw = json.loads(Path(args[0]).read_text())
    data = raw.get("data", raw)
    board = sanitize(data)
    page = render(board)
    audit(page)
    out_path = HERE / "index.html"
    out_path.write_text(page)
    print(f"index.html written ({len(page)} bytes), audit passed")
    if "--push" in sys.argv:
        push(page)
        print("pushed to GitHub")


if __name__ == "__main__":
    main()
