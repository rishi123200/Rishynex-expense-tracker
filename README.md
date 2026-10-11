# Complete Expense Tracker Website

## Set your company name
Open `config.py` and change `COMPANY_NAME = "Your Company Name"` to your real company or brand name. You can also change `APP_TAGLINE` and `CURRENCY_SYMBOL`. The name appears in the website branding and page titles.

## Run on Windows
1. Extract the ZIP and open the folder in VS Code.
2. Terminal → New Terminal.
3. Run `py -m pip install -r requirements.txt`
4. Run `py app.py`
5. Open http://127.0.0.1:5000

## Features
- Registration and login; passwords are stored as hashes.
- Each user sees only their own expenses.
- Add and delete expenses.
- Dashboard totals, monthly total and category summary.
- Filter by date range and category; search description/category.
- Monthly reports and category charts.
- Download expense records as CSV.
- Responsive design for phone and desktop.
- SQLite database created automatically.

## Public deployment
Set a strong `SECRET_KEY` environment variable and configure persistent disk storage. Set `DATABASE_PATH` to a file on that persistent disk. Do not rely on temporary container storage for real expense data. This starter project should be further hardened with CSRF protection, rate limiting, email verification, password reset, backups, privacy and terms pages before handling real customer data.

Developer: Rishidharan R | B.Tech IT
