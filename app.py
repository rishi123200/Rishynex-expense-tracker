import csv
import io
import os
import sqlite3
from datetime import datetime, date
from functools import wraps

from flask import (
    Flask,
    render_template,
    request,
    redirect,
    url_for,
    flash,
    session,
    Response
)
from werkzeug.security import generate_password_hash, check_password_hash

from config import COMPANY_NAME, APP_TAGLINE, CURRENCY_SYMBOL


ROOT = os.path.dirname(os.path.abspath(__file__))

DB_PATH = os.environ.get(
    "DATABASE_PATH",
    os.path.join(ROOT, "expenses.db")
)

app = Flask(__name__)

app.secret_key = os.environ.get("SECRET_KEY")

if not app.secret_key:
    raise RuntimeError(
        "SECRET_KEY is missing. Set it in Render Environment Variables."
    )

app.config.update(
    COMPANY_NAME=COMPANY_NAME,
    APP_TAGLINE=APP_TAGLINE,
    CURRENCY_SYMBOL=CURRENCY_SYMBOL
)


def db_connect():
    connection = sqlite3.connect(DB_PATH, timeout=30)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def init_db():
    with db_connect() as db:
        db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                email TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
        """)

        db.execute("""
            CREATE TABLE IF NOT EXISTS expenses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                expense_date TEXT NOT NULL,
                category TEXT NOT NULL,
                amount REAL NOT NULL CHECK(amount > 0),
                description TEXT NOT NULL,
                FOREIGN KEY(user_id)
                    REFERENCES users(id)
                    ON DELETE CASCADE
            )
        """)


def login_required(fn):
    @wraps(fn)
    def wrapped(*args, **kwargs):
        if "user_id" not in session:
            flash("Please sign in first.", "error")
            return redirect(url_for("login"))

        return fn(*args, **kwargs)

    return wrapped


@app.context_processor
def shared():
    return {
        "company_name": COMPANY_NAME,
        "app_tagline": APP_TAGLINE,
        "currency_symbol": CURRENCY_SYMBOL,
        "current_year": date.today().year
    }


def expenses_for(
    uid,
    start="",
    end="",
    category="",
    search=""
):
    sql = "SELECT * FROM expenses WHERE user_id = ?"
    args = [uid]

    if start:
        sql += " AND expense_date >= ?"
        args.append(start)

    if end:
        sql += " AND expense_date <= ?"
        args.append(end)

    if category:
        sql += " AND lower(category) = lower(?)"
        args.append(category)

    if search:
        sql += """
            AND (
                lower(description) LIKE ?
                OR lower(category) LIKE ?
            )
        """
        search_term = f"%{search.lower()}%"
        args.extend([search_term, search_term])

    sql += " ORDER BY expense_date DESC, id DESC"

    with db_connect() as db:
        return db.execute(sql, args).fetchall()


@app.route("/")
def home():
    if "user_id" in session:
        return redirect(url_for("dashboard"))

    return redirect(url_for("login"))


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        confirm = request.form.get("confirm_password", "")

        if not name or not email or not password or not confirm:
            flash("Please complete all fields.", "error")

        elif len(password) < 8:
            flash(
                "Your password must contain at least 8 characters.",
                "error"
            )

        elif password != confirm:
            flash("Passwords do not match.", "error")

        else:
            try:
                with db_connect() as db:
                    db.execute(
                        """
                        INSERT INTO users (
                            name,
                            email,
                            password_hash,
                            created_at
                        )
                        VALUES (?, ?, ?, ?)
                        """,
                        (
                            name,
                            email,
                            generate_password_hash(password),
                            datetime.now().isoformat(timespec="seconds")
                        )
                    )

                flash(
                    "Account created successfully. Please sign in.",
                    "success"
                )

                return redirect(url_for("login"))

            except sqlite3.IntegrityError:
                flash(
                    "This email address is already registered.",
                    "error"
                )

    return render_template("auth.html", mode="register")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        with db_connect() as db:
            user = db.execute(
                "SELECT * FROM users WHERE email = ?",
                (email,)
            ).fetchone()

        if user and check_password_hash(
            user["password_hash"],
            password
        ):
            session.clear()
            session["user_id"] = user["id"]
            session["user_name"] = user["name"]
            session["user_email"] = user["email"]

            return redirect(url_for("dashboard"))

        flash("Email or password is incorrect.", "error")

    return render_template("auth.html", mode="login")


@app.post("/logout")
@login_required
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/dashboard")
@login_required
def dashboard():
    start = request.args.get("start_date", "").strip()
    end = request.args.get("end_date", "").strip()
    category = request.args.get("category", "").strip()
    search = request.args.get("search", "").strip()

    rows = expenses_for(
        session["user_id"],
        start,
        end,
        category,
        search
    )

    with db_connect() as db:
        all_rows = db.execute(
            "SELECT * FROM expenses WHERE user_id = ?",
            (session["user_id"],)
        ).fetchall()

    total = sum(row["amount"] for row in all_rows)
    average = total / len(all_rows) if all_rows else 0

    categories = {}

    for row in all_rows:
        name = row["category"]
        categories[name] = categories.get(name, 0) + row["amount"]

    category_data = sorted(
        categories.items(),
        key=lambda item: item[1],
        reverse=True
    )

    current_month = date.today().strftime("%Y-%m")

    month_total = sum(
        row["amount"]
        for row in all_rows
        if row["expense_date"].startswith(current_month)
    )

    return render_template(
        "dashboard.html",
        expenses=rows,
        total=total,
        count=len(all_rows),
        average=average,
        largest=max(
            [row["amount"] for row in all_rows],
            default=0
        ),
        category_data=category_data,
        categories=sorted(categories),
        month_total=month_total,
        start_date=start,
        end_date=end,
        selected_category=category,
        search=search
    )


@app.post("/add")
@login_required
def add():
    try:
        expense_date = datetime.strptime(
            request.form.get("expense_date", ""),
            "%Y-%m-%d"
        ).date().isoformat()

        category = request.form.get("category", "").strip().title()
        description = request.form.get("description", "").strip()

        amount_text = request.form.get("amount", "").strip()
        amount = float(amount_text)

        if (
            not category
            or not description
            or not amount_text
            or not amount > 0
            or not amount < float("inf")
        ):
            raise ValueError

        with db_connect() as db:
            db.execute(
                """
                INSERT INTO expenses (
                    user_id,
                    expense_date,
                    category,
                    amount,
                    description
                )
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    session["user_id"],
                    expense_date,
                    category,
                    amount,
                    description
                )
            )

        flash("Expense added successfully.", "success")

    except (ValueError, OverflowError):
        flash(
            "Enter a valid date, category, description, and positive amount.",
            "error"
        )

    return redirect(url_for("dashboard"))


