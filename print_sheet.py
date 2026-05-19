import gspread
from google.oauth2.service_account import Credentials

GSHEET_KEY = "1VIu93hO3e8pTRC1FD8z3yehCvGqxGV1EfT41IIwLH7g"
GSHEET_WORKSHEET = "bubblemaps.io"
CREDENTIALS_FILE = "credentials.json"

scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
creds = Credentials.from_service_account_file(CREDENTIALS_FILE, scopes=scope)
client = gspread.authorize(creds)
sheet = client.open_by_key(GSHEET_KEY).worksheet(GSHEET_WORKSHEET)

records = sheet.get_all_records()
print(f"Total records: {len(records)}")
for idx, r in enumerate(records):
    print(f"Row {idx+2}: {r}")
