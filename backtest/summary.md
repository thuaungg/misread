# Misread backtest: 100 letters

## Before and after the fixes

Hand review of 30 random flags (genuine / debatable / unfair): run 2: 7 / 7 / 16, run 5: 8 / 17 / 5.

### All 100 documents

| | Before | After |
|---|---|---|
| Letters tested | 98 | 99 |
| Crashed | 0 | 0 |
| Median full-read score | 87 | 100 |
| Full read under 70 (answer key or text problem) | 36 | 33 |
| Median busy-reader score | 47 | 50 |
| Letters with a wrong answer | 84 | 52 |
| Wrong-answer cards | 162 | 72 |
| Cards confirmed by the re-check | 121/154 (79%) | 70/72 (97%) |

### Real letters only (what Misread is for)

| | Before | After |
|---|---|---|
| Letters tested | 71 | 71 |
| Crashed | 0 | 0 |
| Median full-read score | 93 | 100 |
| Full read under 70 (answer key or text problem) | 15 | 12 |
| Median busy-reader score | 56 | 69 |
| Letters with a wrong answer | 65 | 37 |
| Wrong-answer cards | 131 | 51 |
| Cards confirmed by the re-check | 95/126 (75%) | 49/51 (96%) |

## What happened to each letter

- **ok**: 99
- **rejected**: 1

## Scores

| Group | Tested | Median busy score | Median full-read score | Letters with a wrong answer | Full read under 70 |
|---|---|---|---|---|---|
| Singapore | 49 | 33 | 67 | 32 (65%) | 28 |
| US and other | 50 | 78 | 100 | 20 (40%) | 5 |
| Normal letters | 80 | 53 | 100 | 43 (54%) | 27 |
| Hard cases | 19 | 49 | 92 | 9 (47%) | 6 |
| Kind: letter | 71 | 69 | 100 | 37 (52%) | 12 |
| Kind: newsletter | 15 | 8 | 33 | 8 (53%) | 13 |
| Kind: template | 6 | 36 | 68 | 3 (50%) | 3 |
| Kind: not a letter | 7 | 25 | 50 | 4 (57%) | 5 |
| All | 99 | 50 | 100 | 52 (53%) | 33 |

A careful full read should score high. Under 70 means the answer key or the extracted text is the likely problem, not the letter.

## Are the "wrong answers" really wrong?

72 wrong-answer cards across 52 letters. Each was re-checked by Nemotron 3 Ultra reading the whole letter. That re-check is generous: judged by hand, far fewer are clear-cut. See [hand_review.md](hand_review.md) for 30 random flags per run.

- **Really wrong (the card is right)**: 70 (97%)
- **Reader was fine (unfair card)**: 2 (3%)

| Question | Cards | Really wrong | Unfair | Key wrong |
|---|---|---|---|---|
| Need to act? | 20 | 20 | 0 | 0 |
| Deadline | 18 | 18 | 0 | 0 |
| If they don't | 17 | 15 | 2 | 0 |
| Who to contact | 9 | 9 | 0 | 0 |
| What to do | 8 | 8 | 0 | 0 |

## The fixer

Ran on 15 letters with the lowest busy scores (confirmed misreads first). 3 stopped with a message instead of a fix.

| Letter | Before | After | Misreads before → after | Change | Same words |
|---|---|---|---|---|---|
| sg_clementi_t1_sec1 | 13 | | | no change beat the original: the site now says so | |
| sg_clementi_t1_sec3 | | | | NoFix: Couldn't find the answer key's sentences in the letter, so there was not… | |
| sg_clementi_t1_sec45 | 13 | 73 | 33% → 0% | Add a “What you need to do” box at the top, made of the letter's own … | yes |
| sg_clementi_welcome_sec1 | 37 | 63 | 33% → 0% | Move the deadline sentence to the top: “We seek your help to complete… | yes |
| sg_yishun_pld_consent | | | | NoFix: Couldn't find the answer key's sentences in the letter, so there was not… | |
| sg_yishun_echa | 33 | 100 | 50% → 0% | Move the deadline sentence to the top: “Kindly submit your nomination… | yes |
| sg_yishun_cross_country | 46 | 33 | 67% → 33% | Make the what to do sentence bold: “We would like to take this opport… | yes |
| sg_yishun_hbl_jul2024 | | | | NoFix: None of the 7 changes tried did better than the original letter, so ther… | |
| sg_mom_ipa_employer | 73 | 90 | 33% → 0% | Move the what happens if not sentence to the top: “Otherwise, we will… | yes |
| sg_hdb_rent_approval | 30 | 57 | 83% → 67% | Move the what happens if not sentence to the top: “HDB reserves the r… | yes |
| sg_hsa_fsn_terumo | 33 | 93 | 83% → 17% | Add a “What you need to do” box at the top, made of the letter's own … | yes |
| us_irs_cp22a | 70 | 100 | 100% → 0% | Move the what to do sentence to the top: “Pay the amount due of $24.6… | yes |
| us_irs_cp88 | 57 | 97 | 100% → 17% | Add a “What you need to do” box at the top, made of the letter's own … | yes |
| us_irs_cp27 | 56 | 89 | 50% → 33% | Move the what to do sentence to the top: “Complete the Earned Income … | yes |
| us_irs_cp63 | 60 | 90 | 100% → 0% | Add a “What you need to do” box at the top, made of the letter's own … | yes |

