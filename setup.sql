-- 1. 既存テーブルのクリーンアップ（外部キーの依存関係順に削除）
DROP TABLE IF EXISTS payments;
DROP TABLE IF EXISTS analysis;
DROP TABLE IF EXISTS order_items;
DROP TABLE IF EXISTS order_counts;
DROP TABLE IF EXISTS orders;
DROP TABLE IF EXISTS products;
DROP TABLE IF EXISTS admins;
DROP TABLE IF EXISTS ledger;
DROP TABLE IF EXISTS users;

-- ==========================================
-- A. 分散管理データ（ブロックチェーン領域）
-- ※このデータは3台で完全に一致させる必要があります
-- ==========================================

-- ユーザーテーブル（暗号化鍵を含む）
CREATE TABLE users (
    user_id CHAR(36) PRIMARY KEY,
    user_name VARCHAR(32) NOT NULL,
    user_password VARCHAR(255) NOT NULL,
    security_code_hash VARCHAR(255) NOT NULL,
    balance INT DEFAULT 0,
    point INT DEFAULT 0,
    login_attempt_count INT DEFAULT 0,
    is_lockout BOOLEAN DEFAULT FALSE,
    encrypted_private_key TEXT NOT NULL, 
    public_key TEXT NOT NULL
);

-- ブロックチェーン台帳
CREATE TABLE ledger (
    height SERIAL PRIMARY KEY,
    prev_hash VARCHAR(64) NOT NULL,
    curr_hash VARCHAR(64) NOT NULL,
    sender_id CHAR(36) NOT NULL,
    amount INT NOT NULL,
    signature TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Genesis Block（初期ブロック）
INSERT INTO ledger (prev_hash, curr_hash, sender_id, amount, signature)
VALUES ('0', 'GENESIS_HASH', 'SYSTEM', 0, 'SYSTEM_SIG');

-- テストユーザー (本来はJava側で鍵生成して登録しますが、初期値としてダミーを入れます)
-- ※実運用の際はJava側でUPDATEしてください
INSERT INTO users (user_id, user_name, user_password, security_code_hash, balance, point, encrypted_private_key, public_key)
VALUES ('user001', 'TestUser', 'pass', '03ac674216f3e15c761ee1a5e255f067953623c8b388b4459e13f978d7c846f4', 50000, 100, 'DUMMY_ENC_KEY', 'DUMMY_PUB_KEY');


-- ==========================================
-- B. 店舗データ（業務アプリケーション領域）
-- ※今回は可用性のため、これらも3台に書き込みます
-- ==========================================

-- 管理者
CREATE TABLE admins (
    admin_name VARCHAR(32) PRIMARY KEY, 
    admin_password VARCHAR(255)
);

-- 商品マスタ
CREATE TABLE products (
    product_id VARCHAR(32) PRIMARY KEY, 
    product_name VARCHAR(64), 
    image BLOB, 
    category VARCHAR(32), 
    price INT, 
    sales_status VARCHAR(32), 
    update_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- 注文集計
CREATE TABLE order_counts (
    product_id VARCHAR(32) PRIMARY KEY, 
    order_count_from_single_adult INT DEFAULT 0, 
    order_count_from_two_adults INT DEFAULT 0, 
    order_count_from_family_group INT DEFAULT 0, 
    order_count_from_adult_group INT DEFAULT 0, 
    order_count_from_group INT DEFAULT 0, 
    FOREIGN KEY (product_id) REFERENCES products(product_id)
);

-- 注文ヘッダ
CREATE TABLE orders (
    order_id CHAR(36) PRIMARY KEY, 
    table_number CHAR(4), 
    adult_count INT, 
    child_count INT, 
    is_payment_completed BOOLEAN DEFAULT FALSE, 
    visit_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- 注文明細
CREATE TABLE order_items (
    order_item_id CHAR(36) PRIMARY KEY, 
    order_id CHAR(36), 
    product_id VARCHAR(32), 
    quantity INT, 
    price INT, 
    add_order_at DATETIME, 
    order_completed_at DATETIME, 
    order_status VARCHAR(32), 
    FOREIGN KEY (order_id) REFERENCES orders(order_id), 
    FOREIGN KEY (product_id) REFERENCES products(product_id)
);

-- 決済履歴（店舗控え）
CREATE TABLE payments (
    order_id CHAR(36) PRIMARY KEY, 
    user_id CHAR(36), 
    used_points INT, 
    earned_points INT, 
    payment_completed_at DATETIME, 
    FOREIGN KEY (order_id) REFERENCES orders(order_id)
);

-- 分析用
CREATE TABLE analysis (
    product_id VARCHAR(32), 
    customer_segment VARCHAR(32), 
    order_count INT, 
    update_date DATETIME, 
    FOREIGN KEY (product_id) REFERENCES products(product_id)
);

-- 初期商品データ
INSERT INTO products (product_id, product_name, price, sales_status) 
VALUES ('DRINK0001', 'Beer', 500, 'ON_SALE');