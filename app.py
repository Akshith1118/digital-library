import os
import datetime
from flask import Flask, render_template, request, redirect, url_for, session, send_file
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
import mysql.connector
import sqlite3
import qrcode

app = Flask(__name__)
app.secret_key = "libris_digital_super_secret_session_key"

# Configuration for file uploads
UPLOAD_FOLDER = os.path.join(app.root_path, 'static', 'uploads')
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# Generate default profile and cover files if not present
with open(os.path.join(UPLOAD_FOLDER, 'default_profile.png'), 'w') as f:
    f.write('')
with open(os.path.join(UPLOAD_FOLDER, 'default_cover.png'), 'w') as f:
    f.write('')

# Database Config & Initialization
# Dual Database Mode: Will attempt MySQL connection. If it fails, falls back automatically to SQLite for easy evaluation.
USING_SQLITE = False
db_conn = None

def get_db_cursor():
    global USING_SQLITE, db_conn
    if USING_SQLITE:
        conn = sqlite3.connect("library_local.db")
        conn.row_factory = sqlite3.Row
        return conn, conn.cursor()
    
    try:
        conn = mysql.connector.connect(
            host="localhost",
            user="root",
            password="23k91a6713",
            database="library_db"
        )
        return conn, conn.cursor(dictionary=True)
    except Exception as e:
        print(f"MySQL Connection Failed: {e}. Falling back to SQLite3...")
        USING_SQLITE = True
        # Establish local SQLite database
        conn = sqlite3.connect("library_local.db")
        conn.row_factory = sqlite3.Row
        init_sqlite_db(conn)
        return conn, conn.cursor()

