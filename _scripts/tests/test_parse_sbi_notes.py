"""Unit tests for _scripts/parse_sbi_notes.py — hermetic, no real PDFs.

parse_pdf() does `import pdfplumber` at call time, so we inject a stub module
into sys.modules whose pages return saved fixture text + tables. This tests
the actual regex/table logic against a realistic SBI-note shape without a
binary fixture or a live source (roadmap Phase 2: parsers vs saved fixtures).
"""
import sys, types, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import pytest
from parse_sbi_notes import num, parse_pdf

pytestmark = pytest.mark.unit


# ---------- num ----------

@pytest.mark.parametrize("raw,expected", [
    ("1,234.5", 1234.5), (" 42 ", 42.0), ("0", 0.0),
    (None, None), ("", None), ("abc", None), ("12.3.4", None),
])
def test_num(raw, expected):
    assert num(raw) == expected


# ---------- pdfplumber stub ----------

class _Page:
    def __init__(self, text, tables): self._t, self._tb = text, tables
    def extract_text(self): return self._t
    def extract_tables(self): return self._tb

class _Pdf:
    def __init__(self, pages): self.pages = pages
    def __enter__(self): return self
    def __exit__(self, *a): return False

def _stub(monkeypatch, text, tables):
    fake = types.ModuleType("pdfplumber")
    fake.open = lambda path: _Pdf([_Page(text, tables)])
    monkeypatch.setitem(sys.modules, "pdfplumber", fake)


SBI_TEXT = """Kusumgar Ltd IPO
Price Band Rs 133 – 140 per share
Fresh Issue (Rs Cr) 500.00
Offer for Sale (Rs Cr) 250.00
Issue Size (Rs Cr) 750.00
QIB 50 % NII 15 % Retail 35 %
We recommend investors to SUBSCRIBE to the issue.
BRLMs SBI Capital Markets Limited Registrar Link Intime India Pvt Ltd
At the upper band the issue is valued at an annualized P/S of 4.2
"""

PEER_TABLE = [
    ["Particulars", "Kusumgar Ltd", "Peer Alpha Ltd", "Peer Beta Ltd", "Peer Gamma Ltd"],
    ["P/E (x)", "45.2", "38.0", "52.1", "-12.0"],
    ["P/S (x)", "5.0", "4.0", "6.0", "8.0"],
    ["RoNW %", "14.1", "12.0", "9.5", "11.0"],
]

# The trap #211's parser comment warns about: the subject's own multi-YEAR
# ratio table (no peers in header) must NOT be read as a peer table.
YEARLY_TABLE = [
    ["Particulars", "FY24", "FY25", "FY26"],
    ["P/E (x)", "60.0", "55.0", "45.2"],
]


def test_full_note_parse(monkeypatch, tmp_path):
    _stub(monkeypatch, SBI_TEXT, [YEARLY_TABLE, PEER_TABLE])
    rec = parse_pdf(str(tmp_path / "Kusumgar Ltd_IPO Note.pdf"))
    assert rec["company"] == "Kusumgar Ltd"
    assert rec["source"] == "SBI"
    assert rec["price_low"] == 133.0 and rec["price_high"] == 140.0
    assert rec["fresh_cr"] == 500.0 and rec["ofs_cr"] == 250.0
    assert rec["issue_size_cr"] == 750.0
    assert rec["qib_pct"] == 50 and rec["nii_pct"] == 15 and rec["retail_pct"] == 35
    assert rec["rating"] == "Subscribe"
    assert rec["registrar"] and "Link Intime" in rec["registrar"]
    assert rec["loss_making"] is False

def test_peer_median_excludes_negative_peer(monkeypatch, tmp_path):
    """P/E peers 38.0, 52.1, -12.0 → negative dropped → median (38+52.1)/2."""
    _stub(monkeypatch, SBI_TEXT, [PEER_TABLE])
    rec = parse_pdf(str(tmp_path / "Kusumgar Ltd_IPO Note.pdf"))
    assert rec["note_pe"] == 45.2
    assert rec["peer_pe"] == 45.05

def test_peer_ps_median_odd_count(monkeypatch, tmp_path):
    """P/S peers 4, 6, 8 → median 6."""
    _stub(monkeypatch, SBI_TEXT, [PEER_TABLE])
    rec = parse_pdf(str(tmp_path / "Kusumgar Ltd_IPO Note.pdf"))
    assert rec["peer_ps"] == 6.0

