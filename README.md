# Cortex Respond

AI-powered inbound lead qualification chatbot. Visitors chat with an AI receptionist that collects contact and qualification info through natural conversation, scores the lead 1–10, and logs it to Google Sheets.

Built with FastAPI + Claude (Anthropic) + Google Sheets.

## Quick Start

**1. Install dependencies**
```bash
pip install -r requirements.txt
```

**2. Configure environment**
```bash
cp .env.example .env
# Edit .env and add your ANTHROPIC_API_KEY
```

**3. Run**
```bash
uvicorn main:app --reload
```

**4. Open** http://localhost:8000

Click the chat widget in the bottom-right corner to try the demo.

## Customise for a different business

Edit `config.yaml` — change `business`, `services`, `faqs`, and `scoring.rules`. No code changes needed. Restart the server after editing.

## Google Sheets Setup (optional)

Without Sheets config, completed leads are logged to the server console. To enable Google Sheets:

1. Create a Google Cloud project and enable the **Google Sheets API** and **Google Drive API**
2. Create a **Service Account** and download the JSON credentials file
3. Share your Google Sheet with the service account email address (Editor access)
4. Set these values in `.env`:
   ```
   GOOGLE_SHEETS_CREDENTIALS_PATH=path/to/credentials.json
   GOOGLE_SHEET_ID=your-sheet-id-here
   ```

The sheet ID is the long string in the Google Sheets URL:  
`https://docs.google.com/spreadsheets/d/<SHEET_ID>/edit`

## Project Structure

```
cortex-respond/
├── main.py           # FastAPI backend — all server logic
├── config.yaml       # Business configuration (name, services, FAQs, scoring)
├── static/
│   └── index.html    # Landing page + chat widget (single file, all CSS/JS inline)
├── requirements.txt
├── .env.example
└── tests/
    └── test_main.py  # Unit + integration tests
```

## How It Works

1. Visitor opens the chat widget on the landing page
2. AI agent (powered by Claude Sonnet) greets them and starts a natural conversation
3. The agent collects: name, phone, email, service interest, budget, and urgency — one question at a time
4. It also answers FAQs about the business from `config.yaml`
5. Once all 6 fields are collected, Claude scores the lead 1–10 and embeds a hidden `<lead_data>` block in its final message
6. The backend parses the block, strips it from the visible reply, and appends the lead to Google Sheets
7. The user sees a warm wrap-up message; you see a new row in your sheet

## Run Tests

```bash
pytest tests/ -v
```
