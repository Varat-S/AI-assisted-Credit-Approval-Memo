"""Files the user adds beside a 10-K (the Module 3 corporate-structure JSON, supporting files), through the
service and the New Analysis page. Offline: SEC EDGAR is the NVIDIA fixture."""

from __future__ import annotations

import json

import pytest
from lxml import html

from app.api import analysis as api
from app.services.acquisition import shared_filing
from tests.integration.test_bo_fo_combined import ACCESSION, FILED, FakeSec, client, loose, root  # noqa: F401

FOLDER = "NVDA 10-K FY2026"
STRUCTURE = {"schema_version": "1.0", "document_type": "corporate_structure_onboarding", "company_name": "NVIDIA",
             "data_status": "test_fixture", "corporate_tree": {
                 "id": "top", "name": "NVIDIA CORP", "role": "Parent Co", "is_guarantor": False, "children": [
                     {"id": "sub", "name": "NVIDIA Subsidiary", "role": "HoldCo", "is_guarantor": False,
                      "ownership_percent_from_parent": 100}]}}
GOOD = json.dumps(STRUCTURE).encode()
BAD = json.dumps({**STRUCTURE, "data_status": ""}).encode()


@pytest.fixture()
def sec(monkeypatch):
    monkeypatch.setattr(api, "_edgar_client", lambda session, user_agent: FakeSec())


def _section(response):
    return html.fromstring(response.text).xpath('//section[@id="add-evidence"]')[0]


# --- service ---------------------------------------------------------------------------------------------


def test_extra_files_sorts_the_structure_from_supporting_files():
    extras = shared_filing.extra_files({"Simplified NVDA Corp Structure.json": GOOD, "Notes 2026.pdf": b"%PDF"})
    assert extras == {shared_filing.M3_STRUCTURE: GOOD, "supporting/Notes_2026.pdf": b"%PDF"}
    assert shared_filing.extra_files({}, structure={"tree.json": GOOD}) == {shared_filing.M3_STRUCTURE: GOOD}


@pytest.mark.parametrize("files, structure, message", [
    ({}, {"tree.json": BAD}, "not a usable corporate-structure JSON"),
    ({}, {"tree.json": b"{not json"}, "not valid JSON"),
    ({}, {"tree.json": b'{"hello": 1}'}, "not a usable corporate-structure JSON"),
    ({"a.json": GOOD}, {"b.json": GOOD}, "More than one corporate-structure JSON"),
    ({"nvda-20260125.htm": b"<html/>"}, None, "looks like part of an SEC filing"),
    ({"filing.zip": b"PK"}, None, "looks like part of an SEC filing"),
    ({"company.json": b"{}"}, None, "written by the app"),
    ({"run.exe": b"MZ"}, None, "cannot be added"),
])
def test_extra_files_refuses_what_would_go_wrong_later(files, structure, message):
    with pytest.raises(shared_filing.SharedFilingError, match=message):
        shared_filing.extra_files(files, structure=structure)


def test_fetch_writes_the_extras_into_the_new_folder(root):
    extras = shared_filing.extra_files({"memo.pdf": b"%PDF"}, structure={"tree.json": GOOD})
    filing = shared_filing.fetch_filing(FakeSec(), "NVDA", fy=2026, extras=extras)
    assert (filing.folder / shared_filing.M3_STRUCTURE).read_bytes() == GOOD
    assert (filing.folder / "supporting" / "memo.pdf").is_file()
    assert shared_filing.m3_structure_path(filing.name).name == shared_filing.M3_STRUCTURE
    assert shared_filing.load_bundle(filing.name).primary_document  # the SEC bundle is untouched


def test_add_files_keeps_a_replaced_structure(root):
    shared_filing.fetch_filing(FakeSec(), "NVDA", fy=2026)
    old = root / FOLDER / "Simplified NVDA Corp Structure.json"
    old.write_bytes(GOOD)
    extras = shared_filing.extra_files({}, structure={"new.json": GOOD})
    with pytest.raises(shared_filing.SharedFilingError, match="already has a corporate-structure JSON"):
        shared_filing.add_files(FOLDER, extras)
    shared_filing.add_files(FOLDER, extras, replace_structure=True)
    assert not old.exists()
    assert [p.name.split("-", 1)[1] for p in (root / FOLDER / "supporting" / "superseded").iterdir()] == \
        ["Simplified_NVDA_Corp_Structure.json"]
    assert shared_filing.m3_structure_path(FOLDER).name == shared_filing.M3_STRUCTURE


