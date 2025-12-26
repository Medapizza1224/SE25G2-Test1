# データベース設計

## 改版履歴
| 日付 | メンバー | バージョン | 概要 |
| :--- | :--- | :--- | :--- |
| 2025/12/13 | 蓬莱、星野、小野田 | 1.0 | 初版作成 |
| 2025/12/15 | 蓬莱、星野、小野田 | 1.1 | 初版修正 |
| 2025/12/16 | 蓬莱、星野、小野田 | 1.2 | 初版修正 |
| 2025/12/18 | 蓬莱、星野、小野田 | 1.3 | インスペクション後修正 |
| 2025/12/19 | 蓬莱、星野、小野田 | 1.4 | インスペクション後再修正 |
---


## テーブル一覧定義

データベース名：order_payment_db

| No | テーブル論理名 | テーブル名 | 概要 |
| :--- | :--- | :--- | :--- |
| 1 | 管理者情報テーブル | admins | システム管理者のログイン情報や名前を管理する |
| 2 | 商品情報テーブル | products | 提供するメニューの商品名、価格、画像、カテゴリなどを管理する |
| 3 | 注文数テーブル | order_counts | 客層ごとの注文数を管理する |
| 4 | 伝票情報テーブル | orders | 来店ごとの伝票情報、人数、合計金額などのヘッダー情報を管理する |
| 5 | 注文項目テーブル | order_items | 伝票ごとの具体的な注文商品、数量、注文時の価格などを管理する |
| 6 | ユーザー情報テーブル | users | 顧客（ユーザー）のID、認証情報、残高、ポイントなどを管理する |
| 7 | 決済情報テーブル | payments | 伝票に対する支払い完了日時、利用・付与ポイントなどの決済実績を管理する |

<br>

## 各テーブル詳細

### **テーブル名：Admins (管理者情報)**

| No | カラム名 | データ型 | Not Null | Key | 和名（備考） |
| :--- | :--- | :--- | :--- | :--- | :--- |
| 1 | admin_name | VARCHAR(32) | YES | PRIMARY | 管理者名 (固定値) |
| 2 | admin_password | VARCHAR(255) | YES | | パスワード (固定値/ハッシュ化) |


<br>

### **テーブル名：Products (商品情報)**

| No | カラム名 | データ型 | Not Null | Key | 和名（備考） |
| :--- | :--- | :--- | :--- | :--- | :--- |
| 1 | product_id | VARCHAR(32) | YES | PRIMARY | 商品ID (例: DRINK0001) |
| 2 | product_name | VARCHAR(64) | YES | | 商品名 |
| 3 | image | BLOB | YES | | 商品画像 |
| 4 | category | VARCHAR(32) | YES | | カテゴリ |
| 5 | price | INT | YES | | 価格 (0円以上) |
| 6 | sales_status | VARCHAR(32) | YES | | 販売状況（販売中・準備中） |
| 7 | update_at | DATETIME | YES | | 更新日時 |

<br>


### **テーブル名： OrderCounts(注文数情報)**

| No | カラム名 | データ型 | Not Null | Key | 和名（備考） |
| :--- | :--- | :--- | :--- | :--- | :--- |
| 1 | product_id | VARCHAR(32) | YES | PRIMARY | 商品ID (例: DRINK0001) |
| 2 | order_count_from_single_adult | INT | NO | | １人のお客様が注文した数 |
| 3 | order_count_from_two_adults | INT | NO | | 2人のお客様が注文した数 |
| 4 | order_count_from_family_group | INT | NO | | ファミリー（大人1人から2人＋子供1から7人）のお客様が注文した数 |
| 5 | order_count_from_adult_group | INT | NO | | 大人グループ（大人3人から8人）のお客様が注文した数 |
| 6 | order_count_from_group | INT | NO | | グループ（大人3人から7人＋子供1人から5人）のお客様が注文した数 |


### **テーブル名：Orders (伝票情報)**

| No | カラム名 | データ型 | Not Null | Key | 和名（備考） |
| :--- | :--- | :--- | :--- | :--- | :--- |
| 1 | order_id | UUID | YES | PRIMARY | 伝票ID |
| 2 | table_number | CHAR(4) | YES | | テーブル番号 (4桁の数字（0000から9999）)|
| 3 | adult_count | INT | YES | | 大人人数 (1人から8人) |
| 4 | child_count | INT | YES | | 子供人数 (0人から7人) |
| 5 | is_payment_completed | BOOL | YES | | 決済完了（デフォルトでFALSEを設定） |
| 6 | visit_at | DATETIME | YES | | 来店日時 |

<br>


### **テーブル名：OrderItems (注文項目情報)**

| No | カラム名 | データ型 | Not Null | Key | 和名（備考） |
| :--- | :--- | :--- | :--- | :--- | :--- |
| 1 | order_item_id | UUID | YES | PRIMARY | 注文項目ID |
| 2 | order_id | UUID | YES | FOREIGN | 伝票ID  |
| 3 | product_id | VARCHAR(32) | YES | FOREIGN | 商品ID |
| 4 | quantity | INT | YES | | 個数 (1個から10個) |
| 5 | price | INT | YES | | 価格 |
| 6 | add_order_at | DATETIME | YES | | 注文カゴ追加日時 |
| 7 | order_completerd_at | DATETIME | NO | | 注文確定日時 |
| 8 | order_status | VARCHAR(32) | YES | | 注文状況 (注文カゴ・調理中・提供済) |

<br>

### **テーブル名：Users (ユーザー情報)**

| No | カラム名 | データ型 | Not Null | Key | 和名（備考） |
| :--- | :--- | :--- | :--- | :--- | :--- |
| 1 | user_id | UUID | YES | PRIMARY | ユーザーID |
| 2 | user_name | VARCHAR(32) | YES | | ユーザー名 (8から32文字) |
| 3 | usesr_password | VARCHAR(255) | YES | | パスワード (ハッシュ化) |
| 4 | security_code | VARCHAR(255) | YES | | セキュリティーコード (4桁数字をハッシュ化) |
| 5 | balance | INT | YES | | 残高 (0円から500,000円) |
| 6 | point | INT | YES | | ポイント数 |
| 7 | login_attempt_count | INT | YES | | 試行回数（ログイン・決済失敗回数：3回失敗でユーザーロックアウト） |
| 8 | is_lockout | BOOL | YES | | ユーザーロックアウト |

<br>

### **テーブル名：Payments (決済情報)**

| No | カラム名 | データ型 | Not Null | Key | Comment |
| :--- | :--- | :--- | :--- | :--- | :--- |
| 1 | order_id | UUID | YES | PRIMARY | 伝票ID  |
| 2 | user_id | UUID | YES | FOREIGN | ユーザーID  |
| 3 | used_points | INT | NO | | 利用ポイント（0ポイントから合計金額） |
| 4 | earned_points | INT | YES | | 付与ポイント（決済金額の1%を付与し、端数は切り捨て） |
| 5 | payment_completed_at | DATETIME | YES | | 決済日時 |

<br>

### **テーブル名：Analysis (分析情報)**

| No | カラム名 | データ型 | Not Null | Key | 和名（備考） |
| :--- | :--- | :--- | :--- | :--- | :--- |
| 1 | product_id | VARCHAR(32) | YES | FOREIGN | 商品ID |
| 2 | customer_segment | VARCHAR(32) | YES | | 客層（大人1人・大人2人・ファミリー・大人グループ・グループ） |
| 3 | order_count | INT | YES | | 注文数 |
| 4 | update_date | DATETIME | YES | | 更新日時 |
