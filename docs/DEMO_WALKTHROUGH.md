# 60-second product demo: script and shot list

Target: **60 seconds, one take of screen recording + your voice-over**. Every sentence below is something the app really does; the order flow was run against the real backend while writing this (text path). The microphone path needs **your** Gnani key, so record it only after `verify_gnani.bat` passes on your machine.

## Before you record (10 minutes)

| Step | Command / action | Why |
|---|---|---|
| 1 | `setup.bat`, put `GNANI_API_KEY=...` in `.env` | Voice needs the key |
| 2 | `verify_gnani.bat` and read the result | Do not record a "live" demo until this passes |
| 3 | `backend\.venv\Scripts\python.exe scripts\seed_db.py --reset` (deletes local demo data) | Fresh stock, clean order numbers |
| 4 | `start.bat`, open http://localhost:8000 in **Chrome or Edge**, 1920x1080, zoom 100%, the one light theme | Same layout as the screenshots |
| 4b | Create the owner account (the first account is the owner): **Create account** on the landing page, tick the terms, then **Open the dashboard**. Sign out, so the take can start on the landing page. After the landing shots, sign in again and trim the sign-in in the editor | The Order desk, Inventory, Catalogue and Analytics are behind sign-in |
| 5 | Settings page: the chip should read *Key set …* (the key itself is masked; still do not show `.env`); *Test connection (2 calls)* is the quick check | The chip shows the key is loaded; only the test button proves a live call |
| 6 | Quiet room, headset mic, one practice take with the Hinglish sentence | Avoid retakes |
| 7 | Recorder: Win+G (Xbox Game Bar) or OBS; record the browser tab only | No notifications, no other tabs |

If the microphone or Prisma fails during recording, **switch to the typed sentence and say so** ("voice is off in this take, typing the same sentence"). Do not splice or fake a voice result.

## Shot list (60 s)

| Time | Screen | On-screen text (add in editor) | Voice-over (about 150 words in total, relaxed pace) |
|---|---|---|---|
| 0:00-0:06 | **Landing**. Slowly show the headline and the live parser box | *SWARA AI: Every Voice. Smarter Commerce.* | "Millions of kirana stores take orders by voice, in Gujarati, Hindi and the mix people really speak. Software rarely listens like that." |
| 0:06-0:13 | Landing: click the **ગુજરાતી** example, then **Gujarati + English**. The "Heard as" bill fills in | *Gujarati, Hindi, English, Hinglish: one engine* | "SWARA AI turns that speech into a bill. This is the same engine every voice order goes through: items, quantities, units, rate and amount." |
| 0:13-0:32 | **Order desk** (`/order`). Pick **Hinglish** in *Customer speaks* (Prisma v2.5 takes one language per request, so choose the language first), mode *Tap to talk*. Press the mic and say: **"Bhai mujhe 2 kilo chawal aur 1 litre doodh chahiye"**. Show transcript, then the bill appearing on the receipt and the spoken reply playing | *Gnani Prisma hears it. Gnani Timbre answers.* | "I tap the mic and just talk. Gnani Prisma transcribes it, the engine finds rice and milk, checks stock, and adds up the bill in rupees. Timbre reads it back in the same language." |
| 0:32-0:40 | Say **"bas itna hi"**, then **"haan"**. The *Order confirmed* panel appears with the order number | *Confirmed by voice* | "Nothing is saved until I say yes. Stock drops the moment the order is confirmed." |
| 0:40-0:47 | **Inventory** (`/inventory`): search "milk" and show the reduced stock, then the **Restock now** list on the **Dashboard** if anything is low | *Live inventory, low-stock alerts* | "The shopkeeper sees stock fall in real time, with alerts when something runs low." |
| 0:47-0:52 | **Catalogue** (`/catalogue`): search "parle", open one product so the drawer shows the raw source value beside the cleaned one | *5,325 real products, Open Food Facts. No prices: the shopkeeper sets them* | "Real products come from public data. It has no prices, so the shopkeeper adds their own." |
| 0:52-0:58 | **Analytics** (`/analytics`): the KPIs and the sales chart; flip one chart to **Table** | *Demo orders are generated, and labelled* | "Analytics read straight from the database. The demo orders are generated, and the app says so." |
| 0:58-1:00 | **Landing** hero or the Dashboard | *SWARA AI. Every Voice. Smarter Commerce.* | "SWARA AI. Every voice. Smarter commerce. Voice ordering for the shop around the corner." |

Word count of the voice-over: about 150. Say it at a normal pace; if it overruns, cut the Orders/Analytics lines first, never the confirm step.

## Honest-demo rules

- Say "generated demo data" if you mention any number on the Dashboard or Analytics. The orders, the revenue and the voice share are drawn by a seeded script, not measured from a shop.
- Do not say the catalogue has prices, or that the prices are real. The catalogue has none, and the staples' prices are placeholders ("Demo price").
- Do not state a latency or accuracy figure in the video unless `verify_gnani.bat` / `evaluate_noise.py` produced it on your machine in the same session. The only measured numbers in this repo that do not need your key are the parser benchmarks in `docs/EVALUATION.md`.
- Evon is not part of the demo. Do not mention it as used.
- Use a throwaway owner account made for the recording, and hide the browser's saved-password dropdowns. Do not show the Account page's contact inbox if you tested the contact form with real names.

## Optional 15-second extra for social media (vertical crop)

Order desk only: say the Hindi sentence **"भैया ढाई किलो चीनी और आधा किलो चायपत्ती दे दो"**. The bill shows *2.5 kg sugar* and *2 packs of tea* (tea is sold in 250 g packs, so half a kilo becomes two packs). That one frame shows unit and pack handling better than any slide.

## Fallback sentences that work (checked against the parser)

| Language | Sentence | Bill |
|---|---|---|
| Hinglish | Bhai mujhe 2 kilo chawal aur 1 litre doodh chahiye | Rice 2 kg + Milk 1 l = ₹172 |
| Gujarati | મને બે કિલો ખાંડ અને એક લિટર દૂધ જોઈએ છે | Sugar 2 kg + Milk 1 l = ₹148 |
| Hindi | भैया ढाई किलो चीनी और आधा किलो चायपत्ती दे दो | Sugar 2.5 kg + Tea 2 packs = ₹355 |
| English | one and a half kilo onion and a dozen eggs please | on the Landing page |
| Gujarati + English | મને 2 kg sugar અને 1 litre milk જોઈએ | on the Landing page |

(Prices are the seeded demo prices, shown with a "Demo price" badge in Inventory. If you changed prices, the totals change.)
