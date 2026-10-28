# Where the example letters came from

Each example is a real public letter, in a different language. Text was extracted from the
original (PDF or web page); **bold** and larger text (marked `## `) were kept because the skim
view depends on them. The same details are shown on each example's page in the app and are
stored in [`sources.json`](sources.json).

| Language | Letter (`letters/<id>.md`) | Publisher | Source | Retrieved | Changes |
| --- | --- | --- | --- | --- | --- |
| English | Medicare notice: Your covered care is ending (NOMNC) (`cms_nomnc`) | Centers for Medicare & Medicaid Services | [link](https://www.atriohp.com/media/0h0kuhyc/form-cms-10123-nomnc-clean-fillable.pdf) | 2026-10-18 | Blank fields filled with made-up values: provider name, patient name and number, end date March 14, 2026, and the service type. |
| Indonesian | Indonesian school: trip payment (`id_talenta_livein_id`) | SMA Talenta, Bandung (Indonesia) | [link](https://www.talentaschool.sch.id/suratedaran/App/SuratDetail/870) | 2026-10-25 | Replaced the class teachers' names, their personal WhatsApp numbers and the bank account with sample values. |
| Russian | California EDD: prove your identity (`us_edd_id_ru`) | California Employment Development Department | [link](https://edd.ca.gov/siteassets/files/pdf_pub_ctr/de1326cr.pdf) | 2026-10-18 | Filled in the blank mailing date (09/15/2026) and effective date (09/06/2026) with sample values. |
| Chinese | Fairfax schools: opting out of sex education (`us_fcps_fle_zh`) | Fairfax County Public Schools | [link](https://content.govdelivery.com/attachments/VAEDUFCPS/2026/10/05/file_attachments/3805974/FLE-Opt-Out_Letter_SY24-25-Chinese.pdf) | 2026-10-18 | Left out the 'CHINESE' language label printed at the top. |
| Spanish | IRS: we changed your tax return (`us_irs_cp12_es`) | Internal Revenue Service | [link](https://www.irs.gov/pub/notices/cp12_spanish.pdf) | 2026-10-25 | None. |
| Burmese | New York schools: your child gets English support (`us_nysed_ell_my`) | New York State Education Department | [link](https://www.nysed.gov/sites/default/files/programs/bilingual-ed/burmese_entitlement_june2018.pdf) | 2026-10-25 | Converted from the old Zawgyi Burmese encoding to standard Unicode with the Rabbit converter, removed text the PDF printed four times over (to fake bold type), and filled the blank fields with sample values (names, dates, address, phone number). |
| Korean | Seoul high school: parent survey (`kr_mirim_ko`) | Mirim Meister High School, Seoul | [link](https://www.e-mirim.hs.kr/upload/board/1764730690921.pdf) | 2026-10-25 | None. |
| Portuguese | Portuguese school: returning textbooks (`pt_manuais_pt`) | Escola Secundária Júlio Dantas, Lagos (Portugal) | [link](https://www.aejd.pt/files/2025_2026/Recolha_Manuais_2025-2026_ESJD_%20Secundario.pdf) | 2026-10-25 | None. |
| French | Quebec school: daycare registration (`ca_garde_fr`) | Centre de services scolaire des Draveurs (Quebec) | [link](https://sources.cssdd.gouv.qc.ca/files/2026/01/SDG-AG-MI-26-27-Lettre-aux-parents-1-1.pdf) | 2026-10-25 | None. |
| Japanese | Kyoto City: help with school costs (`jp_kyoto_aid_ja`) | Kyoto City Board of Education | [link](https://www.city.kyoto.lg.jp/kyoiku/cmsfiles/contents/0000325/325215/R8osirase.pdf) | 2026-10-25 | None. |
| Vietnamese | Kyoto City: starting primary school (`jp_kyoto_entry_vi`) | Kyoto City Board of Education | [link](https://www.city.kyoto.lg.jp/kyoiku/cmsfiles/contents/0000183/183855/sinsyou1yuusou.pdf) | 2026-10-25 | Used only the Vietnamese page (page 6 of 6) of Kyoto's multilingual guide. |
| Malay | Edusave Awards: letter to parents (`sg_edusave_ms`) | Temasek Primary School (Ministry of Education) | [link](https://isomer-user-content.by.gov.sg/615/e9bd5888-16f1-4f8f-b823-9b019e72daf5/Primary_(ML).pdf) | 2026-10-18 | None. |
| Hindi | NHS: cervical screening invitation (`uk_nhs_cervical_hi`) | NHS England (GOV.UK) | [link](https://www.gov.uk/government/publications/cervical-screening-invitations/e56c3089-4134-4636-a296-85c9c4717ac9) | 2026-10-18 | Copied the letter text from the web page; the page's menus and feedback form were left out. |

The letters belong to their publishers and are included only to test and demonstrate Misread.
The 100 backtest letters are listed with their links in
[`backtest/manifest.json`](backtest/manifest.json).