11 of 15 letters got a change that beat the original on the same re-check.

Median gain +30 points; 10/11 improved; 11/11 cut misreads.

## Hard cases

| Letter | Why it's hard | What the system did |
|---|---|---|
| sg_serangoon_t1_2026 | 21-page term letter, 7,234 words | busy 22, full 58, 1 wrong-answer card(s); classified as newsletter (the site warns) |
| sg_yishun_handbook | a 2-part parent handbook, not one letter | busy 6, full 50, 2 wrong-answer card(s); classified as not a letter (the site warns) |
| sg_yishun_engagement_deck | a slide deck, not a letter | busy 29, full 100, 0 wrong-answer card(s); classified as not a letter (the site warns) |
| sg_mom_ipa_helper | Tamil text that extracts as garbage | busy 69, full 100, 0 wrong-answer card(s) |
| sg_hdb_rent_approval | two-column letter plus 4 pages of terms | busy 38, full 73, 2 wrong-answer card(s) |
| sg_hsa_fsn_maquet | technical notice for hospital engineers | busy 67, full 100, 1 wrong-answer card(s) |
| sg_hsa_fsn_terumo | a company's letter template | busy 49, full 100, 2 wrong-answer card(s) |
| sg_cccs_s68_notice | scanned legal notice read by OCR | rejected: 54,145 words is over the 10,000-word limit; warning shown: template: 204 blanks, 3 letters in one file; classified as not a letter (the site warns) |
| sg_ipos_consent_template | blank template to print on letterhead | busy 22, full 33, 0 wrong-answer card(s); warning shown: template: 33 blanks; classified as template (the site warns) |
| sg_customs_traveller_guide | a long guide, not a letter | busy 22, full 33, 1 wrong-answer card(s); classified as not a letter (the site warns) |
| us_nhtsa_dealer_20v124 | technical dealer bulletin, not for the owner | busy 100, full 100, 0 wrong-answer card(s) |
| us_nhtsa_dealer_20v036 | technical dealer bulletin, not for the owner | busy 86, full 100, 0 wrong-answer card(s) |
| us_nhtsa_dealer_20v714 | technical dealer bulletin, not for the owner | busy 94, full 92, 0 wrong-answer card(s) |
| us_cms_abn_blank | blank form with checkboxes | busy 42, full 83, 2 wrong-answer card(s); classified as template (the site warns) |
| us_irs_cp14_spanish | the letter is in Spanish | busy 84, full 100, 0 wrong-answer card(s) |
| us_ca_na290_blank | blank state form | busy 42, full 75, 0 wrong-answer card(s); warning shown: template: 9 blanks |
| us_ca_calfresh_ebt_blank | blank state form | busy 62, full 53, 1 wrong-answer card(s); warning shown: template: 12 blanks; classified as template (the site warns) |
| uk_hmrc_tc_guide | technical guide that contains a sample letter | busy 60, full 100, 0 wrong-answer card(s); warning shown: template: 4 blanks |
| uk_tenant_information | guidance for landlords, not a letter | busy 25, full 50, 1 wrong-answer card(s); classified as not a letter (the site warns) |
| us_cms_im_instructions | instructions for hospitals, not a letter to a patient | busy 100, full 100, 0 wrong-answer card(s); classified as template (the site warns) |

## Speed

- Answer key: median 2s, slowest 10s
- Test (12 readings): median 11s, slowest 22s

## Answer keys

- Need to act: {'False': 12, 'True': 60, 'conditional': 27}
- Questions the key said the letter doesn't answer: {'deadline': 26, 'consequence': 14, 'action': 3, 'contact': 3}

## Every letter

