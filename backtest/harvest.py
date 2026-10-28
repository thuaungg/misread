"""Download the backtest letters and turn each PDF into the text the web app would see.

The text keeps **bold** runs and marks large lines as "## " headings, the same way
the browser's PDF reader in app/static/app.js does, so the skim reader gets the
same cues it would get on the site.

    python backtest/harvest.py          # download anything missing, re-extract all
"""
import json
import pathlib
import re
import statistics
import sys
import time
import urllib.request

import pdfplumber

HERE = pathlib.Path(__file__).resolve().parent
RAW, TEXT = HERE / "raw", HERE / "text"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
ISO = "https://isomer-user-content.by.gov.sg/"
IRS = "https://www.irs.gov/pub/notices/{}_english.pdf"
NHTSA = "https://static.nhtsa.gov/odi/rcl/{}/{}.pdf"

# (id, group, hard-case reason or "", url)
LETTERS = [
    # ---------------------------------------------------------------- Singapore: school letters
    ("sg_sembawang_open_01_2026", "sg", "", ISO + "769/835d41bd-fb41-4351-8c16-ff6626d0136c/Open_Letter_from_SLs_01_of_2026.pdf"),
    ("sg_sembawang_open_03_2026", "sg", "", ISO + "769/d20d0954-8f5c-4ef8-b43a-b8c501fc0421/Open_Letter_from_SLs_03_of_2026.pdf"),
    ("sg_sembawang_open_05_2025", "sg", "", ISO + "769/894d8b64-cd9c-42b2-a971-10353d4aa911/Open_Letter_from_SLs_05_2025_.pdf"),
    ("sg_sembawang_open_07_2025", "sg", "", ISO + "769/9cc1bd67-470d-4111-9a52-9898aea4bb90/Open_Letter_from_SLs_07_2025.pdf"),
    ("sg_serangoon_t1_2026", "sg", "21-page term letter, 7,234 words", ISO + "699/435b097b-8cbe-4eaf-ace6-cce1990dbfd2/2026_Term_1_Letter_to_Parents.pdf"),
    ("sg_clementi_t1_sec1", "sg", "", ISO + "820/cebfb690-30cf-41df-8367-1210d42997ff/Ps_letter__Term_1__2026_Sec_1.pdf"),
    ("sg_clementi_t1_sec3", "sg", "", ISO + "820/50dafb23-e25f-4db7-a3dd-1550dc45ac06/Ps_letter__Term_1__2026_Sec_3.pdf"),
    ("sg_clementi_t1_sec45", "sg", "", ISO + "820/d818421e-e16e-4141-9955-afc4bcaf6abe/Ps_letter__Term_1__2026_Sec_4_and_5.pdf"),
    ("sg_clementi_welcome_sec1", "sg", "", ISO + "820/59998162-9689-47bb-b869-6ffbc308610c/Ps_welcome_letter_for_Sec_1__2026_.pdf"),
    ("sg_fernvale_t1_2026", "sg", "", ISO + "710/6fe08147-c89b-422e-bee8-1e345313d2ca/2026_001_Letter_to_Parents_Term_1_Final.pdf"),
    ("sg_fernvale_p6_assess", "sg", "", ISO + "710/8f304c79-106a-4a4b-95e6-7be3b0aa6250/2026_P6_Term_2_Assessment_Letter.pdf"),
    ("sg_fernvale_p1_assess", "sg", "", ISO + "710/47016c13-528e-4874-9a5e-3ca0f87d1ddf/2026_P1_Semester_1_Assessment_Letter.pdf"),
    ("sg_henrypark_thrive_jan", "sg", "", ISO + "663/ad95124f-6b4f-4d92-b64e-4e43c08d1aa7/TH_R_I_V_E___Jan_2026.pdf"),
    ("sg_henrypark_thrive_apr", "sg", "", ISO + "663/618978a2-1f71-4d7f-a9d3-d99c144da0f6/TH_R_I_V_E___Apr_2026.pdf"),
    ("sg_yuneng_ltp_jan", "sg", "", ISO + "703/e7b9006e-356a-4f10-94f5-c9059ff40c4c/LTP_Jan_2026_.pdf"),
    ("sg_yuneng_lockdown_drill", "sg", "", ISO + "703/8e0886fc-c8dc-4db8-99e7-6c65ad315706/L054_2026_LTP_to_Parents___Emergency_Lockdown_Drill.pdf"),
    ("sg_yuneng_bcrs", "sg", "", ISO + "703/da42f94f-66c5-4bb4-add1-2bd56591506a/LTP_Implementation_of_the_Beverage_Container_Return_Scheme__BCRS__in_schools.pdf"),
    ("sg_yuneng_uniform", "sg", "", ISO + "703/1ede50d5-0c6b-4371-b469-eb5d0919b4c7/YNPS_Information_sheet_on_2026_School_Uniform.pdf"),
    ("sg_yuneng_ltp_mar", "sg", "", ISO + "703/fab4468a-dc10-4ba0-aa27-e38166da03ef/March_2026_LTP.pdf"),
    ("sg_yishun_canteen_hbl", "sg", "", ISO + "916/0394f286-899e-4733-bdcc-7e3f5552ed96/School_Canteen_Renovation_New_HBL_Mar_2026___11_Feb_2026.pdf"),
    ("sg_yishun_canteen_reminder", "sg", "", ISO + "916/1fa665bd-cd20-434a-8721-dbaf9bc1d947/Reminder_of_Canteen_Renovation___3_Mar_2026.pdf"),
    ("sg_yishun_sexuality_ed", "sg", "", ISO + "916/10e729cb-6fdb-4c96-9aa6-34010a7d1fcf/Sexuality_Education_2026___26_Jan_2026.pdf"),
    ("sg_yishun_olevel_results", "sg", "", ISO + "916/1f7ec9b4-5985-430d-b170-5837fe1a308f/GCE_O_Level_result_release_2026___8_Jan_2026.pdf"),
    ("sg_yishun_pld_consent", "sg", "", ISO + "916/50353342-1ea6-40e8-bddd-3b66b30cd6a5/YSS_Parental_Consent_for_Purchase_of_PLD_2026.pdf"),
    ("sg_yishun_echa", "sg", "", ISO + "916/168be63f-5788-407b-bfe5-2cecc85a11e3/Letter_to_Parent__ECHA___26_Aug_2024.pdf"),
    ("sg_yishun_new_year_2025", "sg", "", ISO + "916/1eacf1e0-93ac-4a7b-816a-8f654612b68d/New_Academic_Year_2025_Letter_to_Parents__27_Dec_2024_.pdf"),
    ("sg_yishun_smart_buddy", "sg", "", ISO + "916/03a123b0-34dd-456e-bad8-daefa46b2e6a/Smart_Buddy_Programme.pdf"),
    ("sg_yishun_cross_country", "sg", "", ISO + "916/1647f0ff-8619-4f94-a0e0-dbb992fe3651/yss-annual_cross-country_event-9may2023.pdf"),
    ("sg_yishun_hbl_jul2024", "sg", "", ISO + "916/48c207a0-a1d4-40ce-8786-5e55fcfdf8cf/HBL_on_11_Jul_2024___10_Jul_2024.pdf"),
    ("sg_yishun_pe_tshirt", "sg", "", ISO + "916/3fdd4575-3d17-468b-87b2-00e3d99ddb2a/YSS_PE_T_SHIRT_REFRESH_14_Aug_2024.pdf"),
    ("sg_zhangde_t1_desk", "sg", "", ISO + "677/9dd3e9be-f3f4-43fc-b75f-202901293bd3/1_Term_1_From_the_Desk_of_the_Principal_5th_Jan_2026.pdf"),
    ("sg_zhangde_t3", "sg", "", ISO + "677/995f2c62-7dfb-4535-8d29-d659426b7134/Term_3_2026_Principal_Letter.pdf"),
    ("sg_zhangde_t4", "sg", "", ISO + "677/d6dbf1fe-b7f5-4862-950c-2d2ef5118937/Term_4_2026_Principal_Letter_updated.pdf"),
    ("sg_bowen_ta1_sec45", "sg", "", ISO + "681/835b4fe1-4550-400b-bdee-0135f24ed161/2026__Letter_to_parents_TA1_Sec_4_5.pdf"),
    ("sg_moe_letter_to_parents", "sg", "", ISO + "588/a12c0c75-6f79-48dd-886f-0e46b4256bfc/Letter_to_Parents.pdf"),
    ("sg_yishun_handbook", "sg", "a 2-part parent handbook, not one letter", ISO + "916/19ebe407-a223-4bda-813c-8567ecb48ecf/IP2_3___Parent_Handbook__I_____II__2024.pdf"),
    ("sg_yishun_engagement_deck", "sg", "a slide deck, not a letter", ISO + "916/373adc84-3c48-4dc9-99f1-53a6fb079e43/YSS___Parent_Engagement_Deck_2025.pdf"),
    # ---------------------------------------------------------------- Singapore: agencies and companies
    ("sg_mom_ipa_employer", "sg", "", "https://www.mom.gov.sg/-/media/mom/documents/employment-agencies/ea-alerts/2016/0526-attachment-sample-enhanced-ipa-letter-for-employer.pdf"),
    ("sg_mom_ipa_helper", "sg", "Tamil text that extracts as garbage", "https://www.mom.gov.sg/-/media/mom/documents/employment-agencies/ea-alerts/2016/0526-attachment-sample-enhanced-ipa-letter-for-fdw.pdf"),
    ("sg_hdb_rent_approval", "sg", "two-column letter plus 4 pages of terms", "https://buycondo.sg/wp-content/uploads/2025/07/Approval-Letter-from-HDB-to-rent-example.pdf"),
    ("sg_hsa_fsn_endologix", "sg", "", ISO + "409/2aaf007c-2939-47ed-8e64-b830cbefc853/hsa-6004101-057-18-02_18-fsn_redacted.pdf"),
    ("sg_hsa_fsn_drager", "sg", "", ISO + "409/42cbbf53-5ba9-484a-accd-d36a71f77715/hsa-6004101-063-19-03_56-fsn_redacted.pdf"),
    ("sg_hsa_fsn_maquet", "sg", "technical notice for hospital engineers", ISO + "409/a03e50e0-702d-4a82-9c70-c1fae8ae68fb/hsa-6004101-081-18-02_52-fsn_redacted.pdf"),
    ("sg_hsa_fsn_endobarrier", "sg", "", ISO + "409/09469e04-a21a-4ea0-b3d1-eaf92f113641/hsa-6004101-263-15-01_11-fsn.pdf"),
    ("sg_hsa_fsn_terumo", "sg", "a company's letter template", ISO + "409/405583dc-abca-4c4e-b4ec-ec5c23c782df/hsa-6004101-155-19-02_37-fsn_redacted.pdf"),
    ("sg_hsa_recall_bd", "sg", "", ISO + "409/c70d3017-3d54-4f0d-8e44-9754b70db9ed/hsa-6004101-003-16-01_61-fsn7950e8c4ab864885abf278b56970f392.pdf"),
    ("sg_cccs_s68_notice", "sg", "scanned legal notice read by OCR", ISO + "1004/b0aa6be0-e0b1-4216-863f-bdba55d89946/idamip202320nov202011.pdf"),
    ("sg_customs_circular_06_2021", "sg", "", ISO + "174/784ed411-fa13-47f1-a3fb-231cf2130ac9/Circular_06_2021__Ver3_.pdf"),
    ("sg_ipos_consent_template", "sg", "blank template to print on letterhead", ISO + "61/bede010c-cb50-4eca-9acf-2546f46d2f9d/sample-letter-of-consent.pdf"),
    ("sg_customs_traveller_guide", "sg", "a long guide, not a letter", ISO + "174/810ade16-edc2-4cbb-a43c-e4308d0d58a9/guide-to-travellers-english-2022.pdf"),
    # ---------------------------------------------------------------- US: IRS sample notices
    *[(f"us_irs_{c}", "intl", "", IRS.format(c)) for c in
      ["cp01", "cp501", "cp503", "cp11", "cp13", "cp21a", "cp22a", "cp23", "cp24", "cp49", "cp53", "cp71c",
       "cp80", "cp88", "cp90", "cp161", "cp297", "cp566", "lt11", "cp59", "cp09", "cp27", "cp63", "cp14i", "cp180", "cp60"]],
    # ---------------------------------------------------------------- US: car recalls (owner letters, and dealer notices)
    ("us_nhtsa_ford_maverick", "intl", "", NHTSA.format(2024, "RCONL-24V330-6967")),
    ("us_nhtsa_ford_f150", "intl", "", NHTSA.format(2024, "RCONL-24V444-9268")),
    ("us_nhtsa_prevost", "intl", "", NHTSA.format(2024, "RCONL-24V893-2030")),
    ("us_nhtsa_ford_transit", "intl", "", NHTSA.format(2024, "RCONL-24V805-1237")),
    ("us_nhtsa_hyundai", "intl", "", NHTSA.format(2024, "RCONL-24V106-2024")),
    ("us_nhtsa_genesis", "intl", "", NHTSA.format(2024, "RCONL-24V282-6815")),
    ("us_nhtsa_2013_owner", "intl", "", NHTSA.format(2013, "RCONL-13V010-0123")),
    ("us_nhtsa_2012_owner", "intl", "", NHTSA.format(2012, "RCONL-12V454-0123")),
    ("us_nhtsa_dealer_20v124", "intl", "technical dealer bulletin, not for the owner", NHTSA.format(2020, "RCRN-20V124-0603")),
    ("us_nhtsa_dealer_20v036", "intl", "technical dealer bulletin, not for the owner", NHTSA.format(2020, "RCRN-20V036-7922")),
    ("us_nhtsa_dealer_20v714", "intl", "technical dealer bulletin, not for the owner", NHTSA.format(2020, "RCRN-20V714-9961")),
    # ---------------------------------------------------------------- US: health, debt, benefits
    ("us_cms_im_hospital", "intl", "", "https://lluh.org/sites/lluh.org/files/docs/patients-visitors/notices/An-Importat-Message-from-Medicare_20-1087C.pdf"),
    ("us_cms_abn_blank", "intl", "blank form with checkboxes", "https://www.healthcare.uiowa.edu/path_handbook/requisitions/abn_form.pdf"),
    ("us_irs_cp16", "intl", "", IRS.format("cp16")),
    ("us_irs_cp14_spanish", "intl", "the letter is in Spanish", "https://www.irs.gov/pub/notices/cp14_spanish.pdf"),
    ("us_ca_medical_noa_example", "intl", "", "https://www.calsaws.org/wp-content/uploads/2021/03/Non-MAGI_MAGI-Medi-Cal-NOA-Phase-3-Non-MAGI-APDN-MAGI-CHTN-Example-v1.pdf"),
    ("us_ca_na290_blank", "intl", "blank state form", "https://www.cdss.ca.gov/cdssweb/entres/forms/English/NA290.PDF"),
    ("us_ca_calfresh_ebt_blank", "intl", "blank state form", "https://www.cdss.ca.gov/cdssweb/entres/forms/English/TEMPNA1232.pdf"),
    # ---------------------------------------------------------------- UK
    ("uk_hmrc_tc_guide", "intl", "technical guide that contains a sample letter", "https://assets.publishing.service.gov.uk/government/uploads/system/uploads/attachment_data/file/517233/annex-b-technical-guide.pdf"),
    ("uk_tenant_information", "intl", "guidance for landlords, not a letter", "https://assets.publishing.service.gov.uk/media/699d8cbec497bac082bc7562/Written_information_that_must_be_given_to_tenants-_landlord_guidance.pdf"),
    ("uk_council_tax_letter", "intl", "", "https://assets.publishing.service.gov.uk/media/623991d98fa8f540f5c3c05f/220309_-_CTIL_Q_A_v2.pdf"),
    ("uk_mhra_fsn", "intl", "", "https://assets.publishing.service.gov.uk/media/5485aae7ed915d4c0d0001dd/con459440.pdf"),
    ("us_cms_im_instructions", "intl", "instructions for hospitals, not a letter to a patient", "https://data.nrhp.org/wp-content/uploads/2020/08/IM-instructions_final2020_Englishv508.pdf"),
    ("us_irs_cp10", "intl", "", IRS.format("cp10")),
]


