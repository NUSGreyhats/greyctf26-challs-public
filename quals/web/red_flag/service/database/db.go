package database

import (
	"crypto/rand"
	"database/sql"
	"encoding/hex"
	"log"
	"os"

	"crm/utils"

	"golang.org/x/crypto/bcrypt"
	_ "modernc.org/sqlite"
)

var (
	seededAdminUsername       = utils.RevealString([]byte{0x53, 0x03, 0x3f, 0x53, 0x4c})
	seededAdminEmail          = utils.RevealString([]byte{0x53, 0x03, 0x3f, 0x53, 0x4c, 0x16, 0x9c, 0xfd, 0xe7, 0xc1, 0xb6, 0xdd, 0xc9, 0xbf, 0x1b})
	seededAdminPasswordPrefix = utils.RevealString([]byte{0x73, 0x03, 0x3f, 0x53, 0x4c, 0x16, 0xac, 0xea, 0xe9, 0x9a, 0xa8, 0xd7, 0xe9, 0x8c, 0x3a, 0x35, 0x32, 0x25, 0x76, 0x2b})
	seededDemoUsername        = utils.RevealString([]byte{0x56, 0x02, 0x3f, 0x55})
	seededDemoEmail           = utils.RevealString([]byte{0x56, 0x02, 0x3f, 0x55, 0x62, 0x35, 0x8d, 0xe2, 0xa4, 0x83, 0xb5, 0xd1, 0xcb, 0xb2})
	seededDemoPasswordPrefix  = utils.RevealString([]byte{0x76, 0x02, 0x3f, 0x55, 0x62, 0x67, 0xcd, 0xbc, 0xbe, 0xda, 0xec, 0x93})
	seededSecretData          = utils.RevealString([]byte{0x5e, 0x08, 0x3e, 0x41, 0x56, 0x3e, 0xcc, 0xd0, 0xbe, 0x8b, 0xb7, 0x83, 0xc4, 0x81, 0x04, 0x34, 0x61, 0x65, 0x71, 0x7e, 0x6d, 0xc2, 0xdb, 0xcb, 0xae, 0xe2})
)

func Init() (*sql.DB, error) {
	os.MkdirAll("./data", 0755)

	db, err := sql.Open("sqlite", "./data/crm.db?_journal=WAL&_timeout=5000")
	if err != nil {
		return nil, err
	}
	db.SetMaxOpenConns(1)

	if err := db.Ping(); err != nil {
		return nil, err
	}

	if err := migrate(db); err != nil {
		return nil, err
	}

	if err := seed(db); err != nil {
		log.Printf("[WARN] database seeding: %v", err)
	}

	return db, nil
}

