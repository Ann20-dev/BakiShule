# BakiShule translations (English / Kiswahili)

Generated from `app/messages.py` by `python -m scripts.export_translations`. Please review the
Kiswahili column before the demo and send corrections against the **key**. `{placeholders}` are filled
in by the app and must stay as they are; `<br>` marks a line break. Emojis are replaced by plain text
(⭐→*, ⚠️→!, ✅→OK, ⬇️/⬆️→chini/juu) when an SMS would exceed 2 segments.

Total strings: 175.

## Language selection & shared (shown before a language is known)

| Key | English | Kiswahili |
|---|---|---|
| `language_screen` | Karibu BakiShule / Welcome<br>Chagua lugha / Choose language:<br>1. English<br>2. Kiswahili | Karibu BakiShule / Welcome<br>Chagua lugha / Choose language:<br>1. English<br>2. Kiswahili |
| `not_registered` | Namba hii haijasajiliwa. Tafadhali wasiliana na shule yako. / This number is not registered. Please contact your school. | Namba hii haijasajiliwa. Tafadhali wasiliana na shule yako. / This number is not registered. Please contact your school. |
| `sms_welcome` | Karibu BakiShule! Tuma KISWAHILI au ENGLISH kuchagua lugha. / Reply ENGLISH or KISWAHILI to choose your language. | Karibu BakiShule! Tuma KISWAHILI au ENGLISH kuchagua lugha. / Reply ENGLISH or KISWAHILI to choose your language. |
| `lang_prompt` | Tuma LUGHA SW au LANG EN. / Send LANG EN or LUGHA SW. | Tuma LUGHA SW au LANG EN. / Send LANG EN or LUGHA SW. |
| `language_name` | English | Kiswahili |
| `language_changed` | Language: English | Lugha: Kiswahili |

## Dates

| Key | English | Kiswahili |
|---|---|---|
| `weekdays` | Monday,Tuesday,Wednesday,Thursday,Friday,Saturday,Sunday | Jumatatu,Jumanne,Jumatano,Alhamisi,Ijumaa,Jumamosi,Jumapili |
| `weekdays_short` | Mon,Tue,Wed,Thu,Fri,Sat,Sun | Jtt,Jnn,Jtn,Alh,Iju,Jms,Jpl |
| `months` | Jan,Feb,Mar,Apr,May,Jun,Jul,Aug,Sep,Oct,Nov,Dec | Jan,Feb,Mac,Apr,Mei,Jun,Jul,Ago,Sep,Okt,Nov,Des |
| `date_long` | {weekday} {day} {month} | {weekday} {day} {month} |
| `date_short` | {weekday} {day} {month} | {weekday} {day} {month} |
| `list_and` | {items} and {last} | {items} na {last} |

## USSD navigation & common

| Key | English | Kiswahili |
|---|---|---|
| `nav_back` | 0. Back | 0. Rudi |
| `nav_home` | 00. Main menu | 00. Menyu kuu |
| `invalid_choice` | Invalid choice, try again. | Chaguo si sahihi, jaribu tena. |
| `no_class` | No class is assigned to this number. | Hakuna darasa lililopewa namba hii. |
| `saved` | Saved | Imehifadhiwa |
| `option_save` | 1. Save | 1. Hifadhi |
| `option_cancel` | 0. Cancel | 0. Ghairi |
| `option_skip` | 0. Skip | 0. Ruka |

## Teacher USSD menu

| Key | English | Kiswahili |
|---|---|---|
| `teacher_menu_title` | BakiShule - Teacher | BakiShule - Mwalimu |
| `teacher_menu_1` | Mark attendance | Andika mahudhurio |
| `teacher_menu_2` | Class summary | Muhtasari wa darasa |
| `teacher_menu_3` | At-risk learners | Wanafunzi walio hatarini |
| `teacher_menu_4` | Log behaviour | Andika tabia |
| `teacher_menu_5` | Find learner | Tafuta mwanafunzi |
| `teacher_menu_parent` | Parent menu | Menyu ya mzazi |
| `menu_change_language` | Change language / Badilisha lugha | Badilisha lugha |
| `select_class` | Select class: | Chagua darasa: |
| `done_today` | done today | imeandikwa leo |