| Letter | Words | Busy | Full | Worst wrong answer (they said → actually) | Check |
|---|---|---|---|---|---|
| sg_sembawang_open_01_2026 | 3085 | 39 | 33 |  |  |
| sg_sembawang_open_03_2026 | 2154 | 2 | 60 | Need to act?: “No — I don't need to do anything.” → Yes — you have to act. | reader_wrong |
| sg_sembawang_open_05_2025 | 2621 | 56 | 83 |  |  |
| sg_sembawang_open_07_2025 | 1950 | 3 | 0 |  |  |
| sg_serangoon_t1_2026 | 7234 | 22 | 58 | Deadline: “by 31 January 2026” → Medical certificates for WA absences: on assessment day; Se… | reader_wrong |
| sg_clementi_t1_sec1 | 3164 | 24 | 13 | Need to act?: “No — I don't need to do anything.” → Yes — you have to act. | reader_wrong |
| sg_clementi_t1_sec3 | 3078 | 16 | 20 | Need to act?: “No — I don't need to do anything.” → Yes — you have to act. | reader_wrong |
| sg_clementi_t1_sec45 | 3398 | 7 | 93 | Need to act?: “No — I don't need to do anything.” → Yes — you have to act. | reader_wrong |
| sg_clementi_welcome_sec1 | 2093 | 16 | 53 | Need to act?: “No — I don't need to do anything.” → Yes — you have to act. | reader_wrong |
| sg_fernvale_t1_2026 | 2731 | 33 | 93 | Need to act?: “No — I don't need to do anything.” → Yes — you have to act. | reader_wrong |
| sg_fernvale_p6_assess | 988 | 36 | 40 | Need to act?: “No — I don't need to do anything.” → Yes — you have to act. | reader_wrong |
| sg_fernvale_p1_assess | 588 | 56 | 100 | Who to contact: “Global Learners of Tomorrow” → Subject teachers at 63153051 or fernvale_ps@moe.edu.sg for … | reader_wrong |
| sg_henrypark_thrive_jan | 2047 | 0 | 17 |  |  |
| sg_henrypark_thrive_apr | 3068 | 50 | 50 |  |  |
| sg_yuneng_ltp_jan | 4644 | 8 | 17 | If they don't: “The school will not accept requests from parents regarding the insura…” → Multiple consequences: 1) Students not in proper uniform fo… | reader_wrong |
| sg_yuneng_lockdown_drill | 591 | 96 | 56 |  |  |
| sg_yuneng_bcrs | 336 | 78 | 100 | Need to act?: “Yes — I have to read the full letter and register your child/children…” → No — nothing is needed right now. | reader_wrong |
| sg_yuneng_uniform | 99 | 56 | 67 |  |  |
| sg_yuneng_ltp_mar | 1700 | 3 | 0 | Deadline: “by Tuesday, 31 March 2026 (for class photos) or Monday, 9 March 2026 …” → 27 Mar 2026 (thermometer), 1 Apr 2026 (thermometer), 23 Mar… | reader_wrong |
| sg_yishun_canteen_hbl | 567 | 22 | 50 | Need to act?: “No — I don't need to do anything.” → Yes — you have to act. | reader_wrong |
| sg_yishun_canteen_reminder | 142 | 78 | 100 | Need to act?: “Yes — I have to submit the consent form and arrange for the $200 depo…” → No — nothing is needed right now. | reader_wrong |
| sg_yishun_sexuality_ed | 351 | 14 | 100 |  |  |
| sg_yishun_olevel_results | 183 | 64 | 100 | Deadline: “by 1:30 pm on Wednesday, 14 January 2026” → 14 January 2026, 1:50 pm | reader_wrong |
| sg_yishun_pld_consent | 3092 | 74 | 100 | Need to act?: “Yes — I have to purchase the Chromebook PLD bundle from Acer Computer…” → No — nothing is needed right now. | reader_wrong |
| sg_yishun_echa | 187 | 7 | 100 | Deadline: “by 27 August 2024” → 6 September 2024, 5:00 PM | reader_wrong |
| sg_yishun_new_year_2025 | 1622 | 27 | 40 | Need to act?: “No — I don't need to do anything.” → Yes — you have to act. | reader_wrong |
| sg_yishun_smart_buddy | 334 | 37 | 11 |  |  |
| sg_yishun_cross_country | 286 | 50 | 67 | Deadline: “by 9:00 AM on 12 May 2023” → 12 May 2023, 7:30 am | reader_wrong |
| sg_yishun_hbl_jul2024 | 225 | 41 | 67 | Need to act?: “No — I don't need to do anything.” → Yes — you have to act. | reader_wrong |
| sg_yishun_pe_tshirt | 256 | 50 | 50 | Need to act?: “Yes — I have to purchase a new PE T-shirt for the student” → No — nothing is needed right now. | reader_wrong |
| sg_zhangde_t1_desk | 2704 | 8 | 33 |  |  |
| sg_zhangde_t3 | 2184 | 6 | 33 |  |  |
| sg_zhangde_t4 | 3245 | 7 | 7 | Need to act?: “No — I don't need to do anything.” → Yes — you have to act. | reader_wrong |
| sg_bowen_ta1_sec45 | 958 | 36 | 67 |  |  |
| sg_moe_letter_to_parents | 1119 | 42 | 87 | Deadline: “by Thursday 15 August 2024” → 2 August 2024 (reply on participation); 16 August 2024, 12 … | reader_wrong |
| sg_yishun_handbook | 2652 | 6 | 50 | What to do: “Review the full handbook and set up necessary device or account for m…” → Establish family routines for balanced device use, discuss … | reader_wrong |
| sg_yishun_engagement_deck | 3660 | 29 | 100 |  |  |
| sg_mom_ipa_employer | 944 | 73 | 100 | Deadline: “04 May 2016” → 04 Aug 2016 | reader_wrong |
| sg_mom_ipa_helper | 1580 | 69 | 100 |  |  |
| sg_hdb_rent_approval | 3094 | 38 | 73 | Need to act?: “No — I don't need to do anything.” → Yes — you have to act. | reader_wrong |
| sg_hsa_fsn_endologix | 4542 | 31 | 80 |  |  |
| sg_hsa_fsn_drager | 621 | 75 | 100 | What to do: “Stop using the Infinity Acute Care System and Standalone Infinity M54…” → Wait at least 10 seconds after docking M540 monitor before … | reader_wrong |
| sg_hsa_fsn_maquet | 610 | 67 | 100 | What to do: “Stop using the affected Servo ventilator immediately and contact the …” → Follow precautions: never leave patient unattended, keep re… | reader_wrong |
| sg_hsa_fsn_endobarrier | 457 | 19 | 100 | Need to act?: “No — I don't need to do anything.” → Yes — you have to act. | reader_wrong |
| sg_hsa_fsn_terumo | 761 | 49 | 100 | If they don't: “procedure discontinuation due to the alarm” → Terumo BCT cannot confirm receipt of the field safety notic… | reader_wrong |
| sg_hsa_recall_bd | 1079 | 94 | 100 |  |  |
| sg_cccs_s68_notice | 54145 | | | rejected: 54,145 words is over the 10,000-word limit | |
| sg_customs_circular_06_2021 | 2159 | 20 | 27 | Need to act?: “No — I don't need to do anything.” → Yes — you have to act. | reader_wrong |
| sg_ipos_consent_template | 571 | 22 | 33 |  |  |
| sg_customs_traveller_guide | 2474 | 22 | 33 | Who to contact: “Customs, Immigration and Checkpoints Authority (CICA) of Singapore” → Singapore Customs Call Centre: (+65) 6355 2000 or customs_f… | reader_wrong |
| us_irs_cp01 | 390 | 17 | 50 |  |  |
| us_irs_cp501 | 1728 | 100 | 100 |  |  |
| us_irs_cp503 | 1602 | 100 | 100 |  |  |
| us_irs_cp11 | 1923 | 98 | 100 |  |  |
| us_irs_cp13 | 524 | 41 | 89 | If they don't: “There are miscalculations on your Summary Form that affect certain ar…” → If you don't respond, the IRS will assume you agree with th… | reader_wrong |
| us_irs_cp21a | 756 | 96 | 100 | If they don't: “The letter indicates that if you do not pay, the IRS will assume you …” → Additional penalty and interest charges if not paid by dead… | reader_ok |
| us_irs_cp22a | 756 | 71 | 100 | Deadline: “by February 20, 2017” → March 23, 2017 | reader_wrong |
| us_irs_cp23 | 2086 | 93 | 100 |  |  |
| us_irs_cp24 | 520 | 48 | 100 |  |  |
| us_irs_cp49 | 471 | 67 | 100 | Need to act?: “Yes — I have to contact the IRS using the phone number provided to in…” → No — nothing is needed right now. | reader_wrong |
| us_irs_cp53 | 150 | 42 | 100 | Deadline: “by the notice date shown on the letter” → Within 4 weeks of notice date | reader_wrong |
| us_irs_cp71c | 1800 | 86 | 92 |  |  |
| us_irs_cp80 | 248 | 44 | 100 |  |  |
| us_irs_cp88 | 279 | 64 | 100 | Deadline: “by when (date not specified in the excerpt)” → March 04, 2009 | reader_wrong |
| us_irs_cp90 | 1785 | 93 | 100 |  |  |
| us_irs_cp161 | 1463 | 78 | 87 |  |  |
| us_irs_cp297 | 1791 | 93 | 100 |  |  |
| us_irs_cp566 | 1196 | 78 | 100 |  |  |
| us_irs_lt11 | 1787 | 100 | 100 |  |  |
| us_irs_cp59 | 1098 | 87 | 100 | Deadline: “January 28, 2019 (date of notice)” → Immediately; refund claim deadline is April 15, 2021. | reader_wrong |
| us_irs_cp09 | 1656 | 96 | 100 | If they don't: “If the worksheet indicates you are not eligible, or if the credit is …” → If eligible and worksheet is not returned, you will not rec… | reader_wrong |
| us_irs_cp27 | 929 | 78 | 100 | If they don't: “If the worksheet indicates I am not eligible, I may need to repay any…” → If eligible and worksheet is not returned, you will not rec… | reader_wrong |
| us_irs_cp63 | 367 | 69 | 100 | If they don't: “Your 2018 tax refund is being held” → IRS may determine tax liability using third-party informati… | reader_wrong |
| us_irs_cp14i | 1462 | 93 | 100 | Deadline: “January 30, 2018” → February 20, 2018 | reader_wrong |
| us_irs_cp180 | 276 | 47 | 100 | If they don't: “If we don’t receive Form 8827 by [date not shown], processing of your…” → The IRS will disallow the claimed credit and bill for addit… | reader_wrong |
| us_irs_cp60 | 785 | 98 | 100 |  |  |
| us_nhtsa_ford_maverick | 2258 | 100 | 100 |  |  |
| us_nhtsa_ford_f150 | 2504 | 92 | 100 |  |  |
| us_nhtsa_prevost | 877 | 97 | 100 |  |  |
| us_nhtsa_ford_transit | 2553 | 81 | 100 |  |  |
| us_nhtsa_hyundai | 712 | 94 | 100 |  |  |
| us_nhtsa_genesis | 766 | 89 | 100 |  |  |
| us_nhtsa_2013_owner | 531 | 62 | 100 |  |  |
| us_nhtsa_2012_owner | 512 | 76 | 87 |  |  |
| us_nhtsa_dealer_20v124 | 274 | 100 | 100 |  |  |
| us_nhtsa_dealer_20v036 | 273 | 86 | 100 |  |  |
| us_nhtsa_dealer_20v714 | 279 | 94 | 92 |  |  |
| us_cms_im_hospital | 856 | 3 | 83 | Who to contact: “For more information, call 1-800-MEDICARE (1-800-633-4227), or TTY: .…” → Livanta QIO at 1-877-588-1123 (TTY/TDD 1-855-887-6668, Fax … | reader_wrong |
| us_cms_abn_blank | 554 | 42 | 83 | If they don't: “If you do not choose an option, Medicare may bill you for the full co…” → If you choose Option 1 and Medicare denies payment, you are… | reader_wrong |
| us_irs_cp16 | 732 | 48 | 100 | If they don't: “If you don’t agree with the changes made to your 2009 tax return, the…” → If you don't respond, the IRS will assume you agree with th… | reader_wrong |
| us_irs_cp14_spanish | 1405 | 84 | 100 |  |  |
| us_ca_medical_noa_example | 1171 | 31 | 42 |  |  |
| us_ca_na290_blank | 1110 | 42 | 75 |  |  |
| us_ca_calfresh_ebt_blank | 1196 | 62 | 53 | If they don't: “your CalFresh benefits may be stopped or deactivated if you do not us…” → CalFresh benefits stopped after 135 days inactivity; unused… | reader_wrong |
| uk_hmrc_tc_guide | 385 | 60 | 100 |  |  |
| uk_tenant_information | 3916 | 25 | 50 | Deadline: “by 1 May 2026” → Before or at the start of the tenancy. | reader_wrong |
| uk_council_tax_letter | 3417 | 13 | 20 | Need to act?: “No — I don't need to do anything.” → Yes — you have to act. | reader_wrong |
| uk_mhra_fsn | 1635 | 64 | 80 | Who to contact: “safetyalerts@dh.gsi.gov.uk” → Adverse Incident Centre, MHRA: Tel 020 3080 7080, Email aic… | reader_wrong |
| us_cms_im_instructions | 320 | 100 | 100 |  |  |
| us_irs_cp10 | 576 | 30 | 78 | If they don't: “If you don't agree with the changes we made, your tax return may be a…” → If you don't respond, the IRS will assume you agree with th… | reader_wrong |