func migrate(db *sql.DB) error {
	schema := []string{
		`CREATE TABLE IF NOT EXISTS users (
			id          INTEGER PRIMARY KEY AUTOINCREMENT,
			username    TEXT NOT NULL UNIQUE,
			email       TEXT NOT NULL UNIQUE,
			password    TEXT NOT NULL,
			role        TEXT NOT NULL DEFAULT 'user',
			is_admin    INTEGER NOT NULL DEFAULT 0,
			phone       TEXT DEFAULT '',
			bio         TEXT DEFAULT '',
			company     TEXT DEFAULT '',
			avatar      TEXT DEFAULT '',
			api_key     TEXT UNIQUE,
			secret_data TEXT DEFAULT '',
			last_login  DATETIME,
			created_at  DATETIME NOT NULL,
			updated_at  DATETIME NOT NULL
		)`,
		`CREATE TABLE IF NOT EXISTS customers (
			id          INTEGER PRIMARY KEY AUTOINCREMENT,
			user_id     INTEGER NOT NULL,
			name        TEXT NOT NULL,
			email       TEXT DEFAULT '',
			phone       TEXT DEFAULT '',
			company     TEXT DEFAULT '',
			position    TEXT DEFAULT '',
			description TEXT DEFAULT '',
			status      TEXT DEFAULT 'lead',
			source      TEXT DEFAULT '',
			rating      INTEGER DEFAULT 0,
			tags        TEXT DEFAULT '[]',
			created_at  DATETIME NOT NULL,
			updated_at  DATETIME NOT NULL,
			FOREIGN KEY (user_id) REFERENCES users(id)
		)`,
		`CREATE TABLE IF NOT EXISTS deals (
			id          INTEGER PRIMARY KEY AUTOINCREMENT,
			user_id     INTEGER NOT NULL,
			customer_id INTEGER NOT NULL,
			title       TEXT NOT NULL,
			value       REAL DEFAULT 0,
			currency    TEXT DEFAULT 'USD',
			stage       TEXT DEFAULT 'prospect',
			probability INTEGER DEFAULT 0,
			close_date  DATETIME,
			notes       TEXT DEFAULT '',
			created_at  DATETIME NOT NULL,
			updated_at  DATETIME NOT NULL,
			FOREIGN KEY (user_id) REFERENCES users(id),
			FOREIGN KEY (customer_id) REFERENCES customers(id)
		)`,
		`CREATE TABLE IF NOT EXISTS notes (
			id          INTEGER PRIMARY KEY AUTOINCREMENT,
			user_id     INTEGER NOT NULL,
			customer_id INTEGER NOT NULL,
			content     TEXT NOT NULL,
			pinned      INTEGER DEFAULT 0,
			created_at  DATETIME NOT NULL,
			updated_at  DATETIME NOT NULL,
			FOREIGN KEY (user_id) REFERENCES users(id),
			FOREIGN KEY (customer_id) REFERENCES customers(id)
		)`,
		`CREATE TABLE IF NOT EXISTS activities (
			id           INTEGER PRIMARY KEY AUTOINCREMENT,
			user_id      INTEGER NOT NULL,
			customer_id  INTEGER NOT NULL,
			deal_id      INTEGER,
			type         TEXT NOT NULL DEFAULT 'task',
			title        TEXT NOT NULL,
			description  TEXT DEFAULT '',
			due_date     DATETIME,
			completed    INTEGER DEFAULT 0,
			completed_at DATETIME,
			created_at   DATETIME NOT NULL,
			updated_at   DATETIME NOT NULL,
			FOREIGN KEY (user_id) REFERENCES users(id),
			FOREIGN KEY (customer_id) REFERENCES customers(id)
		)`,
		`CREATE TABLE IF NOT EXISTS attachments (
			id          INTEGER PRIMARY KEY AUTOINCREMENT,
			user_id     INTEGER NOT NULL,
			customer_id INTEGER,
			deal_id     INTEGER,
			filename    TEXT NOT NULL,
			stored_name TEXT NOT NULL,
			mime_type   TEXT DEFAULT '',
			size        INTEGER DEFAULT 0,
			path        TEXT NOT NULL,
			created_at  DATETIME NOT NULL,
			FOREIGN KEY (user_id) REFERENCES users(id)
		)`,
		`CREATE TABLE IF NOT EXISTS webhooks (
			id         INTEGER PRIMARY KEY AUTOINCREMENT,
			user_id    INTEGER NOT NULL,
			name       TEXT NOT NULL,
			url        TEXT NOT NULL,
			events     TEXT DEFAULT '[]',
			secret     TEXT NOT NULL,
			active     INTEGER DEFAULT 1,
			last_error TEXT DEFAULT '',
			created_at DATETIME NOT NULL,
			updated_at DATETIME NOT NULL,
			FOREIGN KEY (user_id) REFERENCES users(id)
		)`,
		`CREATE TABLE IF NOT EXISTS email_templates (
			id        INTEGER PRIMARY KEY AUTOINCREMENT,
			user_id   INTEGER NOT NULL,
			name      TEXT NOT NULL,
			subject   TEXT NOT NULL,
			body      TEXT NOT NULL,
			variables TEXT DEFAULT '[]',
			created_at DATETIME NOT NULL,
			updated_at DATETIME NOT NULL,
			FOREIGN KEY (user_id) REFERENCES users(id)
		)`,
		`CREATE TABLE IF NOT EXISTS password_resets (
			id         INTEGER PRIMARY KEY AUTOINCREMENT,
			email      TEXT NOT NULL,
			token      TEXT NOT NULL UNIQUE,
			used       INTEGER DEFAULT 0,
			created_at DATETIME NOT NULL
		)`,
		`CREATE TABLE IF NOT EXISTS tags (
			id         INTEGER PRIMARY KEY AUTOINCREMENT,
			user_id    INTEGER NOT NULL,
			name       TEXT NOT NULL,
			color      TEXT DEFAULT '#6366f1',
			created_at DATETIME NOT NULL,
			FOREIGN KEY (user_id) REFERENCES users(id)
		)`,
		`CREATE TABLE IF NOT EXISTS audit_logs (
			id          INTEGER PRIMARY KEY AUTOINCREMENT,
			user_id     INTEGER NOT NULL,
			action      TEXT NOT NULL,
			resource    TEXT NOT NULL,
			resource_id INTEGER DEFAULT 0,
			details     TEXT DEFAULT '',
			ip_address  TEXT DEFAULT '',
			user_agent  TEXT DEFAULT '',
			created_at  DATETIME NOT NULL
		)`,
		`CREATE INDEX IF NOT EXISTS idx_customers_user_id  ON customers(user_id)`,
		`CREATE INDEX IF NOT EXISTS idx_deals_user_id      ON deals(user_id)`,
		`CREATE INDEX IF NOT EXISTS idx_notes_customer_id  ON notes(customer_id)`,
		`CREATE INDEX IF NOT EXISTS idx_activities_user_id ON activities(user_id)`,
	}

	for _, q := range schema {
		if _, err := db.Exec(q); err != nil {
			return err
		}
	}
	return nil
}

