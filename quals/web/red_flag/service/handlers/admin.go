package handlers

import (
	"database/sql"
	"net/http"
	"os"
	"time"

	"crm/config"
	"crm/models"
	"crm/utils"

	"github.com/gin-gonic/gin"
	"github.com/golang-jwt/jwt/v4"
)

func AdminListUsers(db *sql.DB) gin.HandlerFunc {
	return func(c *gin.Context) {
		limit, offset := utils.PaginationParams(c)
		rows, err := db.Query(`
			SELECT id, username, email, role, is_admin, phone, company, last_login, created_at, updated_at
			FROM users ORDER BY created_at DESC LIMIT ? OFFSET ?
		`, limit, offset)
		if err != nil {
			c.JSON(http.StatusInternalServerError, gin.H{"error": "database error"})
			return
		}
		defer rows.Close()
		users := []models.User{}
		for rows.Next() {
			var u models.User
			rows.Scan(&u.ID, &u.Username, &u.Email, &u.Role, &u.IsAdmin,
				&u.Phone, &u.Company, &u.LastLogin, &u.CreatedAt, &u.UpdatedAt)
			users = append(users, u)
		}
		var total int
		db.QueryRow("SELECT COUNT(*) FROM users").Scan(&total)
		c.JSON(http.StatusOK, gin.H{"data": users, "total": total, "limit": limit, "offset": offset})
	}
}

func AdminGetUser(db *sql.DB) gin.HandlerFunc {
	return func(c *gin.Context) {
		id := c.Param("id")
		var u models.User
		err := db.QueryRow(`
			SELECT id, username, email, role, is_admin, phone, bio, company, avatar,
			       api_key, secret_data, last_login, created_at, updated_at
			FROM users WHERE id = ?
		`, id).Scan(
			&u.ID, &u.Username, &u.Email, &u.Role, &u.IsAdmin, &u.Phone, &u.Bio,
			&u.Company, &u.Avatar, &u.APIKey, &u.SecretData, &u.LastLogin, &u.CreatedAt, &u.UpdatedAt,
		)
		if err == sql.ErrNoRows {
			c.JSON(http.StatusNotFound, gin.H{"error": "user not found"})
			return
		}
		if err != nil {
			c.JSON(http.StatusInternalServerError, gin.H{"error": "database error"})
			return
		}
		c.JSON(http.StatusOK, u)
	}
}

func AdminUpdateUserRole(db *sql.DB) gin.HandlerFunc {
	return func(c *gin.Context) {
		id := c.Param("id")
		var req struct {
			Role    string `json:"role"     binding:"required"`
			IsAdmin bool   `json:"is_admin"`
		}
		if err := c.ShouldBindJSON(&req); err != nil {
			c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
			return
		}
		_, err := db.Exec(`
			UPDATE users SET role = ?, is_admin = ?, updated_at = datetime('now') WHERE id = ?
		`, req.Role, req.IsAdmin, id)
		if err != nil {
			c.JSON(http.StatusInternalServerError, gin.H{"error": "failed to update role"})
			return
		}
		callerID := utils.GetUserID(c)
		utils.LogAudit(db, callerID, "admin_update_role", "user", 0, "Updated role for user id="+id, c)
		c.JSON(http.StatusOK, gin.H{"message": "role updated"})
	}
}

func AdminDeleteUser(db *sql.DB) gin.HandlerFunc {
	return func(c *gin.Context) {
		id := c.Param("id")
		callerID := utils.GetUserID(c)
		if id == "1" {
			c.JSON(http.StatusForbidden, gin.H{"error": "cannot delete the primary admin account"})
			return
		}
		db.Exec("DELETE FROM users WHERE id = ?", id)
		utils.LogAudit(db, callerID, "admin_delete_user", "user", 0, "Deleted user id="+id, c)
		c.JSON(http.StatusOK, gin.H{"message": "user deleted"})
	}
}

