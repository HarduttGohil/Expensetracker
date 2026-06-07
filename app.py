import pandas as pd
from flask import send_file
from flask import Flask, render_template, request, redirect
import sqlite3

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

DATABASE = "finance.db"

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

    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS users(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE,
        password TEXT
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS transactions(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    date TEXT,
    type TEXT,
    category TEXT,
    amount REAL
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

    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()

    cursor.execute(
        "SELECT * FROM users WHERE id=?",
        (user_id,)
    )

    user = cursor.fetchone()

    conn.close()

    if user:
        return User(user[0], user[1])

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

    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()

    try:

        cursor.execute(
            """
            INSERT INTO users
            (username, password)
            VALUES (?, ?)
            """,
            (
                username,
                password
            )
        )

        conn.commit()

    except sqlite3.IntegrityError:

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

    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT *
        FROM users
        WHERE username=?
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

    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT *
        FROM transactions
        WHERE user_id=?
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
        AND user_id=?
        """,
        (current_user.id,)
    )

    income = cursor.fetchone()[0]

    cursor.execute(
        """
        SELECT COALESCE(SUM(amount),0)
        FROM transactions
        WHERE type='Expense'
        AND user_id=?
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

    conn = sqlite3.connect(DATABASE)
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
        VALUES (?, ?, ?, ?, ?)
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

    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()

    cursor.execute(
        """
        DELETE FROM transactions
        WHERE id=?
        AND user_id=?
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

    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT *
        FROM transactions
        WHERE user_id=?
        AND (
            category LIKE ?
            OR description LIKE ?
        )
        ORDER BY id DESC
        """,
        (
            current_user.id,
            f"%{keyword}%",
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

    conn = sqlite3.connect(DATABASE)

    query = """
        SELECT
        date,
        type,
        category,
        amount,
        description
        FROM transactions
        WHERE user_id=?
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

# --------------------------
# START APP
# --------------------------

if __name__ == "__main__":

    init_db()

    app.run(debug=True)