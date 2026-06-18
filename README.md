# ipo-feedback-skill

Automatically scrape IPO review feedback documents from BSE, SSE, and SZSE. Download PDFs and extract text for your Agent (Claude, GPT, etc.) to generate summary reports.

## Features

- **All three exchanges**: BSE, SSE, SZSE
- **Three document types**: inquiry letters, feedback replies, prospectus registration drafts
- **Auto scraping**: Fetch data via public APIs, no browser required
- **PDF download**: Parallel downloading for speed
- **Text extraction**: Parse PDF content into plain text using pdfplumber
- **Content analysis**: Extract questions from inquiry letters, topics from replies, main business and financials from prospectus
- **Auto cleanup**: Old downloads (>30 days) automatically moved to trash
- **Structured output**: Markdown (for terminal reading) and JSON (for Agent consumption)
- **Flexible time range**: Default to yesterday, max 40 days, customizable via `--days`

## What is this? What is this not?

This is a **Skill**, not an Agent. It only handles data collection and parsing — no LLM calls. Configure it in your own Agent, and let the Agent's LLM generate analysis reports.

```
Your Agent (with LLM)
    └── calls ipo-feedback skill
            ├── scrape exchange data
            ├── download PDFs
            ├── parse text
            └── output structured data → back to Agent → LLM generates report
```

## Supported exchanges

| Exchange | Inquiry Letter | Feedback Reply | Registration Draft |
|----------|---------------|----------------|-------------------|
| BSE | ✅ | ✅ | ✅ |
| SSE | — | ✅ | ✅ |
| SZSE | — | ✅ | ✅ |

- BSE publishes all three document types
- SSE and SZSE only publish company replies and registration drafts, not the original inquiry letters
- Registration drafts = 招股说明书注册稿

## Prerequisites

- **Python >= 3.10**
- **pip** (Python package manager)
- Network access to BSE, SSE, SZSE websites

## Install

```bash
# 1. Clone the repo
git clone https://github.com/corylcr/ipo-feedback-skill.git
cd ipo-feedback-skill

# 2. Create a virtual environment
python3 -m venv venv
source venv/bin/activate  # macOS / Linux
# venv\Scripts\activate   # Windows

# 3. Install
pip install -e .
```

After installation, you'll have the `ipo-feedback` CLI tool.

## Quick start

```bash
# Fetch yesterday's feedback from all exchanges (default)
ipo-feedback fetch --exchange all

# Fetch BSE only
ipo-feedback fetch --exchange bse

# Fetch last 7 days
ipo-feedback fetch --exchange all --days 7

# Output JSON (for Agent consumption)
ipo-feedback fetch --exchange all --format json
```

## Commands

### `ipo-feedback fetch`

Scrape exchange IPO feedback data, download and parse PDFs.

```text
ipo-feedback fetch [OPTIONS]

Options:
  -e, --exchange {bse,sse,szse,all}
                        Exchange to scrape (default: bse)
  -d, --days N          Days to look back, max 40 (default: 1, i.e. yesterday)
  -f, --format {markdown,json}
                        Output format (default: markdown)
  --no-download         List files only, don't download PDFs
  --no-parse            Download PDFs but skip text extraction
  -h, --help            Show help
```

### Examples

```bash
# Daily routine: fetch yesterday's updates from all exchanges
ipo-feedback fetch --exchange all

# BSE this week, list only
ipo-feedback fetch --exchange bse --days 7 --no-download

# JSON output for scripting
ipo-feedback fetch --exchange szse --days 3 --format json > report.json
```

## Configuration

### Integrate with your Agent

Add the skill to your Agent config:

```yaml
# Example: Claude Code skill config
skills:
  - name: ipo-feedback
    command: "cd /path/to/ipo-feedback-skill && ipo-feedback fetch --exchange all --days 1 --format json"
    output: json
```

The Agent reads the JSON output and uses its LLM to generate summary reports.

## Output format

The output includes content analysis for each document type:

- **Inquiry letters**: Questions raised by the exchange, with focus areas
- **Feedback replies**: Topics addressed and reply approaches
- **Prospectus**: Main business description and key financials (revenue, net profit, gross margin, ROE)

