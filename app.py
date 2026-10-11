import csv, io, os, sqlite3
from datetime import datetime, date
from functools import wraps
from flask import Flask, render_template, request, redirect, url_for, flash, session, Response
from werkzeug.security import generate_password_hash, check_password_hash
from config import COMPANY_NAME, APP_TAGLINE, CURRENCY_SYMBOL

ROOT = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.environ.get("DATABASE_PATH", os.path.join(ROOT, "expenses.db"))
app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "change-this-to-a-long-random-secret")
app.config.update(COMPANY_NAME=COMPANY_NAME, APP_TAGLINE=APP_TAGLINE, CURRENCY_SYMBOL=CURRENCY_SYMBOL)

def db_connect():
    c = sqlite3.connect(DB_PATH)
    c.row_factory = sqlite3.Row
    return c

def init_db():
    with db_connect() as db:
        db.execute("CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY, name TEXT NOT NULL, email TEXT UNIQUE NOT NULL, password_hash TEXT NOT NULL, created_at TEXT NOT NULL)")
        db.execute("CREATE TABLE IF NOT EXISTS expenses(id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL, expense_date TEXT NOT NULL, category TEXT NOT NULL, amount REAL NOT NULL, description TEXT NOT NULL, FOREIGN KEY(user_id) REFERENCES users(id))")

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
    return dict(company_name=COMPANY_NAME, app_tagline=APP_TAGLINE, currency_symbol=CURRENCY_SYMBOL, current_year=date.today().year)

def expenses_for(uid, start="", end="", category="", search=""):
    sql = "SELECT * FROM expenses WHERE user_id=?"
    args = [uid]
    if start: sql += " AND expense_date>=?"; args.append(start)
    if end: sql += " AND expense_date<=?"; args.append(end)
    if category: sql += " AND lower(category)=lower(?)"; args.append(category)
    if search:
        sql += " AND (lower(description) LIKE ? OR lower(category) LIKE ?)"
        args += [f"%{search.lower()}%", f"%{search.lower()}%"]
    sql += " ORDER BY expense_date DESC, id DESC"
    with db_connect() as db: return db.execute(sql, args).fetchall()

@app.route("/")
def home():
    return redirect(url_for("dashboard" if "user_id" in session else "login"))

@app.route("/register", methods=["GET","POST"])
def register():
    if request.method == "POST":
        name=request.form.get("name","").strip(); email=request.form.get("email","").strip().lower()
        password=request.form.get("password",""); confirm=request.form.get("confirm_password","")
        if not name or not email or not password: flash("Complete all fields.", "error")
        elif len(password)<8: flash("Password must be at least 8 characters.", "error")
        elif password != confirm: flash("Passwords do not match.", "error")
        else:
            try:
                with db_connect() as db:
                    db.execute("INSERT INTO users(name,email,password_hash,created_at) VALUES(?,?,?,?)",
                               (name,email,generate_password_hash(password),datetime.now().isoformat(timespec="seconds")))
                flash("Account created. Please sign in.", "success"); return redirect(url_for("login"))
            except sqlite3.IntegrityError: flash("That email is already registered.", "error")
    return render_template("auth.html", mode="register")

@app.route("/login", methods=["GET","POST"])
def login():
    if request.method=="POST":
        email=request.form.get("email","").strip().lower(); password=request.form.get("password","")
        with db_connect() as db: user=db.execute("SELECT * FROM users WHERE email=?", (email,)).fetchone()
        if user and check_password_hash(user["password_hash"],password):
            session.clear(); session["user_id"]=user["id"]; session["user_name"]=user["name"]; session["user_email"]=user["email"]
            return redirect(url_for("dashboard"))
        flash("Email or password is incorrect.", "error")
    return render_template("auth.html", mode="login")

@app.post("/logout")
def logout():
    session.clear(); return redirect(url_for("login"))

