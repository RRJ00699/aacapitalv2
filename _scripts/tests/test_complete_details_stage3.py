from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
def read(p): return (ROOT/p).read_text(encoding="utf-8")
def test_details_route_is_kv_only():
 s=read('app/api/ipo/details/[isin]/route.ts'); assert 'kvStore' in s and 'readVersionedSnapshot' in s
 for forbidden in ('@neondatabase','lib/db','SqlClient','ipo-details\"'):
  assert forbidden not in s
def test_allowlist_is_exact_and_bounded():
 s=read('app/api/admin/snapshots/route.ts'); assert 'ipo-details:isin:[A-Z0-9]{12}:v1' in s
def test_evidence_is_not_silently_truncated():
 for p in ('lib/v2/ipo-details.ts','components/ipo/CompleteDetails.tsx'):
  s=read(p); assert '.slice(' not in s and ' LIMIT ' not in s.split('verified_evidence')[1]
def test_latest_v2_score_and_document_identity():
 s=read('lib/v2/ipo-details.ts'); assert "engine_version LIKE 'v2-score-%'" in s and 'ORDER BY x.computed_at DESC LIMIT 1' in s
 for col in ('doc_type','url','sha256','page_count'): assert col in s
def test_visual_semantics_and_navigation():
 s=read('components/ipo/CompleteDetails.tsx'); assert 'AI analysis' in s and 'Verified excerpt, p.' in s
 assert 'Complete Details →' in read('components/ipo/IpoCard.tsx')
def test_stage3_sources_are_read_as_utf8_and_preserve_non_ascii_navigation():
 assert 'encoding="utf-8"' in Path(__file__).read_text(encoding="utf-8")
 assert '→' in read('components/ipo/IpoCard.tsx')
def test_uat_server_resolves_npx_on_windows_and_handles_spawn_errors():
 s=read('uat/serve.mjs')
 assert 'process.platform === "win32" ? "npx.cmd" : "npx"' in s
 assert 'child.on("error"' in s and 'process.exit(1)' in s
def test_explicit_honest_gaps():
 s=read('lib/v2/ipo-details.ts')
 for phrase in ('noOfSharesOffered','Not extracted into V2.','No maintained live source','2026-07-24'): assert phrase in s