### Markdown (default, for terminal reading)

```
# BSE IPO Feedback Report
**Period**: 2026-06-17 ~ 2026-06-18

Total **6** projects updated: inquiry letters **1**, registration drafts **5**

---

## 旭阳新材 (874421)

### Inquiry Letter

- Published: 2026-06-18
- PDF: [第二轮审核问询函](https://...)

**4 questions raised:**

1. **业绩增长可持续性**
   Focus: 报告期内，发行人业绩呈现持续增长趋势...

2. **销售真实性及收入确认准确性**
   Focus: 发行人存在部分客户与供应商重合的情况...

---

## 威易发 (872893)

### Registration Draft

- Published: 2026-06-18
- PDF: [招股说明书（注册稿）](https://...)

**Main Business:**

发行人主营业务为金属密封件的研发、生产与销售，产品为金属密封环，主要应用于涡轮增压器...

**Key Financials:**

- Revenue: ['149743406.85', '133645640.55', '106433089.82']
- Net Profit: ['63274315.84', '65656683.26', '46253309.27']
- Gross Margin: ['69.12%', '69.12%', '67.54%']
- ROE: ['28.17%', '40.04%', '44.25%']

---

**Trash**: 3 old files (>30 days) moved to trash
  - 2026-05-01_OldCompany_...pdf
  - ...
```

### JSON (`--format json`, for Agent consumption)

```json
{
  "exchange": "bse",
  "date_range": "2026-06-17 ~ 2026-06-18",
  "projects": [
    {
      "company_name": "Company Name",
      "stock_code": "872824",
      "inquiry": null,
      "reply": {
        "title": "Second round inquiry reply",
        "publish_date": "2026-06-17",
        "pdf_url": "https://...",
        "pdf_path": "downloads/BSE/...pdf",
        "content_text": "(extracted plain text)"
      },
      "prospectus": {
        "title": "Prospectus (registration draft)",
        "publish_date": "2026-06-18",
        "pdf_url": "https://...",
        "pdf_path": "downloads/BSE/...pdf",
        "content_text": "(extracted plain text)"
      }
    }
  ]
}
```

## Auto cleanup

Each time `ipo-feedback fetch` runs, PDF files older than **30 days** are automatically moved to the system trash (not permanently deleted). The cleanup summary is shown at the end of the report.

## Project structure

```
ipo-feedback-skill/
├── README.md
├── pyproject.toml
├── ipo_feedback/
│   ├── cli.py              # CLI entry point
│   ├── config.py            # Global config
│   ├── models.py            # Data models
│   ├── downloader.py        # PDF downloader
│   ├── parser.py            # PDF text extraction
│   ├── analyzer.py          # Inquiry/reply content analyzer
│   ├── prospectus.py        # Prospectus key info extractor
│   ├── cleanup.py           # Auto-cleanup old files
│   └── exchanges/
│       ├── base.py          # Exchange base class
│       ├── bse.py           # BSE
│       ├── sse.py           # SSE
│       └── szse.py          # SZSE
└── downloads/               # PDF download directory (auto-created)
    ├── BSE/
    ├── SSE/
    └── SZSE/
```

## ⚠️ Disclaimer

All data and files obtained through this project are from **publicly available information** on official exchange websites. By using this project, you acknowledge and agree to the following:

1. **For personal learning and research only**. Commercial use is strictly prohibited.
2. **You shall not use the data obtained from this project for any form of commercial profit**, including but not limited to selling data, providing paid services, etc.
3. **You shall not perform large-scale, high-frequency scraping** on exchange websites, so as not to affect their normal operation. Please control the scraping frequency appropriately.
4. **All legal risks and liabilities arising from the use of this project shall be borne by the user**, and the project developer shall not be held responsible.
5. Content on exchange websites is copyrighted. Downloaded PDF files belong to their original rights holders.
6. If the exchange websites' terms of use or robots.txt prohibit such scraping activities, please stop using this project immediately.

**This project is provided "AS IS", without warranties of any kind, express or implied.**

## License

MIT
