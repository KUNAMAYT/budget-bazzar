import os
import sqlite3
from datetime import date
from pathlib import Path

import psycopg
from dotenv import load_dotenv
from flask import Flask, jsonify, redirect, render_template, request, session, url_for
from psycopg.rows import dict_row
from werkzeug.security import check_password_hash, generate_password_hash

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent
DATABASE_URL = os.getenv("DATABASE_URL")
USE_POSTGRES = bool(DATABASE_URL)

if USE_POSTGRES:
    DATABASE = DATABASE_URL
else:
    DATA_DIR = Path(os.getenv("DATA_DIR", "/tmp" if os.getenv("VERCEL") else BASE_DIR))
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    DATABASE = DATA_DIR / "budget_bazzar.db"

app = Flask(__name__, template_folder=str(BASE_DIR), static_folder=str(BASE_DIR), static_url_path="/static")
app.secret_key = os.getenv("FLASK_SECRET_KEY") or (None if USE_POSTGRES else "dev-change-this-secret")
if not app.secret_key:
    raise RuntimeError("FLASK_SECRET_KEY must be set when DATABASE_URL is configured.")


def get_db():
    if USE_POSTGRES:
        return psycopg.connect(DATABASE, row_factory=dict_row)
    connection = sqlite3.connect(DATABASE)
    connection.row_factory = sqlite3.Row
    return connection


def execute(connection, query, parameters=()):
    if USE_POSTGRES:
        query = query.replace("?", "%s")
    return connection.execute(query, parameters)


def init_db():
    with get_db() as connection:
        if USE_POSTGRES:
            execute(connection, """CREATE TABLE IF NOT EXISTS users (
                id BIGSERIAL PRIMARY KEY,
                name TEXT NOT NULL,
                email TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
            )""")
            execute(connection, """CREATE TABLE IF NOT EXISTS transactions (
                id BIGSERIAL PRIMARY KEY,
                title TEXT NOT NULL,
                category TEXT NOT NULL,
                amount DOUBLE PRECISION NOT NULL CHECK(amount > 0),
                kind TEXT NOT NULL CHECK(kind IN ('income', 'expense')),
                transaction_date TEXT NOT NULL,
                user_id BIGINT REFERENCES users(id)
            )""")
            execute(connection, "ALTER TABLE transactions ADD COLUMN IF NOT EXISTS user_id BIGINT REFERENCES users(id)")
        else:
            execute(connection, """CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                email TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )""")
            execute(connection, """CREATE TABLE IF NOT EXISTS transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                category TEXT NOT NULL,
                amount REAL NOT NULL CHECK(amount > 0),
                kind TEXT NOT NULL CHECK(kind IN ('income', 'expense')),
                transaction_date TEXT NOT NULL
            )""")
            columns = {row[1] for row in execute(connection, "PRAGMA table_info(transactions)")}
            if "user_id" not in columns:
                execute(connection, "ALTER TABLE transactions ADD COLUMN user_id INTEGER REFERENCES users(id)")


def seed_transactions(user_id):
    examples = [
        ("Monthly salary", "Income", 4200, "income"),
        ("Apartment rent", "Home", 1250, "expense"),
        ("Grocery run", "Food", 186.45, "expense"),
        ("Freelance project", "Income", 850, "income"),
    ]
    with get_db() as connection:
        count = execute(connection, "SELECT COUNT(*) AS count FROM transactions WHERE user_id = ?", (user_id,)).fetchone()["count"]
        if count == 0:
            for title, category, amount, kind in examples:
                execute(connection, "INSERT INTO transactions (title, category, amount, kind, transaction_date, user_id) VALUES (?, ?, ?, ?, ?, ?)", (title, category, amount, kind, str(date.today()), user_id))


@app.before_request
def require_login():
    if request.path.startswith("/api/transactions") and "user_id" not in session:
        return jsonify({"error": "Login required."}), 401
    return None


@app.get("/")
def home():
    if "user_id" not in session:
        return redirect(url_for("login_page"))
    return render_template("index.html")


@app.get("/login")
def login_page():
    if "user_id" in session:
        return redirect(url_for("home"))
    return render_template("auth.html")


