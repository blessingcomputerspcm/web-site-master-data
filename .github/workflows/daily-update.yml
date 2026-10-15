# Web Site Master – Daily Auto Job Update

Blessing Computers, Pavoorchatram – 627808 · 9486889040

Ithu thinamum 2 murai (kaalai 5:45, maalai 3:45) automatic-aa odum:
govt websites → Gemini AI → `data/jobs.json` → **Web Site Master** software.

---

## Step 1: GitHub Repository create pannunga

1. https://github.com-la login pannunga.
2. Mela valathu pakkam **+** → **New repository** click pannunga.
3. Repository name: `web-site-master-data`
4. **Public** select pannunga. (Software antha file-ai password illaamal padikkanum. Itha data-vil ragasiyam ethuvum illai.)
5. **Create repository** click pannunga.

## Step 2: Files upload pannunga

1. Repository page-la **uploading an existing file** link-ai click pannunga.
2. Intha zip-ai unzip panni, ulle irukkura **ellaa files & folders**-aiyum (`config.json`, `sources.json`, `requirements.txt`, `README.md`, `updater` folder, `data` folder) drag & drop pannunga.
3. **Commit changes** click pannunga.

## Step 3: Daily schedule file (workflow) create pannunga

Browser upload-la `.github` folder silasamayam varaathu, athanaala ithai thani-aa create pannunga:

1. Repository-la **Add file → Create new file** click pannunga.
2. File name box-la type pannunga: `.github/workflows/daily-update.yml`
3. Zip-la irukkura `.github/workflows/daily-update.yml` file-ai Notepad-la open panni, ellaa content-aiyum copy panni paste pannunga.
4. **Commit changes** click pannunga.

## Step 4: Gemini API key edunga (free)

1. https://aistudio.google.com-la ungal Google account-aal login pannunga.
2. Idathu pakkam **Get API key** → **Create API key** click pannunga.
3. Varum key-ai copy pannunga. (**Itha key-ai yaarukkum, entha chat-laiyum kodukkaatheenga.**)

## Step 5: Key-ai GitHub Secrets-la podunga

1. Repository-la **Settings** → idathu pakkam **Secrets and variables** → **Actions**.
2. **New repository secret** click pannunga.
3. Name: `GEMINI_API_KEY`
4. Secret: copy panna key-ai paste pannunga.
5. **Add secret** click pannunga.

## Step 6: Muthal murai odavidunga

1. Repository-la **Actions** tab click pannunga. "Enable workflows" button vanthaal click pannunga.
2. Idathu pakkam **Daily Job Update** → **Run workflow** → **Run workflow** click pannunga.
3. 5–15 nimidam aagum. Green ✔ vanthaal sari.
4. `data/jobs.json` file open panni puthu jobs vanthirukka-nu paarunga.

## Step 7: Software-la link podunga

1. Web Site Master software → **Admin** (PIN 1234) → **Backup & Settings**.
2. **Online Data Link**-la ithai podunga (USERNAME-kku pathil ungal GitHub username):

   `https://raw.githubusercontent.com/USERNAME/web-site-master-data/main/data/jobs.json`

3. **Save & Update Now** click pannunga. Ini software open aagum pothum, ovvoru 30 nimidaththukku oru murai-um automatic-aa update aagum.

---

## Thevaippattaal maaththa vendiyavai

| Enna | Engu | Eppadi |
|---|---|---|
| AI maaththa (Gemini / ChatGPT / Claude) | `config.json` | `"ai_provider": "gemini"` → `"chatgpt"` or `"claude"`. Athukkaana key-ai Secrets-la podunga: `OPENAI_API_KEY` / `ANTHROPIC_API_KEY` |
| Backup AI | `config.json` | `backup_order` – muthal AI fail aanaal key irukkura adutha AI try aagum |
| Puthu website check panna | `sources.json` | Oru line copy panni name, url, cat (tn / state / central / rail / bank / def) maaththunga |
| Oru website-ai niruththa | `sources.json` | `"enabled": false` |
| Update time | `.github/workflows/daily-update.yml` | `cron` lines (UTC time; IST = UTC + 5:30) |

## Prachanai vanthaal

- **Actions-la red ✘**: run-ai click panni "Find new government jobs" step-la error-ai paarunga. Athai screenshot eduththu Claude-idam kaattunga.
- **Some govt sites "page not readable"**: sila govt sites velinaattu server-ai block pannum. Appo Gemini + Google Search moolam antha site jobs-ai thedum (`use_google_search: true`).
- **Gemini "quota / busy"**: free limit mudinjirukkalaam. Adutha run-la thaanaaga odum.
- Ovvoru job-lum "official notification-la check pannunga" note irukkum. AI-um silasamayam thappu pannum.