func GetAuditLogs(db *sql.DB) gin.HandlerFunc {
	return func(c *gin.Context) {
		limit, offset := utils.PaginationParams(c)
		filterUser := c.Query("user_id")

		query := `
			SELECT al.id, al.user_id, u.username, al.action, al.resource,
			       al.resource_id, al.details, al.ip_address, al.user_agent, al.created_at
			FROM audit_logs al
			LEFT JOIN users u ON al.user_id = u.id
		`
		args := []interface{}{}
		if filterUser != "" {
			query += " WHERE al.user_id = ?"
			args = append(args, filterUser)
		}
		query += " ORDER BY al.created_at DESC LIMIT ? OFFSET ?"
		args = append(args, limit, offset)

		rows, err := db.Query(query, args...)
		if err != nil {
			c.JSON(http.StatusInternalServerError, gin.H{"error": "database error"})
			return
		}
		defer rows.Close()

		type logRow struct {
			ID         int64     `json:"id"`
			UserID     int64     `json:"user_id"`
			Username   string    `json:"username"`
			Action     string    `json:"action"`
			Resource   string    `json:"resource"`
			ResourceID int64     `json:"resource_id"`
			Details    string    `json:"details"`
			IPAddress  string    `json:"ip_address"`
			UserAgent  string    `json:"user_agent"`
			CreatedAt  time.Time `json:"created_at"`
		}
		logs := []logRow{}
		for rows.Next() {
			var lr logRow
			rows.Scan(&lr.ID, &lr.UserID, &lr.Username, &lr.Action, &lr.Resource,
				&lr.ResourceID, &lr.Details, &lr.IPAddress, &lr.UserAgent, &lr.CreatedAt)
			logs = append(logs, lr)
		}
		c.JSON(http.StatusOK, gin.H{"data": logs})
	}
}

// ImpersonateUser issues a short-lived JWT for the target user.
// Intended for support and debugging by administrators.
func ImpersonateUser(db *sql.DB) gin.HandlerFunc {
	return func(c *gin.Context) {
		targetID := c.Param("user_id")
		var u models.User
		err := db.QueryRow("SELECT id, email, role, is_admin FROM users WHERE id = ?", targetID).
			Scan(&u.ID, &u.Email, &u.Role, &u.IsAdmin)
		if err == sql.ErrNoRows {
			c.JSON(http.StatusNotFound, gin.H{"error": "user not found"})
			return
		}

		claims := jwt.MapClaims{
			"sub":           u.ID,
			"email":         u.Email,
			"role":          u.Role,
			"is_admin":      u.IsAdmin,
			"impersonating": true,
			"iat":           time.Now().Unix(),
			"exp":           time.Now().Add(1 * time.Hour).Unix(),
		}
		token, err := jwt.NewWithClaims(jwt.SigningMethodHS256, claims).SignedString([]byte(config.JWTSecret))
		if err != nil {
			c.JSON(http.StatusInternalServerError, gin.H{"error": "failed to issue token"})
			return
		}

		callerID := utils.GetUserID(c)
		utils.LogAudit(db, callerID, "impersonate", "user", u.ID, "Admin impersonated user id="+targetID, c)

		c.JSON(http.StatusOK, gin.H{
			"token":   token,
			"user_id": u.ID,
			"email":   u.Email,
			"expires": time.Now().Add(1 * time.Hour),
		})
	}
}

func AdminStats(db *sql.DB) gin.HandlerFunc {
	return func(c *gin.Context) {
		stats := map[string]int{}
		tables := []string{"users", "customers", "deals", "notes", "activities", "attachments", "webhooks", "audit_logs"}
		for _, t := range tables {
			var cnt int
			db.QueryRow("SELECT COUNT(*) FROM " + t).Scan(&cnt)
			stats[t] = cnt
		}
		c.JSON(http.StatusOK, gin.H{"stats": stats, "generated_at": time.Now()})
	}
}

// DebugInfo exposes internal runtime configuration.
// Enabled only when APP_ENV != "production" (config.Debug == true).
func DebugInfo(db *sql.DB) gin.HandlerFunc {
	return func(c *gin.Context) {
		var userCount, customerCount, dealCount int
		db.QueryRow("SELECT COUNT(*) FROM users").Scan(&userCount)
		db.QueryRow("SELECT COUNT(*) FROM customers").Scan(&customerCount)
		db.QueryRow("SELECT COUNT(*) FROM deals").Scan(&dealCount)

		c.JSON(http.StatusOK, gin.H{
			"app": gin.H{
				"name":    config.AppName,
				"version": config.AppVersion,
				"debug":   config.Debug,
			},
			"config": gin.H{
				"jwt_secret":    config.JWTSecret,
				"admin_api_key": config.AdminKey,
				"db_path":       config.DBPath,
				"upload_dir":    config.UploadDir,
				"smtp_host":     config.SMTPHost,
				"base_url":      config.BaseURL,
			},
			"database": gin.H{
				"users":     userCount,
				"customers": customerCount,
				"deals":     dealCount,
			},
			"environment": os.Environ(),
		})
	}
}

func HealthCheck(db *sql.DB) gin.HandlerFunc {
	return func(c *gin.Context) {
		if err := db.Ping(); err != nil {
			c.JSON(http.StatusServiceUnavailable, gin.H{"status": "unhealthy", "db": err.Error()})
			return
		}
		c.JSON(http.StatusOK, gin.H{
			"status":  "ok",
			"version": config.AppVersion,
			"time":    time.Now(),
		})
	}
}