def test_peer_names_from_header(monkeypatch, tmp_path):
    _stub(monkeypatch, SBI_TEXT, [PEER_TABLE])
    rec = parse_pdf(str(tmp_path / "Kusumgar Ltd_IPO Note.pdf"))
    assert rec["peer_name"] == "Peer Alpha Ltd, Peer Beta Ltd, Peer Gamma Ltd"

def test_yearly_table_alone_yields_no_peers(monkeypatch, tmp_path):
    """Regression: the multi-YEAR ratio table must not be mistaken for peers."""
    _stub(monkeypatch, SBI_TEXT, [YEARLY_TABLE])
    rec = parse_pdf(str(tmp_path / "Kusumgar Ltd_IPO Note.pdf"))
    assert rec["peer_pe"] is None
    # note_ps falls back to the text regex ("annualized P/S of 4.2")
    assert rec["note_ps"] == 4.2

def test_wrong_company_table_skipped(monkeypatch, tmp_path):
    """A peer table whose header lacks the subject company is ignored."""
    other = [["Particulars", "Someone Else Ltd", "Peer X"], ["P/E (x)", "20", "30"]]
    _stub(monkeypatch, SBI_TEXT, [other])
    rec = parse_pdf(str(tmp_path / "Kusumgar Ltd_IPO Note.pdf"))
    assert rec["peer_pe"] is None

def test_company_name_from_filename_strips_ipo_note(monkeypatch, tmp_path):
    _stub(monkeypatch, "minimal", [])
    rec = parse_pdf(str(tmp_path / "Antony Waste Ltd_IPO Note.pdf"))
    assert rec["company"] == "Antony Waste Ltd"

def test_underscored_ipo_note_filename_not_stripped(monkeypatch, tmp_path):
    """Pinned fragility: 'IPO ?Note' does NOT match 'IPO_Note' — a fully
    underscored filename leaks 'IPO Note.pdf' into the company field.
    Safe today (downloader names files 'X Ltd_IPO Note.pdf') but this test
    documents the convention the parser depends on."""
    _stub(monkeypatch, "minimal", [])
    rec = parse_pdf(str(tmp_path / "Antony_Waste_IPO_Note.pdf"))
    assert rec["company"] == "Antony Waste IPO Note.pdf"

def test_hem_source_detection(monkeypatch, tmp_path):
    _stub(monkeypatch, "Research by Hem Securities Ltd. SUBSCRIBE", [])
    rec = parse_pdf(str(tmp_path / "X Ltd_IPO Note.pdf"))
    assert rec["source"] == "Hem"

def test_long_term_subscribe_not_truncated(monkeypatch, tmp_path):
    """Regex alternation order: LONG TERM SUBSCRIBE must win over SUBSCRIBE."""
    _stub(monkeypatch, "Our view: LONG TERM SUBSCRIBE at the upper band", [])
    rec = parse_pdf(str(tmp_path / "X Ltd_IPO Note.pdf"))
    assert rec["rating"] == "Long Term Subscribe"

@pytest.mark.parametrize("phrase", [
    "the company is yet to achieve profitability",
    "has incurred loss in FY25", "a loss-making entity",
])
def test_loss_making_detection(monkeypatch, tmp_path, phrase):
    _stub(monkeypatch, phrase, [])
    rec = parse_pdf(str(tmp_path / "X Ltd_IPO Note.pdf"))
    assert rec["loss_making"] is True

def test_single_positive_peer_is_its_own_median(monkeypatch, tmp_path):
    tbl = [["Particulars", "Kusumgar Ltd", "Only Peer"], ["P/E (x)", "45.2", "38.0"]]
    _stub(monkeypatch, SBI_TEXT, [tbl])
    rec = parse_pdf(str(tmp_path / "Kusumgar Ltd_IPO Note.pdf"))
    assert rec["peer_pe"] == 38.0

def test_all_peers_negative_yields_none(monkeypatch, tmp_path):
    tbl = [["Particulars", "Kusumgar Ltd", "P1", "P2"], ["P/E (x)", "45.2", "-5", "-8"]]
    _stub(monkeypatch, SBI_TEXT, [tbl])
    rec = parse_pdf(str(tmp_path / "Kusumgar Ltd_IPO Note.pdf"))
    assert rec["peer_pe"] is None
