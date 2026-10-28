# Hand review of "wrong answer" flags

The AI re-check (`run.py audit`) turned out to be too generous, so after each run 30 flags were
drawn at random and judged by hand against the letter.

- **Genuine**: the reader is confidently mistaken in a way that would hurt them (a wrong date, a step
  the letter doesn't ask for, the wrong organisation, "nothing to do" when there is).
- **Unfair**: the reader was fine, or just vague (named the school principal instead of the general
  office, "the letter doesn't say", a sentence fragment, a different consequence the letter also gives).
- **Debatable**: reasonable people could disagree, or the document isn't really a letter (newsletters,
  blank forms, guides), or the letter itself is inconsistent (IRS CP22A gives two dates for one payment).

| Run | What changed before it | Genuine | Debatable | Unfair |
|---|---|---|---|---|
| 2 | Unstated questions not scored; separate "invented a task" check; up to 3 valid answers in the key; reader can't echo the form | 7 | 7 | 16 |
| 3 | Stricter definition of "wrong" for the grader; "the letter doesn't say" counts as no answer | 6 | 8 | 16 |
| 4 | Every "wrong" double-checked against the letter itself (Nemotron 3 Super) | 9 | 10 | 11 |
| 5 | Contacts get a narrow "same organisation?" check; documents classified by a separate call | 8 | 17 | 5 |

Of the 17 debatable flags in run 5, 8 are in documents the site now labels as a newsletter, template
or "not a letter". On the 22 flags from real letters in run 5: 8 genuine, 9 debatable, 5 unfair.

## Run 5 sample (random.seed(31)), with verdicts

| # | Letter | Question | Reader said | Verdict |
|---|---|---|---|---|
| 1 | sg_clementi_t1_sec1 | Deadline | by 28 Jan (letter has several dates) | Debatable |
| 2 | us_irs_cp22a | Deadline | February 20, 2017 (letter gives Feb 20 and Mar 23) | Debatable |
| 3 | sg_hsa_fsn_drager | What to do | Stop using the monitor until fixed (letter: keep using, wait 10 s after docking) | Genuine |
| 4 | us_cms_abn_blank | If they don't | Medicare may bill you in full | Debatable (blank form) |
| 5 | sg_hsa_fsn_terumo | What to do | Contact Terumo (letter: distribute notice, return form) | Debatable |
| 6 | sg_clementi_t1_sec45 | If they don't | Lateness rule (key: SDF and car decal) | Unfair |
| 7 | sg_hsa_fsn_terumo | If they don't | Procedure stops due to alarm | Unfair |
| 8 | us_irs_cp63 | What to do | Call the IRS about the refund (letter: file 2017 return by Feb 7) | Genuine |
| 9 | sg_yishun_echa | Deadline | 27 August (letter: 6 September) | Genuine |
| 10 | uk_council_tax_letter | Need to act? | No | Debatable (not a letter) |
| 11 | uk_tenant_information | Deadline | 1 May 2026 | Debatable (not a letter) |
| 12 | sg_customs_traveller_guide | Contact | "Customs, Immigration and Checkpoints Authority" | Debatable (not a letter) |
| 13 | sg_fernvale_p1_assess | Contact | The school motto | Unfair (nonsense, should be "missed") |
| 14 | uk_mhra_fsn | Contact | Department of Health alerts email (letter: MHRA) | Debatable |
| 15 | sg_clementi_t1_sec1 | If they don't | Missing the CCA deadline (key: missing the session) | Unfair |
| 16 | sg_yuneng_ltp_mar | Deadline | 31 March / 9 March | Debatable (newsletter) |
| 17 | sg_clementi_t1_sec3 | Need to act? | No (letter asks for forms) | Genuine |
| 18 | us_irs_cp88 | Deadline | "date not specified" | Unfair (pattern now added) |
| 19 | us_irs_cp27 | What to do | Contact the IRS (letter: fill in and mail the worksheet) | Genuine |
| 20 | sg_yishun_new_year_2025 | Need to act? | No | Debatable (newsletter) |
| 21 | uk_council_tax_letter | Contact | Email address | Debatable (not a letter) |
| 22 | sg_yishun_cross_country | What to do | Report to school at 9 am (letter: stadium by 7.30 am) | Genuine |
| 23 | sg_yishun_hbl_jul2024 | Deadline | 10 Jul (letter: 11 Jul) | Genuine |
| 24 | sg_yishun_canteen_reminder | Need to act? | Submit a consent form and $200 deposit (not in the letter) | Debatable: the reader model invented it |
| 25 | sg_hdb_rent_approval | Deadline | End of the rental period | Debatable |
| 26 | sg_yishun_pld_consent | Need to act? | Buy the Chromebook bundle by the deadline | Debatable (key may be wrong) |
| 27 | us_irs_cp53 | Deadline | "by the notice date" | Debatable |
| 28 | sg_customs_circular_06_2021 | Need to act? | No (circular requires traders to comply) | Genuine |
| 29 | us_irs_cp88 | If they don't | Refund stays held (letter: IRS assesses tax, may lose credits) | Debatable |
| 30 | sg_yishun_canteen_hbl | Deadline | 9 March | Debatable (newsletter) |
