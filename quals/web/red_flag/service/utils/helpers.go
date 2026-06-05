package utils

import (
	"crypto/rand"
	"database/sql"
	"encoding/hex"
	"strconv"
	"time"

	"github.com/gin-gonic/gin"
)

func GetUserID(c *gin.Context) int64 {
	userID, _ := c.Get("user_id")
	switch v := userID.(type) {
	case int64:
		return v
	case float64:
		return int64(v)
	default:
		return 0
	}
}

func GetUserRole(c *gin.Context) string {
	role, _ := c.Get("user_role")
	if r, ok := role.(string); ok {
		return r
	}
	return "user"
}

func IsAdmin(c *gin.Context) bool {
	isAdmin, _ := c.Get("is_admin")
	if a, ok := isAdmin.(bool); ok {
		return a
	}
	return false
}

func PaginationParams(c *gin.Context) (int, int) {
	limit, _ := strconv.Atoi(c.DefaultQuery("limit", "20"))
	offset, _ := strconv.Atoi(c.DefaultQuery("offset", "0"))
	if limit <= 0 || limit > 200 {
		limit = 20
	}
	if offset < 0 {
		offset = 0
	}
	return limit, offset
}

func GenerateAPIKey() string {
	b := make([]byte, 32)
	rand.Read(b)
	return "crm_" + hex.EncodeToString(b)
}

func GenerateSecret() string {
	b := make([]byte, 16)
	rand.Read(b)
	return hex.EncodeToString(b)
}

func LogAudit(db *sql.DB, userID int64, action, resource string, resourceID int64, details string, c *gin.Context) {
	ip := c.ClientIP()
	ua := c.Request.UserAgent()
	db.Exec(`
		INSERT INTO audit_logs (user_id, action, resource, resource_id, details, ip_address, user_agent, created_at)
		VALUES (?, ?, ?, ?, ?, ?, ?, datetime('now'))
	`, userID, action, resource, resourceID, details, ip, ua)
}

func NullableTime(s string) *time.Time {
	if s == "" {
		return nil
	}
	t, err := time.Parse(time.RFC3339, s)
	if err != nil {
		return nil
	}
	return &t
}

func NullInt64(v int64) *int64 {
	if v == 0 {
		return nil
	}
	return &v
}