def download(lid, url):
    out = RAW / f"{lid}.pdf"
    if out.exists() and out.stat().st_size > 1000 and out.read_bytes()[:4] == b"%PDF":
        return out, None
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=60) as r:
            data = r.read()
    except Exception as e:  # noqa: BLE001
        return None, f"download failed: {e}"
    if data[:4] != b"%PDF":
        return None, "not a PDF (the site sent a web page instead)"
    out.write_bytes(data)
    return out, None


def is_bold(fontname):
    return bool(re.search(r"bold|black|heavy|semibold|demi", fontname or "", re.I))


def extract(path):
    """PDF → text with **bold** and ## headings, like readPdf() in app.js."""
    pages = []
    with pdfplumber.open(path) as pdf:
        n_pages = len(pdf.pages)
        for page in pdf.pages:
            words = page.extract_words(extra_attrs=["fontname", "size"], keep_blank_chars=False, use_text_flow=False)
            if not words:
                continue
            body = statistics.median(w["size"] for w in words)
            rows = []
            for w in sorted(words, key=lambda w: (round(w["top"]), w["x0"])):
                row = next((r for r in rows if abs(r["top"] - w["top"]) < body * 0.45), None)
                if row is None:
                    rows.append(row := {"top": w["top"], "words": []})
                row["words"].append(w)
            rows.sort(key=lambda r: r["top"])
            lines, prev = [], None
            for r in rows:
                ws = sorted(r["words"], key=lambda w: w["x0"])
                if prev is not None and r["top"] - prev > body * 2.2:
                    lines.append("")
                prev = r["top"]
                runs = []
                for w in ws:
                    b = is_bold(w["fontname"])
                    if runs and runs[-1][0] == b:
                        runs[-1][1].append(w["text"])
                    else:
                        runs.append((b, [w["text"]]))
                text = " ".join(f"**{' '.join(t)}**" if b else " ".join(t) for b, t in runs)
                if statistics.mean(w["size"] for w in ws) > body * 1.25:
                    text = "## " + text.replace("**", "")
                lines.append(text)
            pages.append("\n".join(lines))
    text = "\n\n".join(pages)
    text = re.sub(r"\*\*\s*\*\*", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    return text, n_pages


def main():
    RAW.mkdir(exist_ok=True)
    TEXT.mkdir(exist_ok=True)
    manifest = []
    for lid, group, hard, url in LETTERS:
        path, err = download(lid, url)
        row = {"id": lid, "group": group, "hard": hard, "url": url}
        if err:
            row["error"] = err
        else:
            try:
                text, n = extract(path)
                (TEXT / f"{lid}.txt").write_text(text, encoding="utf-8")
                row.update(pages=n, words=len(text.split()))
            except Exception as e:  # noqa: BLE001
                row["error"] = f"could not read PDF: {e}"
        manifest.append(row)
        print(f"{lid:32s} {row.get('error') or str(row['pages']) + ' pages, ' + str(row['words']) + ' words'}", flush=True)
        time.sleep(0.2)
    (HERE / "manifest.json").write_text(json.dumps(manifest, indent=1), encoding="utf-8")
    ok = [m for m in manifest if "error" not in m]
    print(f"\n{len(ok)}/{len(manifest)} letters ready "
          f"(sg {sum(m['group'] == 'sg' for m in ok)}, intl {sum(m['group'] == 'intl' for m in ok)}, hard {sum(bool(m['hard']) for m in ok)})")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    main()