# --- New Analysis page -------------------------------------------------------------------------------------


def test_download_with_a_corporate_structure(client, root, sec):
    listed = client.get("/analysis/new/reports", params={"ticker": "nvda", "user_agent": "t@example.com"})
    assert listed.status_code == 200
    form = _section(listed).xpath('.//form[@id="fetch-form"]')[0]
    assert form.get("enctype") == "multipart/form-data"
    assert form.xpath('.//input[@name="structure"]') and form.xpath('.//input[@name="supporting"]')
    fetched = client.post("/analysis/new/fetch", data={"ticker": "NVDA", "accession": ACCESSION,
                                                       "user_agent": "t@example.com"},
                          files=[("structure", ("NVDA Corp Structure.json", GOOD, "application/json")),
                                 ("supporting", ("Notes.pdf", b"%PDF", "application/pdf"))],
                          follow_redirects=False)
    assert fetched.status_code == 303, fetched.text
    assert (root / FOLDER / shared_filing.M3_STRUCTURE).read_bytes() == GOOD
    assert (root / FOLDER / "supporting" / "Notes.pdf").is_file()
    page = client.get(fetched.headers["location"])
    assert "Corporate structure: m3_corporate_structure.json" in page.text
    assert "Supporting files in supporting/: Notes.pdf" in page.text


def test_a_bad_structure_downloads_nothing_and_keeps_the_year_list(client, root, sec):
    response = client.post("/analysis/new/fetch", data={"ticker": "NVDA", "accession": ACCESSION,
                                                        "user_agent": "t@example.com"},
                           files=[("structure", ("tree.json", BAD, "application/json"))])
    assert response.status_code == 400
    section = _section(response)
    assert "data_status is required" in section.xpath('.//*[@id="edgar-errors"]')[0].text_content()
    assert "Nothing was downloaded" in response.text
    assert section.xpath(f'.//input[@name="accession"][@value="{ACCESSION}"][@checked]')  # still chosen
    assert not list(root.iterdir())


def test_download_needs_a_year_and_a_ticker(client, root, sec):
    assert "Enter a ticker" in client.get("/analysis/new/reports", params={"user_agent": "t@example.com"}).text
    missing = client.post("/analysis/new/fetch", data={"ticker": "NVDA", "user_agent": "t@example.com"})
    assert missing.status_code == 400 and "Pick the fiscal year" in missing.text


def test_upload_keeps_a_structure_picked_into_the_filing_box(client, root, loose):
    files = [("files", (p.name, p.read_bytes(), "application/octet-stream")) for p in sorted(loose.iterdir())]
    files.append(("files", ("Simplified NVDA Corp Structure.json", GOOD, "application/json")))
    uploaded = client.post("/analysis/new/import", files=files,
                           data={"accession": ACCESSION, "filing_date": FILED.isoformat()}, follow_redirects=False)
    assert uploaded.status_code == 303, uploaded.text
    assert (root / FOLDER / shared_filing.M3_STRUCTURE).read_bytes() == GOOD


def test_upload_without_the_filing_says_what_is_missing(client, root):
    response = client.post("/analysis/new/import", files=[("files", ("tree.json", GOOD, "application/json"))])
    assert response.status_code == 400 and "Choose the filing itself" in response.text
    assert _section(response).xpath('.//input[@name="evidence_mode"][@value="upload"][@checked]')


def test_add_files_to_a_saved_filing(client, root):
    shared_filing.fetch_filing(FakeSec(), "NVDA", fy=2026)
    page = client.get("/analysis/new", params={"add_folder": FOLDER})
    section = _section(page)
    assert section.xpath('.//input[@name="evidence_mode"][@value="add"][@checked]')
    assert section.xpath(f'.//select[@name="folder"]/option[@value="{FOLDER}"][@selected]')
    added = client.post("/analysis/new/add-files", data={"folder": FOLDER},
                        files=[("structure", ("tree.json", GOOD, "application/json"))], follow_redirects=False)
    assert added.status_code == 303
    assert "Corporate structure: m3_corporate_structure.json" in client.get(added.headers["location"]).text
    again = client.post("/analysis/new/add-files", data={"folder": FOLDER},
                        files=[("structure", ("tree.json", GOOD, "application/json"))])
    assert again.status_code == 400 and "already has a corporate-structure JSON" in again.text
    nothing = client.post("/analysis/new/add-files", data={"folder": FOLDER})
    assert nothing.status_code == 400 and "Choose at least one file" in nothing.text
