package models

import "time"

type User struct {
	ID         int64      `json:"id"`
	Username   string     `json:"username"`
	Email      string     `json:"email"`
	Password   string     `json:"-"`
	Role       string     `json:"role"`
	IsAdmin    bool       `json:"is_admin"`
	Phone      string     `json:"phone"`
	Bio        string     `json:"bio"`
	Company    string     `json:"company"`
	Avatar     string     `json:"avatar"`
	APIKey     string     `json:"api_key,omitempty"`
	SecretData string     `json:"secret_data,omitempty"`
	LastLogin  *time.Time `json:"last_login"`
	CreatedAt  time.Time  `json:"created_at"`
	UpdatedAt  time.Time  `json:"updated_at"`
}

type Customer struct {
	ID          int64     `json:"id"`
	UserID      int64     `json:"user_id"`
	Name        string    `json:"name"`
	Email       string    `json:"email"`
	Phone       string    `json:"phone"`
	Company     string    `json:"company"`
	Position    string    `json:"position"`
	Description string    `json:"description"`
	Status      string    `json:"status"`
	Source      string    `json:"source"`
	Rating      int       `json:"rating"`
	Tags        string    `json:"tags"`
	CreatedAt   time.Time `json:"created_at"`
	UpdatedAt   time.Time `json:"updated_at"`
}

type Deal struct {
	ID           int64      `json:"id"`
	UserID       int64      `json:"user_id"`
	CustomerID   int64      `json:"customer_id"`
	CustomerName string     `json:"customer_name,omitempty"`
	Title        string     `json:"title"`
	Value        float64    `json:"value"`
	Currency     string     `json:"currency"`
	Stage        string     `json:"stage"`
	Probability  int        `json:"probability"`
	CloseDate    *time.Time `json:"close_date"`
	Notes        string     `json:"notes"`
	CreatedAt    time.Time  `json:"created_at"`
	UpdatedAt    time.Time  `json:"updated_at"`
}

type Note struct {
	ID         int64     `json:"id"`
	UserID     int64     `json:"user_id"`
	CustomerID int64     `json:"customer_id"`
	Content    string    `json:"content"`
	Pinned     bool      `json:"pinned"`
	CreatedAt  time.Time `json:"created_at"`
	UpdatedAt  time.Time `json:"updated_at"`
}

type Activity struct {
	ID          int64      `json:"id"`
	UserID      int64      `json:"user_id"`
	CustomerID  int64      `json:"customer_id"`
	DealID      *int64     `json:"deal_id"`
	Type        string     `json:"type"`
	Title       string     `json:"title"`
	Description string     `json:"description"`
	DueDate     *time.Time `json:"due_date"`
	Completed   bool       `json:"completed"`
	CompletedAt *time.Time `json:"completed_at"`
	CreatedAt   time.Time  `json:"created_at"`
	UpdatedAt   time.Time  `json:"updated_at"`
}

type Attachment struct {
	ID         int64     `json:"id"`
	UserID     int64     `json:"user_id"`
	CustomerID *int64    `json:"customer_id"`
	DealID     *int64    `json:"deal_id"`
	Filename   string    `json:"filename"`
	StoredName string    `json:"stored_name"`
	MimeType   string    `json:"mime_type"`
	Size       int64     `json:"size"`
	Path       string    `json:"path"`
	CreatedAt  time.Time `json:"created_at"`
}

type Webhook struct {
	ID        int64     `json:"id"`
	UserID    int64     `json:"user_id"`
	Name      string    `json:"name"`
	URL       string    `json:"url"`
	Events    string    `json:"events"`
	Secret    string    `json:"secret"`
	Active    bool      `json:"active"`
	LastError string    `json:"last_error"`
	CreatedAt time.Time `json:"created_at"`
	UpdatedAt time.Time `json:"updated_at"`
}

type EmailTemplate struct {
	ID        int64     `json:"id"`
	UserID    int64     `json:"user_id"`
	Name      string    `json:"name"`
	Subject   string    `json:"subject"`
	Body      string    `json:"body"`
	Variables string    `json:"variables"`
	CreatedAt time.Time `json:"created_at"`
	UpdatedAt time.Time `json:"updated_at"`
}

type PasswordReset struct {
	ID        int64     `json:"id"`
	Email     string    `json:"email"`
	Token     string    `json:"token"`
	Used      bool      `json:"used"`
	CreatedAt time.Time `json:"created_at"`
}

type Tag struct {
	ID        int64     `json:"id"`
	UserID    int64     `json:"user_id"`
	Name      string    `json:"name"`
	Color     string    `json:"color"`
	CreatedAt time.Time `json:"created_at"`
}

type AuditLog struct {
	ID         int64     `json:"id"`
	UserID     int64     `json:"user_id"`
	Action     string    `json:"action"`
	Resource   string    `json:"resource"`
	ResourceID int64     `json:"resource_id"`
	Details    string    `json:"details"`
	IPAddress  string    `json:"ip_address"`
	UserAgent  string    `json:"user_agent"`
	CreatedAt  time.Time `json:"created_at"`
}