@app.route("/dashboard")
@login_required
def dashboard():
    start=request.args.get("start_date",""); end=request.args.get("end_date","")
    category=request.args.get("category",""); search=request.args.get("search","").strip()
    rows=expenses_for(session["user_id"],start,end,category,search)
    with db_connect() as db: all_rows=db.execute("SELECT * FROM expenses WHERE user_id=?",(session["user_id"],)).fetchall()
    total=sum(r["amount"] for r in all_rows); average=total/len(all_rows) if all_rows else 0
    cats={}
    for r in all_rows: cats[r["category"]]=cats.get(r["category"],0)+r["amount"]
    cat_data=sorted(cats.items(),key=lambda x:x[1],reverse=True)
    this_month=date.today().strftime("%Y-%m")
    month_total=sum(r["amount"] for r in all_rows if r["expense_date"].startswith(this_month))
    return render_template("dashboard.html", expenses=rows, total=total, count=len(all_rows), average=average,
        largest=max([r["amount"] for r in all_rows],default=0), category_data=cat_data, categories=sorted(cats),
        month_total=month_total,start_date=start,end_date=end,selected_category=category,search=search)

@app.post("/add")
@login_required
def add():
    try:
        d=datetime.strptime(request.form.get("expense_date",""),"%Y-%m-%d").date().isoformat()
        cat=request.form.get("category","").strip().title(); desc=request.form.get("description","").strip()
        amount=float(request.form.get("amount",""))
        if not cat or not desc or amount<=0: raise ValueError
        with db_connect() as db: db.execute("INSERT INTO expenses(user_id,expense_date,category,amount,description) VALUES(?,?,?,?,?)",(session["user_id"],d,cat,amount,desc))
        flash("Expense added successfully.","success")
    except ValueError: flash("Enter a valid date, category, description, and positive amount.","error")
    return redirect(url_for("dashboard"))

@app.post("/delete/<int:eid>")
@login_required
def delete(eid):
    with db_connect() as db: result=db.execute("DELETE FROM expenses WHERE id=? AND user_id=?",(eid,session["user_id"]))
    flash("Expense deleted." if result.rowcount else "Expense not found.","success" if result.rowcount else "error")
    return redirect(request.referrer or url_for("dashboard"))

@app.route("/reports")
@login_required
def reports():
    with db_connect() as db: rows=db.execute("SELECT expense_date,category,amount FROM expenses WHERE user_id=?",(session["user_id"],)).fetchall()
    monthly={}; cats={}
    for r in rows:
        key=r["expense_date"][:7]; monthly[key]=monthly.get(key,0)+r["amount"]; cats[r["category"]]=cats.get(r["category"],0)+r["amount"]
    return render_template("reports.html",monthly_data=sorted(monthly.items()),category_data=sorted(cats.items(),key=lambda x:x[1],reverse=True),total=sum(r["amount"] for r in rows),transaction_count=len(rows))

@app.route("/export.csv")
@login_required
def export():
    rows=expenses_for(session["user_id"],request.args.get("start_date",""),request.args.get("end_date",""),request.args.get("category",""),request.args.get("search",""))
    out=io.StringIO(); w=csv.writer(out); w.writerow(["Date","Category","Amount","Description"])
    for r in rows: w.writerow([datetime.strptime(r["expense_date"],"%Y-%m-%d").strftime("%d-%m-%Y"),r["category"],f'{r["amount"]:.2f}',r["description"]])
    return Response("\ufeff"+out.getvalue(),mimetype="text/csv",headers={"Content-Disposition":"attachment; filename=expense-report.csv"})

@app.route("/profile")
@login_required
def profile():
    with db_connect() as db:
        user=db.execute("SELECT * FROM users WHERE id=?",(session["user_id"],)).fetchone()
        count=db.execute("SELECT COUNT(*) n FROM expenses WHERE user_id=?",(session["user_id"],)).fetchone()["n"]
    return render_template("profile.html",user=user,count=count)

if __name__ == "__main__":
    init_db()
    app.run()