## Teacher USSD: attendance

| Key | English | Kiswahili |
|---|---|---|
| `att_screen_header` | {cls} - {date} ({total} learners) | {cls} - {date} (wanafunzi {total}) |
| `att_already_marked` | Already marked today; this replaces it. | Tayari imeandikwa leo; hii itaibadilisha. |
| `att_enter` | Enter absent roll numbers e.g. 03 07 12 | Andika namba za wasiokuja mf. 03 07 12 |
| `att_all_present` | 0 = all present | 0 = wote wamekuja |
| `att_enter_blank` | Enter absent roll numbers e.g. 03 07 12, or 0 if all present. | Andika namba za wasiokuja mf. 03 07 12, au 0 kama wote wamekuja. |
| `att_unknown_roll` | Unknown roll: {rolls}. | Namba isiyojulikana: {rolls}. |
| `att_roll_range` | {cls} rolls are {first}-{last}. | Namba za {cls} ni {first}-{last}. |
| `att_enter_again` | Enter absent roll numbers again. | Andika namba za wasiokuja tena. |
| `att_confirm` | Confirm {cls} {date}: | Thibitisha {cls} {date}: |
| `att_counts` | Present {present}/{total}, absent {absent} | Wamekuja {present}/{total}, hawakuja {absent} |
| `att_absent_list` | Absent: {names} | Hawakuja: {names} |
| `more` | +{count} more | +{count} zaidi |
| `att_cancelled` | Attendance cancelled. Nothing was saved. | Mahudhurio yameghairiwa. Hakuna kilichohifadhiwa. |
| `att_invalid_roll` | Invalid roll number. No attendance saved. | Namba si sahihi. Mahudhurio hayajahifadhiwa. |
| `att_saved` | Saved attendance for {count} learners in {cls}. | Imehifadhiwa: mahudhurio ya wanafunzi {count} wa {cls}. |
| `att_saved_counts` | Present {present}, absent {absent}. | Wamekuja {present}, hawakuja {absent}. |
| `att_flagged` | Flagged in class: {count}. | Walio hatarini darasani: {count}. |
| `att_parents_notified` | Parents of {count} absent flagged learner(s) will get an SMS. | Wazazi wa wanafunzi {count} walio hatarini watapata SMS. |
| `att_invalid_entry` | Invalid attendance entry. Dial again. | Mahudhurio si sahihi. Piga tena. |

## Teacher USSD: class summary, at-risk, lookup

| Key | English | Kiswahili |
|---|---|---|
| `sum_header` | {cls} - {date} | {cls} - {date} |
| `sum_today` | Today: {present} present, {absent} absent ({pct}) | Leo: {present} wamekuja, {absent} hawakuja ({pct}) |
| `sum_unmarked` | Today: not yet marked | Leo: bado haijaandikwa |
| `sum_week` | This week: {pct} | Wiki hii: {pct} |
| `sum_month` | Last 30 days: {pct} | Siku 30 zilizopita: {pct} |
| `sum_flagged` | Flagged: {count} ({critical} critical) | Hatarini: {count} ({critical} hatari kubwa) |
| `sum_absent` | Absent: {rolls} | Hawakuja: {rolls} |
| `ar_none` | No flagged learners in {cls}. Keep it up! | Hakuna walio hatarini {cls}. Hongera! |
| `ar_header` | {cls} flagged ({count}): | {cls} walio hatarini ({count}): |
| `ar_reply_for_details` | Reply number for details | Jibu namba kwa maelezo |
| `level_green` | OK | SAWA |
| `level_watch` | WATCH | ANGALIA |
| `level_at_risk` | AT RISK | HATARINI |
| `level_critical` | CRITICAL | HATARI KUBWA |
| `det_risk` | Risk: {level} {score}/100 | Hatari: {level} {score}/100 |
| `det_30_days` | 30 days: {pct} present, {absent} absent | Siku 30: alikuja {pct}, hakuja {absent} |
| `det_last_absent` | Last absent: {date} | Hakuja mara ya mwisho: {date} |
| `det_parent_said` | Parent said: {text} | Mzazi alisema: {text} |
| `det_guardian` | Guardian: {name} {phone} | Mlezi: {name} {phone} |
| `lookup_enter_roll` | {cls}: enter learner roll number | {cls}: andika namba ya mwanafunzi |
| `lookup_not_found` | No learner with roll {roll} in {cls}. | Hakuna mwanafunzi namba {roll} katika {cls}. |