@app.post("/api/auth/register")
def register():
    payload = request.get_json(silent=True) or {}
    name = str(payload.get("name", "")).strip()
    email = str(payload.get("email", "")).strip().lower()
    password = str(payload.get("password", ""))
    if not name or "@" not in email or len(password) < 8:
        return jsonify({"error": "Name, valid email, and an 8-character password are required."}), 400
    try:
        with get_db() as connection:
            sql = "INSERT INTO users (name, email, password_hash) VALUES (?, ?, ?)"
            if USE_POSTGRES:
                sql += " RETURNING id"
            cursor = execute(connection, sql, (name, email, generate_password_hash(password)))
            user_id = cursor.fetchone()["id"] if USE_POSTGRES else cursor.lastrowid
    except (sqlite3.IntegrityError, psycopg.IntegrityError):
        return jsonify({"error": "An account with this email already exists."}), 409
    session["user_id"] = user_id
    session["user_name"] = name
    seed_transactions(user_id)
    return jsonify({"name": name, "email": email}), 201


@app.post("/api/auth/login")
def login():
    payload = request.get_json(silent=True) or {}
    email = str(payload.get("email", "")).strip().lower()
    password = str(payload.get("password", ""))
    with get_db() as connection:
        user = execute(connection, "SELECT * FROM users WHERE email = ?", (email,)).fetchone()
    if not user or not check_password_hash(user["password_hash"], password):
        return jsonify({"error": "Email or password is incorrect."}), 401
    session["user_id"] = user["id"]
    session["user_name"] = user["name"]
    seed_transactions(user["id"])
    return jsonify({"name": user["name"], "email": user["email"]})


@app.post("/api/auth/logout")
def logout():
    session.clear()
    return jsonify({"logged_out": True})


@app.get("/api/auth/me")
def current_user():
    if "user_id" not in session:
        return jsonify({"error": "Login required."}), 401
    return jsonify({"name": session["user_name"]})


@app.get("/api/transactions")
def list_transactions():
    with get_db() as connection:
        rows = execute(connection, "SELECT * FROM transactions WHERE user_id = ? ORDER BY transaction_date DESC, id DESC", (session["user_id"],)).fetchall()
    return jsonify([dict(row) for row in rows])


@app.post("/api/transactions")
def add_transaction():
    payload = request.get_json(silent=True) or {}
    title = str(payload.get("title", "")).strip()
    category = str(payload.get("category", "Other")).strip() or "Other"
    kind = payload.get("kind")
    transaction_date = payload.get("transaction_date") or str(date.today())
    try:
        amount = float(payload.get("amount", 0))
    except (TypeError, ValueError):
        amount = 0
    if not title or kind not in {"income", "expense"} or amount <= 0:
        return jsonify({"error": "Title, type, and a positive amount are required."}), 400
    with get_db() as connection:
        sql = "INSERT INTO transactions (title, category, amount, kind, transaction_date, user_id) VALUES (?, ?, ?, ?, ?, ?)"
        if USE_POSTGRES:
            sql += " RETURNING id"
        cursor = execute(connection, sql, (title, category, amount, kind, transaction_date, session["user_id"]))
        transaction_id = cursor.fetchone()["id"] if USE_POSTGRES else cursor.lastrowid
        row = execute(connection, "SELECT * FROM transactions WHERE id = ? AND user_id = ?", (transaction_id, session["user_id"])).fetchone()
    return jsonify(dict(row)), 201


@app.delete("/api/transactions/<int:transaction_id>")
def delete_transaction(transaction_id):
    with get_db() as connection:
        result = execute(connection, "DELETE FROM transactions WHERE id = ? AND user_id = ?", (transaction_id, session["user_id"]))
    if result.rowcount == 0:
        return jsonify({"error": "Transaction not found."}), 404
    return jsonify({"deleted": transaction_id})


@app.get("/api/health")
def health():
    return jsonify({"status": "ok", "service": "Budget Bazzar"})


init_db()

if __name__ == "__main__":
    app.run(host="0.0.0.0", debug=os.getenv("FLASK_DEBUG", "0") == "1", port=int(os.getenv("PORT", "5000")))
