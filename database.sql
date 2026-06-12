-- MySQL Database Schema for Digital Library Management System

CREATE DATABASE IF NOT EXISTS library_db;
USE library_db;

-- 1. Users Table
CREATE TABLE IF NOT EXISTS users (
    id INT AUTO_INCREMENT PRIMARY KEY,
    fullname VARCHAR(150) NOT NULL,
    email VARCHAR(150) UNIQUE NOT NULL,
    password VARCHAR(255) NOT NULL,
    role ENUM('student', 'teacher', 'admin') NOT NULL DEFAULT 'student',
    status ENUM('active', 'blocked') NOT NULL DEFAULT 'active',
    profile_image VARCHAR(255) DEFAULT 'default_profile.png',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 2. Books Table
CREATE TABLE IF NOT EXISTS books (
    book_id INT AUTO_INCREMENT PRIMARY KEY,
    title VARCHAR(200) NOT NULL,
    author VARCHAR(150) NOT NULL,
    isbn VARCHAR(50) UNIQUE NOT NULL,
    category VARCHAR(100) NOT NULL,
    publisher VARCHAR(150) NOT NULL,
    quantity INT NOT NULL DEFAULT 1,
    available_quantity INT NOT NULL DEFAULT 1,
    cover_image VARCHAR(255) DEFAULT 'default_cover.png',
    qr_code_path VARCHAR(255) DEFAULT NULL
);

-- 3. Transactions Table
CREATE TABLE IF NOT EXISTS transactions (
    transaction_id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT,
    book_id INT,
    issue_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    due_date TIMESTAMP NOT NULL,
    return_date TIMESTAMP NULL DEFAULT NULL,
    status ENUM('requested', 'issued', 'returned', 'overdue') NOT NULL DEFAULT 'requested',
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (book_id) REFERENCES books(book_id) ON DELETE CASCADE
);

-- 4. Activity Logs Table
CREATE TABLE IF NOT EXISTS activity_logs (
    log_id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NULL,
    action VARCHAR(255) NOT NULL,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE SET NULL
);

-- Indexes for performance optimization
CREATE INDEX idx_user_email ON users(email);
CREATE INDEX idx_book_isbn ON books(isbn);
CREATE INDEX idx_transaction_status ON transactions(status);

-- Seed Sample Data (Password hashes are for "password123")
-- Admin: admin@library.com
-- Teacher: teacher@library.com
-- Student: student@library.com

INSERT INTO users (fullname, email, password, role, status) VALUES 
('System Admin', 'admin@library.com', 'pbkdf2:sha256:260000$cOqg2Kmx$8ef58c7cc6c54784de88bb5d70b7ad38260d3d52d9a6c22cfc1b827e8a9f02c6', 'admin', 'active'),
('Professor Alice', 'teacher@library.com', 'pbkdf2:sha256:260000$cOqg2Kmx$8ef58c7cc6c54784de88bb5d70b7ad38260d3d52d9a6c22cfc1b827e8a9f02c6', 'teacher', 'active'),
('Akshith Reddy', 'student@library.com', 'pbkdf2:sha256:260000$cOqg2Kmx$8ef58c7cc6c54784de88bb5d70b7ad38260d3d52d9a6c22cfc1b827e8a9f02c6', 'student', 'active');

INSERT INTO books (title, author, isbn, category, publisher, quantity, available_quantity) VALUES
('Introduction to Algorithms', 'Thomas H. Cormen', '978-0262033848', 'Scientific Research', 'MIT Press', 5, 5),
('A Brief History of Time', 'Stephen Hawking', '978-0553380163', 'Scientific Research', 'Bantam Books', 3, 3),
('The Story of Art', 'E.H. Gombrich', '978-0714833224', 'History & Arts', 'Phaidon Press', 2, 2),
('Design Patterns', 'Erich Gamma', '978-0201633610', 'Digital Archive', 'Addison-Wesley', 4, 4);