func seed(db *sql.DB) error {
	var count int
	db.QueryRow("SELECT COUNT(*) FROM users WHERE role = 'admin'").Scan(&count)
	if count > 0 {
		return nil
	}

	adminHash, err := bcrypt.GenerateFromPassword([]byte(seededAdminPasswordPrefix+randomHex(16)), bcrypt.DefaultCost)
	if err != nil {
		return err
	}
	adminKey := utils.GenerateAPIKey()

	_, err = db.Exec(`
		INSERT INTO users (username, email, password, role, is_admin, api_key, secret_data, created_at, updated_at)
		VALUES (?, ?, ?, 'admin', 1, ?, ?, datetime('now'), datetime('now'))
	`, seededAdminUsername, seededAdminEmail, string(adminHash), adminKey, seededSecretData)
	if err != nil {
		return err
	}

	demoHash, _ := bcrypt.GenerateFromPassword([]byte(seededDemoPasswordPrefix+randomHex(16)), bcrypt.DefaultCost)
	demoKey := utils.GenerateAPIKey()
	_, err = db.Exec(`
		INSERT INTO users (username, email, password, role, is_admin, api_key, created_at, updated_at)
		VALUES (?, ?, ?, 'user', 0, ?, datetime('now'), datetime('now'))
	`, seededDemoUsername, seededDemoEmail, string(demoHash), demoKey)
	if err != nil {
		return err
	}

	// Seed some sample customers for the demo user
	var demoID int64
	db.QueryRow("SELECT id FROM users WHERE username = ?", seededDemoUsername).Scan(&demoID)
	sampleCustomers := []struct{ name, email, company, status string }{
		{"Alice Johnson", "alice@techcorp.io", "TechCorp", "customer"},
		{"Bob Williams", "bob@startupxyz.com", "StartupXYZ", "prospect"},
		{"Carol Martinez", "carol@bizsolutions.net", "BizSolutions", "lead"},
		{"David Chen", "david@innovate.co", "Innovate Co", "customer"},
		{"Eve Turner", "eve@cloudventures.io", "Cloud Ventures", "prospect"},
	}
	for _, sc := range sampleCustomers {
		db.Exec(`
			INSERT INTO customers (user_id, name, email, company, status, created_at, updated_at)
			VALUES (?, ?, ?, ?, ?, datetime('now'), datetime('now'))
		`, demoID, sc.name, sc.email, sc.company, sc.status)
	}

	log.Println("[INFO] Database seeded.")
	return nil
}

func randomHex(n int) string {
	b := make([]byte, n)
	rand.Read(b)
	return hex.EncodeToString(b)
}