## Risk reasons (USSD detail, teacher alerts)

| Key | English | Kiswahili |
|---|---|---|
| `reason_streak` | {count} absences in a row | Hakuja siku {count} mfululizo |
| `reason_drop` | Attendance down {pct} (last 2 wks) | Mahudhurio yameshuka {pct} (wiki 2) |
| `reason_weekday` | Often absent on {weekday} | Hukosa shule {weekday} mara nyingi |
| `reason_monthly` | Monthly absence clusters | Hukosa shule kila mwezi |
| `reason_sibling` | Sibling absent on {count} same days | Ndugu hakuja siku {count} hizo hizo |
| `reason_fees` | Parent reported fee difficulty | Mzazi alisema karo ni changamoto |
| `reason_behaviour` | {count} behaviour concerns in {days} days | Wasiwasi wa tabia {count} ndani ya siku {days} |
| `reason_default` | Attendance risk increased | Hatari ya mahudhurio imeongezeka |

## Behaviour logging, codes & subjects

| Key | English | Kiswahili |
|---|---|---|
| `beh_no_roll` | No roll {roll} in {cls}. | Hakuna namba {roll} katika {cls}. |
| `beh_enter_again` | Enter roll number again: | Andika namba tena: |
| `beh_choose` | {roll} {name}: choose | {roll} {name}: chagua |
| `beh_invalid_code` | Invalid behaviour code, try again. | Chaguo si sahihi, jaribu tena. |
| `beh_subject_title` | Subject (optional): | Somo (si lazima): |
| `beh_invalid_subject` | Invalid subject, try again. | Somo si sahihi, jaribu tena. |
| `beh_saved` | Saved for {roll} {name}: | Imehifadhiwa kwa {roll} {name}: |
| `beh_parent_can_view` | Parent can see it by SMS (BEHAVIOUR). | Mzazi ataiona kwa SMS (TABIA). |
| `behaviour_1` | Participated well | Alishiriki vizuri |
| `behaviour_2` | Homework not done | Hakufanya kazi ya nyumbani |
| `behaviour_3` | Late | Alichelewa darasani |
| `behaviour_4` | Disruptive | Alisumbua darasani |
| `behaviour_5` | Helped others | Aliwasaidia wenzake |
| `behaviour_6` | Excellent test score | Alama bora mtihanini |
| `behaviour_short_1` | Participated | Alishiriki |
| `behaviour_short_2` | No homework | Hakufanya kazi |
| `behaviour_short_3` | Late | Alichelewa |
| `behaviour_short_4` | Disruptive | Alisumbua |
| `behaviour_short_5` | Helped others | Alisaidia wenzake |
| `behaviour_short_6` | Top test score | Alama bora |
| `subject_1` | Maths | Hisabati |
| `subject_2` | English | Kiingereza |
| `subject_3` | Kiswahili | Kiswahili |
| `subject_4` | Science | Sayansi |
| `subject_5` | Social Studies | Masomo ya Jamii |
| `subject_6` | CRE | CRE |
| `teacher_title` | Tr. {surname} | Mwl. {surname} |

## Parent USSD

| Key | English | Kiswahili |
|---|---|---|
| `parent_menu_title` | BakiShule - {name} | BakiShule - {name} |
| `parent_menu_1` | Today's status | Hali ya leo |
| `parent_menu_2` | Attendance | Mahudhurio |
| `parent_menu_3` | Behaviour | Tabia |
| `parent_menu_4` | Weekly report | Ripoti ya wiki |
| `parent_menu_5` | Contact school | Wasiliana na shule |
| `choose_child` | Choose child: | Chagua mtoto: |
| `enter_pin` | Enter your PIN: | Ingiza PIN yako: |
| `contact_prompt` | Type your message to the school: | Andika ujumbe wako kwa shule: |
| `contact_sent` | Sent. The class teacher will get back to you. | Imetumwa. Mwalimu wa darasa atawasiliana nawe. |
| `contact_empty` | Message was empty. Nothing sent. | Ujumbe ulikuwa mtupu. Hakuna kilichotumwa. |
| `choose_child_sms` | You have {count} children: {children}. Send {example} | Una watoto {count}: {children}. Tuma {example} |