@app.post("/delete/<int:eid>")
@login_required
def delete(eid):
    with db_connect() as db:
        result = db.execute(
            """
            DELETE FROM expenses
            WHERE id = ? AND user_id = ?
            """,
            (eid, session["user_id"])
        )

    if result.rowcount:
        flash("Expense deleted successfully.", "success")
    else:
        flash("Expense not found.", "error")

    return redirect(url_for("dashboard"))


@app.route("/reports")
@login_required
def reports():
    with db_connect() as db:
        rows = db.execute(
            """
            SELECT expense_date, category, amount
            FROM expenses
            WHERE user_id = ?
            """,
            (session["user_id"],)
        ).fetchall()

    monthly = {}
    categories = {}

    for row in rows:
        month = row["expense_date"][:7]
        monthly[month] = monthly.get(month, 0) + row["amount"]

        category = row["category"]
        categories[category] = (
            categories.get(category, 0) + row["amount"]
        )

    return render_template(
        "reports.html",
        monthly_data=sorted(monthly.items()),
        category_data=sorted(
            categories.items(),
            key=lambda item: item[1],
            reverse=True
        ),
        total=sum(row["amount"] for row in rows),
        transaction_count=len(rows)
    )


@app.route("/export.csv")
@login_required
def export():
    rows = expenses_for(
        session["user_id"],
        request.args.get("start_date", ""),
        request.args.get("end_date", ""),
        request.args.get("category", ""),
        request.args.get("search", "")
    )

    output = io.StringIO()
    writer = csv.writer(output)

    writer.writerow([
        "Date",
        "Category",
        "Amount",
        "Description"
    ])

    for row in rows:
        writer.writerow([
            datetime.strptime(
                row["expense_date"],
                "%Y-%m-%d"
            ).strftime("%d-%m-%Y"),
            row["category"],
            f'{row["amount"]:.2f}',
            row["description"]
        ])

    return Response(
        "\ufeff" + output.getvalue(),
        mimetype="text/csv",
        headers={
            "Content-Disposition":
                "attachment; filename=expense-report.csv"
        }
    )


@app.route("/profile")
@login_required
def profile():
    with db_connect() as db:
        user = db.execute(
            "SELECT * FROM users WHERE id = ?",
            (session["user_id"],)
        ).fetchone()

        count = db.execute(
            "SELECT COUNT(*) AS n FROM expenses WHERE user_id = ?",
            (session["user_id"],)
        ).fetchone()["n"]

    return render_template(
        "profile.html",
        user=user,
        count=count
    )


# Initialize database tables when the application starts,
# including when it is launched by Gunicorn on Render.
init_db()


if __name__ == "__main__":
    app.run(debug=False)