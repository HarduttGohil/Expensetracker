import pandas as pd
from flask import send_file
from flask import Flask, render_template, request, redirect
import psycopg2
import os


from flask_login import (
    LoginManager,
    UserMixin,
    login_user,
    login_required,
    logout_user,
    current_user
)

from werkzeug.security import (
    generate_password_hash,
    check_password_hash
)

app = Flask(__name__)

app.secret_key = "my_super_secret_key"
# Connect to Postgres via the shared transaction-mode pooler (IPv4-only)
DATABASE_URL = "postgresql://postgres.oncthwlejeeiaanrnwme:Expensetracker_0107@aws-1-ap-southeast-1.pooler.supabase.com:5432/postgres"
def get_connection():
    return psycopg2.connect(
    DATABASE_URL,
    sslmode="require"
)
# --------------------------
# LOGIN MANAGER
# --------------------------

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "login"


# --------------------------
# DATABASE
# --------------------------

def init_db():

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS users(
        id SERIAL PRIMARY KEY,
        username VARCHAR(255) UNIQUE,
        password TEXT
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS transactions(
        id SERIAL PRIMARY KEY,
        user_id INTEGER,
        date VARCHAR(50),
        type VARCHAR(50),
        category VARCHAR(255),
        amount DECIMAL
    )
    """)

    conn.commit()
    conn.close()


# --------------------------
# USER CLASS
# --------------------------

class User(UserMixin):

    def __init__(self, id, username):
        self.id = id
        self.username = username


@login_manager.user_loader
def load_user(user_id):

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT *
        FROM users
        WHERE id=%s
        """,
        (user_id,)
    )

    user = cursor.fetchone()

    conn.close()

    if user:
        return User(
            user[0],
            user[1]
        )

    return None


# --------------------------
# REGISTER
# --------------------------

@app.route("/register")
def register():
    return render_template("register.html")


@app.route("/register_user", methods=["POST"])
def register_user():

    username = request.form["username"]

    password = generate_password_hash(
        request.form["password"]
    )

    conn = get_connection()
    cursor = conn.cursor()

    try:

        cursor.execute(
            """
            INSERT INTO users
            (username, password)
            VALUES (%s, %s)
            """,
            (
                username,
                password
            )
        )

        conn.commit()

    except psycopg2.Error:

        conn.close()

        return "Username already exists"

    conn.close()

    return redirect("/login")


# --------------------------
# LOGIN
# --------------------------

@app.route("/login")
def login():
    return render_template("login.html")


@app.route("/login_user", methods=["POST"])
def login_user_route():

    username = request.form["username"]
    password = request.form["password"]

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT *
        FROM users
        WHERE username=%s
        """,
        (username,)
    )

    user = cursor.fetchone()

    conn.close()

    if user and check_password_hash(
        user[2],
        password
    ):

        login_user(
            User(
                user[0],
                user[1]
            )
        )

        return redirect("/")

    return "Invalid Username or Password"


# --------------------------
# LOGOUT
# --------------------------

@app.route("/logout")
@login_required
def logout():

    logout_user()

    return redirect("/login")


# --------------------------
# HOME PAGE
# --------------------------

@app.route("/")
@login_required
def index():

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT *
        FROM transactions
        WHERE user_id=%s
        ORDER BY id DESC
        """,
        (current_user.id,)
    )

    transactions = cursor.fetchall()

    cursor.execute(
        """
        SELECT COALESCE(SUM(amount),0)
        FROM transactions
        WHERE type='Income'
        AND user_id=%s
        """,
        (current_user.id,)
    )

    income = cursor.fetchone()[0]

    cursor.execute(
        """
        SELECT COALESCE(SUM(amount),0)
        FROM transactions
        WHERE type='Expense'
        AND user_id=%s
        """,
        (current_user.id,)
    )

    expense = cursor.fetchone()[0]

    balance = income - expense

    conn.close()

    return render_template(
        "index.html",
        transactions=transactions,
        income=income,
        expense=expense,
        balance=balance,
        username=current_user.username
    )


# --------------------------
# ADD TRANSACTION
# --------------------------