## SMS: menu, PIN & limits

| Key | English | Kiswahili |
|---|---|---|
| `menu` | BakiShule SMS:<br>STATUS - today<br>ATT - attendance<br>BEHAVIOUR <PIN> - behaviour<br>REPORT <PIN> - weekly report<br>LANG SW - Kiswahili<br>STOP - no more SMS | BakiShule SMS:<br>HALI - hali ya leo<br>MAHUDHURIO - mahudhurio<br>TABIA <PIN> - tabia<br>RIPOTI <PIN> - ripoti ya wiki<br>LUGHA EN - English<br>ACHA - acha SMS |
| `rate_limited` | BakiShule: you have reached today's limit of {limit} requests. Please try again tomorrow. | BakiShule: umefikia kikomo cha maombi {limit} leo. Tafadhali jaribu tena kesho. |
| `pin_required` | Please add your 4-digit PIN, e.g. {example} | Tafadhali ongeza PIN yako ya tarakimu 4, mfano {example} |
| `pin_wrong` | Wrong PIN. {left} attempt(s) left before a 1-hour lock. | PIN si sahihi. Majaribio {left} yamebaki kabla ya kufungiwa saa 1. |
| `pin_locked` | Too many wrong PINs. Please try again after {time}. | PIN zisizo sahihi nyingi. Jaribu tena baada ya saa {time}. |
| `no_pin` | No PIN is set for this number. Please ask the school for your PIN. | Namba hii haina PIN. Tafadhali omba PIN yako shuleni. |
| `pin_only` | To use your PIN, send it after a command, e.g. REPORT {example}. | Tuma PIN pamoja na amri, mfano RIPOTI {example}. |
| `combined_hint` | Send {command} 1 for details. | Tuma {command} 1 kwa maelezo zaidi. |

## SMS: STATUS (HALI)

| Key | English | Kiswahili |
|---|---|---|
| `status_line` | {name} ({cls}) - {date}: {today} | {name} ({cls}) - {date}: {today} |
| `today_present` | {icon} At school today. | {icon} Yuko shuleni leo. |
| `today_absent` | {icon} Not at school today. | {icon} Hayupo shuleni leo. |
| `today_unmarked` | Today's attendance is not marked yet. | Mahudhurio ya leo bado hayajaandikwa. |
| `last_note` | Last note: {icon} {label}{subject} ({teacher}). | Mwisho: {icon} {label}{subject} ({teacher}). |
| `no_notes` | No behaviour notes yet. | Hakuna taarifa za tabia bado. |
| `status_more` | Send ATT, BEHAVIOUR or REPORT for more. | Tuma MAHUDHURIO, TABIA au RIPOTI kwa zaidi. |
| `status_short` | {name}: {today} | {name}: {today} |
| `short_present` | at school today | yuko shuleni leo |
| `short_absent` | not at school today | hayupo shuleni leo |
| `short_unmarked` | not marked yet | bado haijaandikwa |

## SMS: ATT (MAHUDHURIO)

| Key | English | Kiswahili |
|---|---|---|
| `att_week_line` | {name} - This week: {attended}/{total} days ({missed}). | {name} - Wiki hii: siku {attended}/{total} ({missed}). |
| `att_missed_days` | missed {days} | hakuja {days} |
| `att_no_missed` | no days missed | hakukosa siku |
| `att_term_line` | Term: {pct}. | Muhula: {pct}. |
| `att_class_avg` | Class average: {pct}. | Wastani wa darasa: {pct}. |
| `att_short` | {name}: {attended}/{total} days this week, term {pct} | {name}: siku {attended}/{total} wiki hii, muhula {pct} |

## SMS: BEHAVIOUR (TABIA)

| Key | English | Kiswahili |
|---|---|---|
| `beh_header` | {name} - Behaviour this term: {positive}{pos} {concern}{con} | {name} - Tabia muhula huu: {positive}{pos} {concern}{con} |
| `beh_none` | No behaviour notes yet this term. | Hakuna taarifa za tabia muhula huu. |

