#!/usr/bin/env python3
"""
rhp_link.py — connect a downloaded RHP folder to an ipo id. The missing link.

THE PROBLEM
  The SEBI downloader saves rhps/<company-slug>/. The database identifies IPOs by
  number. Nothing joins them, so drive.py reports "no local PDF mapped in
  rhp_map.json" for every IPO and the extraction step can never fire — leaving
  documents.<rows> as the last missing column almost everywhere.

TWO TIERS, CHEAPEST FIRST
  Tier 1 (FREE): pull the ISIN off the cover pages and resolve it against ipo.isin.
      An ISIN is an exact identifier — no name matching, no fuzziness, no judgement.
      Now viable because nse_fetch writes metaInfo.isin to the spine.
  Tier 2 (PAID, opt-in --identify, ~$0.01/PDF): only for PDFs Tier 1 could not place.
      One small Sonnet call over the cover pages asking for ONLY the issuer name and
      ISIN. Used because reading the cover with a regex FAILED BADLY: a cover page
      lists every intermediary in the deal, and the heuristic version returned
      "Axis Capital Limited", "JM Financial Limited", "KHAMBATTA SECURITIES LIMITED"
      as issuers and created six junk spine rows. A model reading the document will
      not confuse the issuer with its bankers.

NOTHING IS CREATED WITHOUT EVIDENCE
  A new spine row is written only when we have BOTH a name and an ISIN, and only with
  --create. Everything else is reported for you to decide.

  python rhp_link.py                      # Tier 1 only, report, writes nothing
  python rhp_link.py --write-map          # Tier 1 + save rhp_map.json
  python rhp_link.py --identify --write-map           # + paid identity for the rest
  python rhp_link.py --identify --create --write-map  # + create missing spine rows
"""
import os, sys, io, re, json, glob, argparse
if __name__ == "__main__":
    try: sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    except Exception: pass
import psycopg2

FILE_BUILD = "rhp_link 2026-08-01a — ISIN-first, Sonnet identity fallback"
RHP_DIR = "rhps"
MAP = "rhp_map.json"
COVER_PAGES = 10
IDENTIFY_COST = 0.012          # cover pages only: ~3K in + ~100 out

ISIN_RX = re.compile(r"\b(IN[A-Z0-9]{10})\b")
ISIN_LABELLED = re.compile(r"ISIN[^A-Z0-9]{0,25}(IN[A-Z0-9]{10})", re.I)


def valid_isin(code):
    """A real ISIN carries digits. 'INTERNATIONA' — the first 12 letters of
    'INTERNATIONAL Securities Identification Number' — carries none, and matched the
    naive pattern on the 08-01 run, producing isin='INTERNATIONA' on two spine rows."""
    return code and sum(ch.isdigit() for ch in code) >= 3


def find_isin(text):
    """Prefer a code beside the word ISIN; else a bare code that repeats.

    An RHP names peer and subsidiary ISINs too, so a first-match wins rule would happily
    adopt another company's identity. Returns (isin, how)."""
    labelled = [c for c in ISIN_LABELLED.findall(text or "") if valid_isin(c)]
    if labelled:
        best = max(set(labelled), key=labelled.count)
        return best.upper(), f"labelled x{labelled.count(best)}"
    bare = [c for c in ISIN_RX.findall(text or "") if valid_isin(c)]
    if bare:
        best = max(set(bare), key=bare.count)
        if bare.count(best) >= 2:
            return best.upper(), f"unlabelled x{bare.count(best)}"
    return None, "no reliable ISIN on the cover pages"


def cover_text(pdf, n=COVER_PAGES):
    import fitz
    doc = fitz.open(pdf)
    return "\n".join(doc[i].get_text() for i in range(min(n, len(doc)))), len(doc)