@app.route("/add", methods=["POST"])
@login_required
def add():

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        INSERT INTO transactions
        (
            user_id,
            date,
            type,
            category,
            amount
        )
        VALUES (%s, %s, %s, %s, %s)
        """,
        (
            current_user.id,
            request.form["date"],
            request.form["type"],
            request.form["category"],
            request.form["amount"]
        )
    )

    conn.commit()
    conn.close()

    return redirect("/")


# --------------------------
# DELETE TRANSACTION
# --------------------------

@app.route("/delete/<int:id>")
@login_required
def delete(id):

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        DELETE FROM transactions
        WHERE id=%s
        AND user_id=%s
        """,
        (
            id,
            current_user.id
        )
    )

    conn.commit()
    conn.close()

    return redirect("/")


# --------------------------
# SEARCH
# --------------------------

@app.route("/search")
@login_required
def search():

    keyword = request.args.get("keyword", "")

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT *
        FROM transactions
        WHERE user_id=%s
        AND category ILIKE %s
        ORDER BY id DESC
        """,
        (
            current_user.id,
            f"%{keyword}%"
        )
    )

    transactions = cursor.fetchall()

    conn.close()

    return render_template(
        "search.html",
        transactions=transactions,
        keyword=keyword
    )
@app.route("/export")
@login_required
def export_excel():

    conn = get_connection()

    query = """
        SELECT
        date,
        type,
        category,
        amount
        FROM transactions
        WHERE user_id=%s
    """

    df = pd.read_sql_query(
        query,
        conn,
        params=(current_user.id,)
    )

    file_name = "transactions.xlsx"

    df.to_excel(
        file_name,
        index=False
    )

    conn.close()

    return send_file(
        file_name,
        as_attachment=True
    )

@app.route("/monthly_report")
@login_required
def monthly_report():

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT
        substr(date,1,7) as month,

        SUM(
            CASE
            WHEN type='Income'
            THEN amount
            ELSE 0
            END
        ) as income,

        SUM(
            CASE
            WHEN type='Expense'
            THEN amount
            ELSE 0
            END
        ) as expense

        FROM transactions

        WHERE user_id=%s

        GROUP BY month

        ORDER BY month DESC
    """,
    (current_user.id,)
    )

    reports = cursor.fetchall()

    conn.close()

    return render_template(
        "monthly_report.html",
        reports=reports
    )

@app.route("/yearly_report")
@login_required
def yearly_report():

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT
        substr(date,1,4) as year,

        SUM(
            CASE
            WHEN type='Income'
            THEN amount
            ELSE 0
            END
        ) as income,

        SUM(
            CASE
            WHEN type='Expense'
            THEN amount
            ELSE 0
            END
        ) as expense

        FROM transactions

        WHERE user_id=%s

        GROUP BY year

        ORDER BY year DESC
    """,
    (current_user.id,)
    )

    reports = cursor.fetchall()

    conn.close()

    return render_template(
        "yearly_report.html",
        reports=reports
    )


@app.route("/edit/<int:id>")
@login_required
def edit(id):

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT *
        FROM transactions
        WHERE id=%s
        AND user_id=%s
        """,
        (
            id,
            current_user.id
        )
    )

    transaction = cursor.fetchone()

    conn.close()

    if not transaction:
        return "Transaction Not Found"

    return render_template(
        "edit.html",
        transaction=transaction
    )

@app.route("/update/<int:id>", methods=["POST"])
@login_required
def update(id):

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        UPDATE transactions
        SET
            date=%s,
            type=%s,
            category=%s,
            amount=%s
        WHERE id=%s
        AND user_id=%s
        """,
        (
            request.form["date"],
            request.form["type"],
            request.form["category"],
            request.form["amount"],
            id,
            current_user.id
        )
    )

    conn.commit()
    conn.close()

    return redirect("/")

@app.route("/users")
def users():

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT id, username FROM users")

    data = cursor.fetchall()

    conn.close()

    return str(data)

@app.route("/debug_users")
def debug_users():

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT username, password FROM users")
    data = cursor.fetchall()

    conn.close()

    return str(data)

@app.route("/test_db")
def test_db():

    try:

        conn = get_connection()
        cursor = conn.cursor()

        cursor.execute("SELECT NOW()")

        result = cursor.fetchone()

        conn.close()

        return f"Database Connected: {result}"

    except Exception as e:

        return str(e)

# --------------------------
# START APP
# --------------------------

init_db()
if __name__ == "__main__":
    app.run(debug=True)