## SMS: REPORT (RIPOTI)

| Key | English | Kiswahili |
|---|---|---|
| `report_title` | Weekly report - {name}, {cls}: | Ripoti ya wiki - {name}, {cls}: |
| `report_attendance` | Attendance {pct}{arrow} (was {previous}). | Mahudhurio {pct}{arrow} (ilikuwa {previous}). |
| `report_attendance_same` | Attendance {pct} (same as last week). | Mahudhurio {pct} (sawa na wiki iliyopita). |
| `report_attendance_only` | Attendance {pct}. | Mahudhurio {pct}. |
| `report_behaviour` | Behaviour {positive}{pos} {concern}{con}. | Tabia {positive}{pos} {concern}{con}. |
| `report_status` | Status: {icon}{risk}. | Hali: {icon}{risk}. |
| `risk_green` | On track | Sawa |
| `risk_watch` | Watch | Angalia |
| `risk_at_risk` | At risk | Hatarini |
| `risk_critical` | High risk | Hatari kubwa |
| `risk_none` | Not scored yet | Bado haijapimwa |
| `tip_attendance` | Tip: Ask {first} about {day}. Send 2 if fees are a challenge. | Ushauri: Muulize {first} kuhusu {day}. Tuma 2 kama karo ni changamoto. |
| `tip_behaviour` | Tip: Talk with {first} about behaviour in class. | Ushauri: Ongea na {first} kuhusu tabia darasani. |
| `tip_checkin` | Tip: A short daily chat about school helps {first}. | Ushauri: Mazungumzo mafupi kila siku kuhusu shule humsaidia {first}. |
| `tip_praise` | Tip: Great week! Tell {first} you are proud of them. | Ushauri: Wiki nzuri! Mwambie {first} unajivunia. |
| `fallback_down` | down | chini |
| `fallback_up` | up | juu |

## SMS: check-ins, acknowledgements, alerts, receipts

| Key | English | Kiswahili |
|---|---|---|
| `checkin` | We missed {name} {days}. Is everything okay? Reply 1 Sick, 2 Fees, 3 Other. | Hatukumwona {name} {days}. Kila kitu kiko sawa? Jibu 1 Mgonjwa, 2 Karo, 3 Mengineyo. |
| `checkin_on_days` | on {days} | {days} |
| `checkin_for_days` | for {count} school days | kwa siku {count} za shule |
| `ack_1` | Thank you. Get well soon, {names}! The class teacher has been informed. | Asante. Pona haraka, {names}! Mwalimu wa darasa amejulishwa. |
| `ack_2` | Thank you for telling us. The school will contact you about fee support for {names}. | Asante kwa kutujulisha. Shule itawasiliana nawe kuhusu msaada wa karo kwa {names}. |
| `ack_3` | Thank you. Your message about {names} has been passed to the class teacher. Send MENU for options. | Asante. Ujumbe wako kuhusu {names} umepelekwa kwa mwalimu. Tuma MSAADA kwa machaguo. |
| `ack_start` | You will get BakiShule updates again. Send STOP to opt out. | Utapokea tena taarifa za BakiShule. Tuma ACHA kujiondoa. |
| `alert_at_risk` | At-risk: {name} ({cls}). {summary} | Hatarini: {name} ({cls}). {summary} |
| `alert_parent_reply` | Parent reply: {text} | Jibu la mzazi: {text} |
| `teacher_parent_sick` | Parent reports {name} is sick. Please follow up. | Mzazi anasema {name} ni mgonjwa. Tafadhali fuatilia. |
| `teacher_parent_reply` | Parent reply about {name}: {text} | Jibu la mzazi kuhusu {name}: {text} |
| `teacher_parent_message` | Message from parent of {name}: {text} | Ujumbe kutoka kwa mzazi wa {name}: {text} |
| `reward_congrats` | Congratulations {first}! You completed 4 weeks of full attendance. KES {amount} airtime is yours. | Hongera {first}! Umekamilisha wiki 4 bila kukosa shule. Umepata salio la KES {amount}. |
| `sponsor_receipt` | Fee support of KES {amount} has been arranged for {name}. | Msaada wa karo wa KES {amount} umepangwa kwa {name}. |