def identify_with_sonnet(text, api_key):
    """ONE small call: issuer name + ISIN, nothing else. Returns (name, isin, cost)."""
    import rhp_sonnet
    prompt = (
        "These are the cover pages of an Indian IPO Red Herring Prospectus.\n\n"
        "Return ONLY this JSON, no preamble, no markdown:\n"
        '{"issuer_name": "<the COMPANY OFFERING SHARES, exactly as printed>", '
        '"isin": "<its ISIN, or null>", '
        '"evidence": "<the verbatim line the issuer name came from, under 20 words>"}\n\n'
        "CRITICAL: the issuer is the company whose shares are being offered. A cover "
        "page also names Book Running Lead Managers (Axis Capital, JM Financial, IIFL, "
        "ICICI Securities, Kotak), the Registrar (KFin, MUFG Intime, Bigshare, Link "
        "Intime), legal counsel and bankers. NONE of those is the issuer. If you cannot "
        "tell which company is issuing, return null rather than guess.\n\n"
        "Return the ISIN only if it is the ISSUER's own ISIN, not a peer's.\n\nTEXT:\n"
        + text[:14000])
    out, itok, otok = rhp_sonnet.call_sonnet(
        "You identify the issuing company of an Indian IPO prospectus. You never confuse "
        "the issuer with its bankers, registrar or legal advisers.",
        prompt, api_key, max_tokens=300)
    cost = itok * rhp_sonnet.IN_RATE + otok * rhp_sonnet.OUT_RATE
    try:
        d = rhp_sonnet.parse_json(out)
    except Exception:
        return None, None, cost
    isin = (d.get("isin") or "").strip().upper() or None
    return (d.get("issuer_name") or None,
            isin if valid_isin(isin) else None,
            cost, d.get("evidence"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--write-map", action="store_true")
    ap.add_argument("--identify", action="store_true", help=f"PAID (~${IDENTIFY_COST}/PDF)")
    ap.add_argument("--create", action="store_true", help="create spine rows for new IPOs")
    ap.add_argument("--max-spend", type=float, default=0.20)
    a = ap.parse_args()

    if not os.path.isdir(RHP_DIR):
        sys.exit(f"no {RHP_DIR}/ directory")
    folders = sorted(d for d in os.listdir(RHP_DIR)
                     if os.path.isdir(os.path.join(RHP_DIR, d)))
    conn = psycopg2.connect(os.environ["DATABASE_URL"]); cur = conn.cursor()
    mapping = {}
    if os.path.exists(MAP):
        try: mapping = json.load(open(MAP, encoding="utf-8"))
        except Exception: mapping = {}
    already = set(mapping.values())

    print(f"  [build] {FILE_BUILD}")
    print(f"  {len(folders)} folder(s) · {len(mapping)} already mapped · "
          f"identify={'ON (paid)' if a.identify else 'off'}\n")

    key = os.environ.get("ANTHROPIC_API_KEY") if a.identify else None
    if a.identify and not key:
        sys.exit("--identify needs ANTHROPIC_API_KEY")
    spent = 0.0
    linked = created = unresolved = 0

    for folder in folders:
        if folder in already:
            print(f"  [MAPPED] {folder:32} already linked"); continue
        pdfs = glob.glob(os.path.join(RHP_DIR, folder, "*.pdf"))
        if not pdfs:
            print(f"  [NO PDF] {folder:32}"); continue
        try:
            text, npages = cover_text(pdfs[0])
        except Exception as e:
            print(f"  [FAIL]   {folder:32} {type(e).__name__}"); continue

        # ---- Tier 1: free ISIN match ----
        isin, how = find_isin(text)
        row = None
        if isin:
            cur.execute("SELECT id, name_display FROM ipo WHERE isin=%s", (isin,))
            row = cur.fetchone()
        if row:
            print(f"  [LINK]   {folder:32} -> id={row[0]:<5} {str(row[1])[:32]:34} "
                  f"(isin {isin}, {how})")
            mapping[str(row[0])] = folder; linked += 1; continue

        # ---- Tier 2: paid identity, only if asked ----
        if not a.identify:
            print(f"  [UNRESOLVED] {folder:28} isin={isin or '(none)'} ({how}) "
                  f"— rerun with --identify to resolve")
            unresolved += 1; continue
        if spent + IDENTIFY_COST > a.max_spend:
            print(f"  [SKIP]   {folder:32} would exceed --max-spend ${a.max_spend}")
            unresolved += 1; continue

        name, sisin, cost, evidence = identify_with_sonnet(text, key)
        spent += cost
        print(f"  [ID]     {folder:32} name={str(name)[:34]!r} isin={sisin} "
              f"(${cost:.4f})")
        if evidence:
            print(f"           evidence: {str(evidence)[:80]}")
        if not name:
            print("           could not identify the issuer — left alone")
            unresolved += 1; continue

        # resolve again with what the model found
        row = None
        if sisin:
            cur.execute("SELECT id, name_display FROM ipo WHERE isin=%s", (sisin,))
            row = cur.fetchone()
        if not row:
            from fill_ipo import _norm
            cur.execute("SELECT id, name_display FROM ipo WHERE name_norm=%s", (_norm(name),))
            row = cur.fetchone()
        if row:
            print(f"           -> id={row[0]} {str(row[1])[:34]}")
            mapping[str(row[0])] = folder; linked += 1; continue

        if not a.create:
            print(f"           NEW IPO (not in the spine) — rerun with --create to add")
            unresolved += 1; continue
        if not sisin:
            print(f"           NEW but NO ISIN — not created (identity would be name-only)")
            unresolved += 1; continue
        from fill_ipo import upsert_ipo, _norm
        ipo_id, action = upsert_ipo(conn, dict(isin=sisin, name_display=name,
                                               name_norm=_norm(name), is_mainboard=True,
                                               status="announced"), source="rhp")
        print(f"           -> spine row {action}: id={ipo_id}")
        mapping[str(ipo_id)] = folder; created += 1

    if a.write_map:
        json.dump(mapping, open(MAP, "w", encoding="utf-8"), indent=2)
        print(f"\n  {MAP} now maps {len(mapping)} IPOs")
    print(f"\n  done. {linked} linked · {created} spine rows created · "
          f"{unresolved} unresolved · spent ${spent:.4f}"
          + ("" if a.write_map else "   (map NOT saved — pass --write-map)"))
    conn.close()


if __name__ == "__main__":
    main()