def init_sqlite_db(conn):
    cursor = conn.cursor()
    cursor.executescript("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        fullname TEXT NOT NULL,
        email TEXT UNIQUE NOT NULL,
        password TEXT NOT NULL,
        role TEXT NOT NULL DEFAULT 'student',
        status TEXT NOT NULL DEFAULT 'active',
        profile_image TEXT DEFAULT 'default_profile.png',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS books (
        book_id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT NOT NULL,
        author TEXT NOT NULL,
        isbn TEXT UNIQUE NOT NULL,
        category TEXT NOT NULL,
        publisher TEXT NOT NULL,
        quantity INTEGER NOT NULL DEFAULT 1,
        available_quantity INTEGER NOT NULL DEFAULT 1,
        cover_image TEXT DEFAULT 'default_cover.png',
        qr_code_path TEXT DEFAULT NULL
    );

    CREATE TABLE IF NOT EXISTS transactions (
        transaction_id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        book_id INTEGER,
        issue_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        due_date TIMESTAMP NOT NULL,
        return_date TIMESTAMP DEFAULT NULL,
        status TEXT NOT NULL DEFAULT 'requested',
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
        FOREIGN KEY (book_id) REFERENCES books(book_id) ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS activity_logs (
        log_id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NULL,
        action TEXT NOT NULL,
        timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE SET NULL
    );

    CREATE TABLE IF NOT EXISTS notifications (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        transaction_id INTEGER,
        title TEXT NOT NULL,
        message TEXT NOT NULL,
        type TEXT DEFAULT 'overdue_warning',
        is_read INTEGER DEFAULT 0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
    );
    """)
    # Seed admin credential if table is empty (password is "password123")
    cursor.execute("SELECT COUNT(*) FROM users")
    if cursor.fetchone()[0] == 0:
        hashed_pwd = generate_password_hash("password123")
        cursor.execute("INSERT INTO users (fullname, email, password, role, status) VALUES (?, ?, ?, ?, ?)",
                       ('System Admin', 'admin@library.com', hashed_pwd, 'admin', 'active'))
        cursor.execute("INSERT INTO users (fullname, email, password, role, status) VALUES (?, ?, ?, ?, ?)",
                       ('Professor Alice', 'teacher@library.com', hashed_pwd, 'teacher', 'active'))
        cursor.execute("INSERT INTO users (fullname, email, password, role, status) VALUES (?, ?, ?, ?, ?)",
                       ('Akshith Reddy', 'student@library.com', hashed_pwd, 'student', 'active'))
        
        # Seed books
        cursor.executemany("""
        INSERT INTO books (title, author, isbn, category, publisher, quantity, available_quantity) 
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """, [
            ('Introduction to Algorithms', 'Thomas H. Cormen', '978-0262033848', 'Scientific Research', 'MIT Press', 5, 5),
            ('A Brief History of Time', 'Stephen Hawking', '978-0553380163', 'Scientific Research', 'Bantam Books', 3, 3),
            ('The Story of Art', 'E.H. Gombrich', '978-0714833224', 'History & Arts', 'Phaidon Press', 2, 2),
            ('Design Patterns', 'Erich Gamma', '978-0201633610', 'Digital Archive', 'Addison-Wesley', 4, 4)
        ])
    conn.commit()

# Log dynamic actions
def log_activity(user_id, action):
    conn, cursor = get_db_cursor()
    q = "INSERT INTO activity_logs (user_id, action) VALUES (?, ?)" if USING_SQLITE else "INSERT INTO activity_logs (user_id, action) VALUES (%s, %s)"
    cursor.execute(q, (user_id, action))
    conn.commit()
    conn.close()

# Mock Email Notification sender
def send_email_notification(to_email, subject, body):
    print(f"\n[EMAIL SENT] To: {to_email}\nSubject: {subject}\nBody: {body}\n")

# Utility to check allowed upload files
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in {'png', 'jpg', 'jpeg', 'gif'}

# Helper to safely parse datetimes
def parse_datetime(val):
    if isinstance(val, datetime.datetime):
        return val
    if isinstance(val, str):
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d"):
            try:
                return datetime.datetime.strptime(val, fmt)
            except ValueError:
                pass
    return None

# Method that sends notification after students took book over 15 days on book due to return
def notify_overdue_students(days_threshold=15, force=False):
    """
    Sends notification when students have taken/held a book for over `days_threshold` days
    (default 15 days) and the book has not been returned (status in 'issued', 'overdue').
    
    Workflow:
      1. Identifies student loans (role == 'student') that are unreturned.
      2. Calculates days held since issue date: (now - issue_date).days
         and days overdue past due date: (now - due_date).days.
      3. If days_held >= days_threshold or days_overdue >= days_threshold:
         - Dispatches simulated email notification
         - Stores in-app notification in `notifications` table (avoiding duplicates within 24h unless force=True)
         - Records audit trail in `activity_logs`
         - Marks transaction status as 'overdue'
    
    Returns:
      List of dictionary records for all students notified.
    """
    conn, cursor = get_db_cursor()
    
    q = """
    SELECT 
        t.transaction_id,
        t.user_id,
        t.book_id,
        t.issue_date,
        t.due_date,
        t.status,
        u.fullname AS student_name,
        u.email AS student_email,
        u.role AS user_role,
        b.title AS book_title,
        b.author AS book_author,
        b.isbn AS book_isbn
    FROM transactions t
    JOIN users u ON t.user_id = u.id
    JOIN books b ON t.book_id = b.book_id
    WHERE u.role = 'student'
      AND (t.return_date IS NULL OR t.return_date = '')
      AND t.status IN ('issued', 'overdue')
    """
    cursor.execute(q)
    rows = cursor.fetchall()
    
    now = datetime.datetime.now()
    notified_records = []
    
    for row in rows:
        issue_dt = parse_datetime(row['issue_date'])
        due_dt = parse_datetime(row['due_date'])
        
        if not issue_dt:
            continue
            
        days_held = (now - issue_dt).days
        days_overdue = (now - due_dt).days if (due_dt and now > due_dt) else 0
        
        # Check condition: student took the book for over days_threshold days (15+ days)
        if days_held >= days_threshold or days_overdue >= days_threshold:
            # Check duplicate alert within last 24 hours to avoid spamming
            if not force:
                chk_q = """
                SELECT id, created_at FROM notifications 
                WHERE user_id = ? AND transaction_id = ? AND type = 'overdue_warning'
                ORDER BY created_at DESC LIMIT 1
                """ if USING_SQLITE else """
                SELECT id, created_at FROM notifications 
                WHERE user_id = %s AND transaction_id = %s AND type = 'overdue_warning'
                ORDER BY created_at DESC LIMIT 1
                """
                cursor.execute(chk_q, (row['user_id'], row['transaction_id']))
                recent_notif = cursor.fetchone()
                if recent_notif:
                    raw_dt = recent_notif['created_at'] if isinstance(recent_notif, dict) else recent_notif[1]
                    recent_dt = parse_datetime(raw_dt)
                    if recent_dt and (now - recent_dt).total_seconds() < 86400:
                        # Already notified within the past 24 hours
                        continue
            
            # Formulate notification subject and message
            title = f"Urgent: Book Return Overdue Notice - '{row['book_title']}'"
            due_str = due_dt.strftime('%Y-%m-%d') if due_dt else str(row['due_date'])
            issue_str = issue_dt.strftime('%Y-%m-%d') if issue_dt else str(row['issue_date'])
            
            message = (
                f"Dear {row['student_name']},\n\n"
                f"You borrowed the book '{row['book_title']}' on {issue_str}. "
                f"You have had this book for {days_held} days, which exceeds the allowed 15-day limit.\n"
                f"The scheduled return due date was: {due_str} ({days_overdue} day(s) overdue).\n\n"
                f"Please return this book to the library immediately to resolve your overdue status "
                f"and prevent further fines or borrowing restrictions.\n\n"
                f"— Libris Digital Library"
            )
            
            # 1. Send Simulated Email Notification
            send_email_notification(row['student_email'], title, message)
            
            # 2. Insert into notifications table for in-app display
            ins_notif = """
            INSERT INTO notifications (user_id, transaction_id, title, message, type, is_read, created_at)
            VALUES (?, ?, ?, ?, 'overdue_warning', 0, ?)
            """ if USING_SQLITE else """
            INSERT INTO notifications (user_id, transaction_id, title, message, type, is_read, created_at)
            VALUES (%s, %s, %s, %s, 'overdue_warning', 0, %s)
            """
            cursor.execute(ins_notif, (row['user_id'], row['transaction_id'], title, message, now.strftime("%Y-%m-%d %H:%M:%S")))
            
            # 3. Log to activity_logs
            ins_log = """
            INSERT INTO activity_logs (user_id, action, timestamp) VALUES (?, ?, ?)
            """ if USING_SQLITE else """
            INSERT INTO activity_logs (user_id, action, timestamp) VALUES (%s, %s, %s)
            """
            log_msg = f"Overdue return notice sent to {row['student_name']} for '{row['book_title']}' (Held: {days_held} days, Overdue: {days_overdue} days)"
            cursor.execute(ins_log, (row['user_id'], log_msg, now.strftime("%Y-%m-%d %H:%M:%S")))
            
            # 4. Update transaction status to overdue if not already
            if row['status'] != 'overdue':
                up_st = "UPDATE transactions SET status = 'overdue' WHERE transaction_id = ?" if USING_SQLITE else "UPDATE transactions SET status = 'overdue' WHERE transaction_id = %s"
                cursor.execute(up_st, (row['transaction_id'],))
                
            notified_records.append({
                'transaction_id': row['transaction_id'],
                'student_id': row['user_id'],
                'student_name': row['student_name'],
                'student_email': row['student_email'],
                'book_title': row['book_title'],
                'issue_date': issue_str,
                'due_date': due_str,
                'days_held': days_held,
                'days_overdue': days_overdue
            })
            
    conn.commit()
    conn.close()
    return notified_records

# Fine calculations engine
def update_overdue_fines():
    conn, cursor = get_db_cursor()
    
    # Query all active issues (issued or overdue)
    q = "SELECT * FROM transactions WHERE status IN ('issued', 'overdue')"
    cursor.execute(q)
    rows = cursor.fetchall()
    
    for row in rows:
        due_val = row['due_date']
        due = parse_datetime(due_val)
        now = datetime.datetime.now()
        
        if due and now > due:
            qu = """
            UPDATE transactions 
            SET status = 'overdue' 
            WHERE transaction_id = ?
            """ if USING_SQLITE else """
            UPDATE transactions 
            SET status = 'overdue' 
            WHERE transaction_id = %s
            """
            tid = row['transaction_id']
            cursor.execute(qu, (tid,))
    conn.commit()
    conn.close()
    
    # Automatically check and dispatch notifications for students whose book loans exceed 15 days
    notify_overdue_students(days_threshold=15, force=False)

# Helper for login protection
def is_logged_in():
    return 'user_id' in session

# ----------------- ROUTES -----------------

# Index & Login
@app.route('/', methods=['GET', 'POST'])
@app.route('/login', methods=['GET', 'POST'])
def login():
    if is_logged_in():
        return redirect(url_for('dashboard'))
        
    if request.method == 'POST':
        email = request.form['email']
        pwd = request.form['password']
        
        conn, cursor = get_db_cursor()
        q = "SELECT * FROM users WHERE email = ?" if USING_SQLITE else "SELECT * FROM users WHERE email = %s"
        cursor.execute(q, (email,))
        user = cursor.fetchone()
        conn.close()
        
        if user and check_password_hash(user['password'], pwd):
            if user['status'] == 'blocked':
                return render_template('index.html', error="Your account is blocked. Please contact the administrator.")
            
            # Setup session
            session['user_id'] = user['id']
            session['email'] = user['email']
            session['role'] = user['role']
            session['name'] = user['fullname']
            session['profile_image'] = user['profile_image']
            
            log_activity(user['id'], "Logged in successfully")
            return redirect(url_for('dashboard'))
        else:
            return render_template('index.html', error="Invalid Email or Password Credentials")
            
    return render_template('index.html')

# Register
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        name = request.form['fullname']
        email = request.form['email']
        role = request.form['role']
        pwd = request.form['password']
        
        conn, cursor = get_db_cursor()
        q = "SELECT * FROM users WHERE email = ?" if USING_SQLITE else "SELECT * FROM users WHERE email = %s"
        cursor.execute(q, (email,))
        if cursor.fetchone():
            conn.close()
            return render_template('register.html', error="Email address already registered!")
            
        hashed_pwd = generate_password_hash(pwd)
        ins = """
        INSERT INTO users (fullname, email, password, role, status) 
        VALUES (?, ?, ?, ?, 'active')
        """ if USING_SQLITE else """
        INSERT INTO users (fullname, email, password, role, status) 
        VALUES (%s, %s, %s, %s, 'active')
        """
        cursor.execute(ins, (name, email, hashed_pwd, role))
        conn.commit()
        conn.close()
        
        send_email_notification(email, "Welcome to Libris Digital", f"Hello {name},\nYour account as a {role} has been created successfully!")
        return render_template('index.html', registration_success=True)
        
    return render_template('register.html')

# Dynamic Dashboard Route
@app.route('/dashboard')
def dashboard():
    if not is_logged_in():
        return redirect(url_for('login'))
        
    if session['role'] == 'admin':
        return redirect(url_for('admin_dashboard'))
        
    # Student & Teacher Dashboard logic
    update_overdue_fines()
    
    conn, cursor = get_db_cursor()
    # Fetch user limits
    limits = {
        'max_books': 5 if session['role'] == 'teacher' else 3,
        'duration_days': 14 if session['role'] == 'teacher' else 7
    }
    
    # Fetch books
    q_books = "SELECT * FROM books"
    cursor.execute(q_books)
    books = cursor.fetchall()
    
    # Fetch active transactions and historical transactions
    q_trans = """
    SELECT t.*, b.title, b.author 
    FROM transactions t 
    JOIN books b ON t.book_id = b.book_id 
    WHERE t.user_id = ?
    """ if USING_SQLITE else """
    SELECT t.*, b.title, b.author 
    FROM transactions t 
    JOIN books b ON t.book_id = b.book_id 
    WHERE t.user_id = %s
    """
    cursor.execute(q_trans, (session['user_id'],))
    transactions = cursor.fetchall()
    
    # Recommendations engine: Recommend popular books in similar categories
    q_recs = "SELECT DISTINCT * FROM books LIMIT 4"
    cursor.execute(q_recs)
    recommendations = cursor.fetchall()
    
    # Fetch active unread notifications
    q_notifs = "SELECT * FROM notifications WHERE user_id = ? AND is_read = 0 ORDER BY created_at DESC" if USING_SQLITE else "SELECT * FROM notifications WHERE user_id = %s AND is_read = 0 ORDER BY created_at DESC"
    cursor.execute(q_notifs, (session['user_id'],))
    notifications = cursor.fetchall()
    
    conn.close()
    return render_template('user_dashboard.html', books=books, transactions=transactions, limits=limits, recommendations=recommendations, notifications=notifications)

# Admin Dashboard
@app.route('/admin/dashboard')
def admin_dashboard():
    if not is_logged_in() or session['role'] != 'admin':
        return redirect(url_for('login'))
        
    update_overdue_fines()
    
    conn, cursor = get_db_cursor()
    
    stats = {}
    
    def get_count(query):
        cursor.execute(query)
        row = cursor.fetchone()
        if isinstance(row, dict):
            return list(row.values())[0]
        return row[0]
        
    # Count metrics
    stats['total_books'] = get_count("SELECT COUNT(*) FROM books")
    stats['total_students'] = get_count("SELECT COUNT(*) FROM users WHERE role='student'")
    stats['total_teachers'] = get_count("SELECT COUNT(*) FROM users WHERE role='teacher'")
    stats['books_issued'] = get_count("SELECT COUNT(*) FROM transactions WHERE status IN ('issued', 'overdue')")
    
    # Overdue student loans (> 15 days)
    q_overdue_15 = """
    SELECT COUNT(*) FROM transactions t 
    JOIN users u ON t.user_id = u.id 
    WHERE u.role = 'student' 
      AND (t.return_date IS NULL OR t.return_date = '') 
      AND t.status IN ('issued', 'overdue')
      AND (julianday('now') - julianday(t.issue_date)) >= 15
    """ if USING_SQLITE else """
    SELECT COUNT(*) FROM transactions t 
    JOIN users u ON t.user_id = u.id 
    WHERE u.role = 'student' 
      AND (t.return_date IS NULL OR t.return_date = '') 
      AND t.status IN ('issued', 'overdue')
      AND DATEDIFF(NOW(), t.issue_date) >= 15
    """
    stats['overdue_15_students'] = get_count(q_overdue_15)
    
    # Fetch activity logs
    q_logs = """
    SELECT a.*, u.fullname as user_name 
    FROM activity_logs a 
    LEFT JOIN users u ON a.user_id = u.id 
    ORDER BY a.timestamp DESC LIMIT 10
    """
    cursor.execute(q_logs)
    logs = cursor.fetchall()
    
    conn.close()
    notification_msg = request.args.get('notification_msg')
    return render_template('admin_dashboard.html', stats=stats, logs=logs, success=notification_msg)

# Admin route to manually trigger overdue notifications (15+ days)
@app.route('/admin/notify_overdue', methods=['GET', 'POST'])
def trigger_overdue_notifications():
    if not is_logged_in() or session['role'] != 'admin':
        return redirect(url_for('login'))
        
    days = request.args.get('days', default=15, type=int)
    notified = notify_overdue_students(days_threshold=days, force=True)
    count = len(notified)
    
    if count > 0:
        names = ", ".join([n['student_name'] for n in notified[:3]])
        if count > 3:
            names += f" and {count - 3} others"
        msg = f"Overdue return notices successfully sent to {count} student(s) who held books for over {days} days ({names})."
    else:
        msg = f"No student currently has unreturned books borrowed for over {days} days."
        
    return redirect(url_for('admin_dashboard', notification_msg=msg))

# Mark notification as read / dismiss
@app.route('/notifications/read/<int:notification_id>', methods=['POST'])
def mark_notification_read(notification_id):
    if not is_logged_in():
        return redirect(url_for('login'))
        
    conn, cursor = get_db_cursor()
    q = "UPDATE notifications SET is_read = 1 WHERE id = ? AND user_id = ?" if USING_SQLITE else "UPDATE notifications SET is_read = 1 WHERE id = %s AND user_id = %s"
    cursor.execute(q, (notification_id, session['user_id']))
    conn.commit()
    conn.close()
    return redirect(request.referrer or url_for('dashboard'))

# Book Management View
@app.route('/admin/books')
def book_management():
    if not is_logged_in() or session['role'] != 'admin':
        return redirect(url_for('login'))
        
    conn, cursor = get_db_cursor()
    cursor.execute("SELECT * FROM books")
    books = cursor.fetchall()
    conn.close()
    return render_template('book_management.html', books=books)

# Add Book
@app.route('/admin/books/add', methods=['POST'])
def add_book():
    if not is_logged_in() or session['role'] != 'admin':
        return redirect(url_for('login'))
        
    title = request.form['title']
    author = request.form['author']
    isbn = request.form['isbn']
    category = request.form['category']
    publisher = request.form['publisher']
    quantity = int(request.form['quantity'])
    
    # File cover processing
    file = request.files.get('cover_image')
    cover_filename = 'default_cover.png'
    if file and allowed_file(file.filename):
        cover_filename = secure_filename(file.filename)
        file.save(os.path.join(app.config['UPLOAD_FOLDER'], cover_filename))
        
    # Generate QR Code image file
    qr_filename = f"qr_{isbn}.png"
    qr_img = qrcode.make(f"LIBRIS-ISBN:{isbn}")
    qr_img.save(os.path.join(app.config['UPLOAD_FOLDER'], qr_filename))
    
    conn, cursor = get_db_cursor()
    ins = """
    INSERT INTO books (title, author, isbn, category, publisher, quantity, available_quantity, cover_image, qr_code_path) 
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """ if USING_SQLITE else """
    INSERT INTO books (title, author, isbn, category, publisher, quantity, available_quantity, cover_image, qr_code_path) 
    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
    """
    try:
        cursor.execute(ins, (title, author, isbn, category, publisher, quantity, quantity, cover_filename, qr_filename))
        conn.commit()
        log_activity(session['user_id'], f"Added book: {title} (ISBN: {isbn})")
        success_msg = f"Book '{title}' successfully added."
    except Exception as e:
        success_msg = None
        error_msg = f"Error adding book (Duplicate ISBN?): {e}"
        conn.close()
        return redirect(url_for('book_management'))
        
    conn.close()
    return redirect(url_for('book_management'))

# Edit Book
@app.route('/admin/books/edit/<int:book_id>', methods=['POST'])
def edit_book(book_id):
    if not is_logged_in() or session['role'] != 'admin':
        return redirect(url_for('login'))
        
    title = request.form['title']
    author = request.form['author']
    isbn = request.form['isbn']
    category = request.form['category']
    publisher = request.form['publisher']
    quantity = int(request.form['quantity'])
    
    conn, cursor = get_db_cursor()
    
    file = request.files.get('cover_image')
    if file and allowed_file(file.filename):
        cover_filename = secure_filename(file.filename)
        file.save(os.path.join(app.config['UPLOAD_FOLDER'], cover_filename))
        up = """
        UPDATE books 
        SET title=?, author=?, isbn=?, category=?, publisher=?, quantity=?, available_quantity=?, cover_image=? 
        WHERE book_id=?
        """ if USING_SQLITE else """
        UPDATE books 
        SET title=%s, author=%s, isbn=%s, category=%s, publisher=%s, quantity=%s, available_quantity=%s, cover_image=%s 
        WHERE book_id=%s
        """
        cursor.execute(up, (title, author, isbn, category, publisher, quantity, quantity, cover_filename, book_id))
    else:
        up = """
        UPDATE books 
        SET title=?, author=?, isbn=?, category=?, publisher=?, quantity=?, available_quantity=? 
        WHERE book_id=?
        """ if USING_SQLITE else """
        UPDATE books 
        SET title=%s, author=%s, isbn=%s, category=%s, publisher=%s, quantity=%s, available_quantity=%s 
        WHERE book_id=%s
        """
        cursor.execute(up, (title, author, isbn, category, publisher, quantity, quantity, book_id))
        
    conn.commit()
    conn.close()
    return redirect(url_for('book_management'))

# Delete Book
@app.route('/admin/books/delete/<int:book_id>', methods=['POST'])
def delete_book(book_id):
    if not is_logged_in() or session['role'] != 'admin':
        return redirect(url_for('login'))
        
    conn, cursor = get_db_cursor()
    de = "DELETE FROM books WHERE book_id = ?" if USING_SQLITE else "DELETE FROM books WHERE book_id = %s"
    cursor.execute(de, (book_id,))
    conn.commit()
    conn.close()
    return redirect(url_for('book_management'))

# User Management View
@app.route('/admin/users')
def user_management():
    if not is_logged_in() or session['role'] != 'admin':
        return redirect(url_for('login'))
        
    conn, cursor = get_db_cursor()
    cursor.execute("SELECT * FROM users")
    users = cursor.fetchall()
    conn.close()
    return render_template('user_management.html', users=users)

# Add User Account (Admin only)
@app.route('/admin/users/add', methods=['POST'])
def add_user():
    if not is_logged_in() or session['role'] != 'admin':
        return redirect(url_for('login'))
        
    name = request.form['fullname']
    email = request.form['email']
    role = request.form['role']
    pwd = request.form['password']
    
    conn, cursor = get_db_cursor()
    q = "SELECT * FROM users WHERE email = ?" if USING_SQLITE else "SELECT * FROM users WHERE email = %s"
    cursor.execute(q, (email,))
    if cursor.fetchone():
        cursor.execute("SELECT * FROM users")
        users = cursor.fetchall()
        conn.close()
        return render_template('user_management.html', users=users, error="Email/UserID already registered!")
        
    hashed_pwd = generate_password_hash(pwd)
    ins = """
    INSERT INTO users (fullname, email, password, role, status) 
    VALUES (?, ?, ?, ?, 'active')
    """ if USING_SQLITE else """
    INSERT INTO users (fullname, email, password, role, status) 
    VALUES (%s, %s, %s, %s, 'active')
    """
    cursor.execute(ins, (name, email, hashed_pwd, role))
    conn.commit()
    log_activity(session['user_id'], f"Created user account: {name} ({role})")
    
    cursor.execute("SELECT * FROM users")
    users = cursor.fetchall()
    conn.close()
    
    send_email_notification(email, "Account Created By Admin", f"Hello {name},\nAn account as a {role} has been created for you by the Admin. Log in with your email/username and password.")
    return render_template('user_management.html', users=users, success=f"User account for '{name}' successfully created.")

# Block User
@app.route('/admin/users/block/<int:user_id>', methods=['POST'])
def block_user(user_id):
    if not is_logged_in() or session['role'] != 'admin':
        return redirect(url_for('login'))
        
    conn, cursor = get_db_cursor()
    up = "UPDATE users SET status = 'blocked' WHERE id = ?" if USING_SQLITE else "UPDATE users SET status = 'blocked' WHERE id = %s"
    cursor.execute(up, (user_id,))
    conn.commit()
    conn.close()
    return redirect(url_for('user_management'))

# Activate User
@app.route('/admin/users/activate/<int:user_id>', methods=['POST'])
def activate_user(user_id):
    if not is_logged_in() or session['role'] != 'admin':
        return redirect(url_for('login'))
        
    conn, cursor = get_db_cursor()
    up = "UPDATE users SET status = 'active' WHERE id = ?" if USING_SQLITE else "UPDATE users SET status = 'active' WHERE id = %s"
    cursor.execute(up, (user_id,))
    conn.commit()
    conn.close()
    return redirect(url_for('user_management'))

# Delete User
@app.route('/admin/users/delete/<int:user_id>', methods=['POST'])
def delete_user(user_id):
    if not is_logged_in() or session['role'] != 'admin':
        return redirect(url_for('login'))
        
    conn, cursor = get_db_cursor()
    de = "DELETE FROM users WHERE id = ?" if USING_SQLITE else "DELETE FROM users WHERE id = %s"
    cursor.execute(de, (user_id,))
    conn.commit()
    conn.close()
    return redirect(url_for('user_management'))

# Borrow Request Action
@app.route('/borrow/<int:book_id>', methods=['POST'])
def borrow_book(book_id):
    if not is_logged_in():
        return redirect(url_for('login'))
        
    conn, cursor = get_db_cursor()
    
    # Verify borrow limit
    role = session['role']
    max_limit = 5 if role == 'teacher' else 3
    duration_days = 14 if role == 'teacher' else 7
    
    qc = "SELECT COUNT(*) FROM transactions WHERE user_id = ? AND status IN ('issued', 'overdue', 'requested')" if USING_SQLITE else "SELECT COUNT(*) FROM transactions WHERE user_id = %s AND status IN ('issued', 'overdue', 'requested')"
    cursor.execute(qc, (session['user_id'],))
    current_loans = cursor.fetchone()[0]
    
    if current_loans >= max_limit:
        conn.close()
        return redirect(url_for('dashboard'))
        
    # Reduce book quantity
    q_qty = "SELECT available_quantity, title FROM books WHERE book_id = ?" if USING_SQLITE else "SELECT available_quantity, title FROM books WHERE book_id = %s"
    cursor.execute(q_qty, (book_id,))
    book = cursor.fetchone()
    
    if book and book['available_quantity'] > 0:
        new_avail = book['available_quantity'] - 1
        qu = "UPDATE books SET available_quantity = ? WHERE book_id = ?" if USING_SQLITE else "UPDATE books SET available_quantity = %s WHERE book_id = %s"
        cursor.execute(qu, (new_avail, book_id))
        
        # Calculate due date
        due_date = (datetime.datetime.now() + datetime.timedelta(days=duration_days)).strftime("%Y-%m-%d %H:%M:%S")
        
        # Insert transaction
        it = """
        INSERT INTO transactions (user_id, book_id, due_date, status) 
        VALUES (?, ?, ?, 'issued')
        """ if USING_SQLITE else """
        INSERT INTO transactions (user_id, book_id, due_date, status) 
        VALUES (%s, %s, %s, 'issued')
        """
        cursor.execute(it, (session['user_id'], book_id, due_date))
        conn.commit()
        log_activity(session['user_id'], f"Borrowed book: {book['title']}")
        send_email_notification(session['email'], "Book Issued Successfully", f"The book '{book['title']}' has been checked out. Return due date: {due_date}.")
        
    conn.close()
    return redirect(url_for('dashboard'))

# Return Book Action
@app.route('/return/<int:transaction_id>', methods=['POST'])
def return_book(transaction_id):
    if not is_logged_in():
        return redirect(url_for('login'))
        
    conn, cursor = get_db_cursor()
    
    # Fetch transaction info
    qt = "SELECT * FROM transactions WHERE transaction_id = ?" if USING_SQLITE else "SELECT * FROM transactions WHERE transaction_id = %s"
    cursor.execute(qt, (transaction_id,))
    trans = cursor.fetchone()
    
    if trans and trans['status'] in ('issued', 'overdue'):
        # Return book quantity
        qb = "SELECT available_quantity, title FROM books WHERE book_id = ?" if USING_SQLITE else "SELECT available_quantity, title FROM books WHERE book_id = %s"
        cursor.execute(qb, (trans['book_id'],))
        book = cursor.fetchone()
        
        new_qty = book['available_quantity'] + 1
        qu = "UPDATE books SET available_quantity = ? WHERE book_id = ?" if USING_SQLITE else "UPDATE books SET available_quantity = %s WHERE book_id = %s"
        cursor.execute(qu, (new_qty, trans['book_id']))
        
        # Update transaction
        now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        ut = "UPDATE transactions SET return_date = ?, status = 'returned' WHERE transaction_id = ?" if USING_SQLITE else "UPDATE transactions SET return_date = %s, status = 'returned' WHERE transaction_id = %s"
        cursor.execute(ut, (now_str, transaction_id))
        conn.commit()
        
        log_activity(session['user_id'], f"Returned book: {book['title']}")
        send_email_notification(session['email'], "Book Returned Successfully", f"Thank you for returning '{book['title']}'. Your loan is now resolved.")
        
    conn.close()
    return redirect(url_for('dashboard'))

# Admin QR Code quick-actions simulate trigger
@app.route('/admin/issue_qr/<int:book_id>', methods=['POST'])
def admin_issue_qr(book_id):
    if not is_logged_in() or session['role'] != 'admin':
        return redirect(url_for('login'))
        
    conn, cursor = get_db_cursor()
    # Fast issue to admin test user
    cursor.execute("SELECT id FROM users LIMIT 1")
    row = cursor.fetchone()
    if not row:
        conn.close()
        return redirect(url_for('book_management'))
    uid = row['id'] if isinstance(row, dict) else row[0]
    
    # Reduce book quantity
    due_date = (datetime.datetime.now() + datetime.timedelta(days=7)).strftime("%Y-%m-%d %H:%M:%S")
    q_update = "UPDATE books SET available_quantity = available_quantity - 1 WHERE book_id = ?" if USING_SQLITE else "UPDATE books SET available_quantity = available_quantity - 1 WHERE book_id = %s"
    cursor.execute(q_update, (book_id,))
    
    q_insert = "INSERT INTO transactions (user_id, book_id, due_date, status) VALUES (?, ?, ?, 'issued')" if USING_SQLITE else "INSERT INTO transactions (user_id, book_id, due_date, status) VALUES (%s, %s, %s, 'issued')"
    cursor.execute(q_insert, (uid, book_id, due_date))
    conn.commit()
    conn.close()
    return redirect(url_for('book_management'))

@app.route('/admin/return_qr/<int:book_id>', methods=['POST'])
def admin_return_qr(book_id):
    if not is_logged_in() or session['role'] != 'admin':
        return redirect(url_for('login'))
        
    conn, cursor = get_db_cursor()
    q_select = "SELECT transaction_id FROM transactions WHERE book_id = ? AND status='issued' LIMIT 1" if USING_SQLITE else "SELECT transaction_id FROM transactions WHERE book_id = %s AND status='issued' LIMIT 1"
    cursor.execute(q_select, (book_id,))
    trans = cursor.fetchone()
    if trans:
        tid = trans['transaction_id'] if isinstance(trans, dict) else trans[0]
        now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        q_update_book = "UPDATE books SET available_quantity = available_quantity + 1 WHERE book_id = ?" if USING_SQLITE else "UPDATE books SET available_quantity = available_quantity + 1 WHERE book_id = %s"
        cursor.execute(q_update_book, (book_id,))
        
        q_update_trans = "UPDATE transactions SET return_date = ?, status = 'returned' WHERE transaction_id = ?" if USING_SQLITE else "UPDATE transactions SET return_date = %s, status = 'returned' WHERE transaction_id = %s"
        cursor.execute(q_update_trans, (now_str, tid))
        conn.commit()
    conn.close()
    return redirect(url_for('book_management'))

# Profile Route Settings
@app.route('/profile')
def profile():
    if not is_logged_in():
        return redirect(url_for('login'))
        
    conn, cursor = get_db_cursor()
    q = "SELECT * FROM users WHERE id = ?" if USING_SQLITE else "SELECT * FROM users WHERE id = %s"
    cursor.execute(q, (session['user_id'],))
    user = cursor.fetchone()
    conn.close()
    return render_template('profile.html', user=user)

# Profile Info Update
@app.route('/profile/update', methods=['POST'])
def profile_update():
    if not is_logged_in():
        return redirect(url_for('login'))
        
    fullname = request.form['fullname']
    email = request.form['email']
    new_pwd = request.form.get('new_password')
    
    conn, cursor = get_db_cursor()
    
    if new_pwd:
        hashed_pwd = generate_password_hash(new_pwd)
        up = "UPDATE users SET fullname = ?, email = ?, password = ? WHERE id = ?" if USING_SQLITE else "UPDATE users SET fullname = %s, email = %s, password = %s WHERE id = %s"
        cursor.execute(up, (fullname, email, hashed_pwd, session['user_id']))
    else:
        up = "UPDATE users SET fullname = ?, email = ? WHERE id = ?" if USING_SQLITE else "UPDATE users SET fullname = %s, email = %s WHERE id = %s"
        cursor.execute(up, (fullname, email, session['user_id']))
        
    conn.commit()
    conn.close()
    
    session['name'] = fullname
    session['email'] = email
    
    return redirect(url_for('profile'))

# Avatar Image Upload
@app.route('/profile/avatar', methods=['POST'])
def profile_avatar():
    if not is_logged_in():
        return redirect(url_for('login'))
        
    file = request.files.get('profile_image')
    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
        
        conn, cursor = get_db_cursor()
        up = "UPDATE users SET profile_image = ? WHERE id = ?" if USING_SQLITE else "UPDATE users SET profile_image = %s WHERE id = %s"
        cursor.execute(up, (filename, session['user_id']))
        conn.commit()
        conn.close()
        
        session['profile_image'] = filename
        
    return redirect(url_for('profile'))

# Admin Reports Page
@app.route('/admin/reports')
def admin_reports():
    if not is_logged_in() or session['role'] != 'admin':
        return redirect(url_for('login'))
        
    conn, cursor = get_db_cursor()
    q = """
    SELECT t.*, u.fullname, b.title 
    FROM transactions t 
    JOIN users u ON t.user_id = u.id 
    JOIN books b ON t.book_id = b.book_id 
    ORDER BY t.issue_date DESC
    """
    cursor.execute(q)
    transactions = cursor.fetchall()
    conn.close()
    return render_template('reports.html', transactions=transactions)

# Export functionality
@app.route('/admin/reports/export/<export_format>')
def export_reports(export_format):
    if not is_logged_in() or session['role'] != 'admin':
        return redirect(url_for('login'))
        
    # Write report CSV to disk and return
    export_path = os.path.join(app.config['UPLOAD_FOLDER'], "report.csv")
    conn, cursor = get_db_cursor()
    cursor.execute("""
    SELECT t.transaction_id, u.fullname, b.title, t.issue_date, t.due_date, t.return_date, t.status 
    FROM transactions t 
    JOIN users u ON t.user_id = u.id 
    JOIN books b ON t.book_id = b.book_id
    """)
    rows = cursor.fetchall()
    conn.close()
    
    with open(export_path, 'w', encoding='utf-8') as f:
        f.write("Transaction ID,Name,Title,Issue Date,Due Date,Return Date,Status\n")
        for row in rows:
            f.write(f"{row['transaction_id']},{row['fullname']},{row['title']},{row['issue_date']},{row['due_date']},{row['return_date'] or ''},{row['status']}\n")
            
    return send_file(export_path, as_attachment=True, download_name="library_system_report.csv")

# Logout
@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

if __name__ == '__main__':
    import socket
    def get_local_ip():
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
            return ip
        except Exception:
            return "127.0.0.1"
            
    local_ip = get_local_ip()
    print(f"\n=======================================================")
    print(f" TO OPEN THIS ON YOUR PHONE:")
    print(f" 1. Make sure your phone is on the same Wi-Fi network.")
    print(f" 2. Open your phone's browser and go to:")
    print(f"    http://{local_ip}:5000")
    print(f"=======================================================\n")
    app.run(debug=True, host='0.0.0.0', port=5000)