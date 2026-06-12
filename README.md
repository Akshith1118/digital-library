# Digital Library Management System

A full-stack, responsive, role-based Digital Library Management System built with **Python Flask**, **Bootstrap 5**, and a robust database design supporting both **MySQL** and a plug-and-play **SQLite fallback**.

---

## 🌟 Key Features

1. **Role-Based Access Control:** Distinct workflows, borrow limits, and dashboards for **Students**, **Teachers**, and **Administrators**.
2. **Password Security:** Salted and hashed password generation utilizing `pbkdf2:sha256` password hashing algorithm via `werkzeug.security`.
3. **Core Library System:** Search, filter, request, issue, and return books seamlessly. Stocks reduce automatically upon issue and increase on return.
4. **QR Code Generator:** Automatically generates high-definition QR codes for newly added books to facilitate quick scanning.
5. **Dynamic Fine Management:** Calculations trigger daily. Rules: No fines for the first 7 days, thereafter ₹10 per day.
6. **Robust Reports:** View audit trails, logs, and export database tables instantly to downloadable CSV files.
7. **Adaptive Dual Database Mode:** Attempts connection to a MySQL backend. If not configured or not accessible, it immediately boots a local SQLite workspace file (`library_local.db`) so the project can be previewed instantly.

---

## 📂 Project Structure

```
login-website/
│
├── app.py                      # Core Flask logic, routes, and data models
├── database.sql                # MySQL Schema definition and seed queries
├── library_local.db            # SQLite instance database file (created automatically)
├── requirements.txt            # System dependencies
├── README.md                   # Installation & Setup guide
│
├── static/
│   ├── css/
│   │   └── style.css           # Styling directives and custom dark mode parameters
│   ├── js/
│   │   └── app.js              # Theme switcher, search bars, and QR scan mocks
│   └── uploads/                # Cover images, generated QR codes, and profiles
│
└── templates/
    ├── index.html              # Home page and Login portal
    ├── register.html           # User registration form
    ├── admin_dashboard.html    # Admin panel home layout
    ├── user_dashboard.html     # Student & Teacher shared panel
    ├── book_management.html    # Inventory and book controls
    ├── user_management.html    # Admin panel member controller
    ├── reports.html            # Log views and export files
    └── profile.html            # Settings, picture uploads and password changes
```

---

## 🔧 Installation & Running Guide

### 1. Prerequisites
Ensure you have Python 3.8+ installed on your machine.

### 2. Install Dependencies
Run the command below in your workspace terminal to fetch the necessary packages:
```bash
pip install -r requirements.txt
```

### 3. Setup Database (Optional)
If using **MySQL**, log into your server and run the script inside [database.sql](file:///c:/Users/Akshith%20reddy/OneDrive/Desktop/login-website/database.sql):
```sql
SOURCE database.sql;
```
If you do not have MySQL running, the application will automatically create and seed the SQLite database file `library_local.db` upon initial startup.

### 4. Running the Web Application
Execute the command below:
```bash
python app.py
```
Open your browser and navigate to: `http://127.0.0.1:5000`

---

## 🔑 Seeding Credentials (Password: `password123`)

* **Admin:** `admin@library.com`
* **Teacher:** `teacher@library.com`
* **Student:** `student@library.com`
