package handlers

import (
	"bytes"
	"database/sql"
	"encoding/json"
	"io"
	"net/http"
	"net/url"
	"time"

	"crm/models"
	"crm/utils"

	"github.com/gin-gonic/gin"
)

func ListWebhooks(db *sql.DB) gin.HandlerFunc {
	return func(c *gin.Context) {
		userID := utils.GetUserID(c)
		rows, err := db.Query(`
			SELECT id, user_id, name, url, events, secret, active, last_error, created_at, updated_at
			FROM webhooks WHERE user_id = ?
			ORDER BY created_at DESC
		`, userID)
		if err != nil {
			c.JSON(http.StatusInternalServerError, gin.H{"error": "database error"})
			return
		}
		defer rows.Close()
		webhooks := []models.Webhook{}
		for rows.Next() {
			var w models.Webhook
			rows.Scan(&w.ID, &w.UserID, &w.Name, &w.URL, &w.Events, &w.Secret,
				&w.Active, &w.LastError, &w.CreatedAt, &w.UpdatedAt)
			w.Secret = "***" // mask secret in list view
			webhooks = append(webhooks, w)
		}
		c.JSON(http.StatusOK, gin.H{"data": webhooks, "count": len(webhooks)})
	}
}

func CreateWebhook(db *sql.DB) gin.HandlerFunc {
	return func(c *gin.Context) {
		userID := utils.GetUserID(c)
		var req struct {
			Name   string `json:"name"   binding:"required"`
			URL    string `json:"url"    binding:"required"`
			Events string `json:"events"`
		}
		if err := c.ShouldBindJSON(&req); err != nil {
			c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
			return
		}

		parsedURL, err := url.Parse(req.URL)
		if err != nil || (parsedURL.Scheme != "http" && parsedURL.Scheme != "https") {
			c.JSON(http.StatusBadRequest, gin.H{"error": "webhook URL must use HTTP or HTTPS"})
			return
		}

		secret := utils.GenerateSecret()
		if req.Events == "" {
			req.Events = `["*"]`
		}

		result, err := db.Exec(`
			INSERT INTO webhooks (user_id, name, url, events, secret, active, created_at, updated_at)
			VALUES (?, ?, ?, ?, ?, 1, datetime('now'), datetime('now'))
		`, userID, req.Name, req.URL, req.Events, secret)
		if err != nil {
			c.JSON(http.StatusInternalServerError, gin.H{"error": "failed to create webhook"})
			return
		}
		id, _ := result.LastInsertId()
		c.JSON(http.StatusCreated, gin.H{"message": "webhook created", "id": id, "secret": secret})
	}
}

func GetWebhook(db *sql.DB) gin.HandlerFunc {
	return func(c *gin.Context) {
		userID := utils.GetUserID(c)
		id := c.Param("id")
		var w models.Webhook
		err := db.QueryRow(`
			SELECT id, user_id, name, url, events, secret, active, last_error, created_at, updated_at
			FROM webhooks WHERE id = ? AND user_id = ?
		`, id, userID).Scan(&w.ID, &w.UserID, &w.Name, &w.URL, &w.Events, &w.Secret,
			&w.Active, &w.LastError, &w.CreatedAt, &w.UpdatedAt)
		if err == sql.ErrNoRows {
			c.JSON(http.StatusNotFound, gin.H{"error": "webhook not found"})
			return
		}
		if err != nil {
			c.JSON(http.StatusInternalServerError, gin.H{"error": "database error"})
			return
		}
		c.JSON(http.StatusOK, w)
	}
}

func UpdateWebhook(db *sql.DB) gin.HandlerFunc {
	return func(c *gin.Context) {
		userID := utils.GetUserID(c)
		id := c.Param("id")
		var req struct {
			Name   string `json:"name"`
			URL    string `json:"url"`
			Events string `json:"events"`
			Active *bool  `json:"active"`
		}
		if err := c.ShouldBindJSON(&req); err != nil {
			c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
			return
		}
		if req.URL != "" {
			parsedURL, err := url.Parse(req.URL)
			if err != nil || (parsedURL.Scheme != "http" && parsedURL.Scheme != "https") {
				c.JSON(http.StatusBadRequest, gin.H{"error": "webhook URL must use HTTP or HTTPS"})
				return
			}
		}
		active := 1
		if req.Active != nil && !*req.Active {
			active = 0
		}
		_, err := db.Exec(`
			UPDATE webhooks SET
				name       = COALESCE(NULLIF(?, ''), name),
				url        = COALESCE(NULLIF(?, ''), url),
				events     = COALESCE(NULLIF(?, ''), events),
				active     = ?,
				updated_at = datetime('now')
			WHERE id = ? AND user_id = ?
		`, req.Name, req.URL, req.Events, active, id, userID)
		if err != nil {
			c.JSON(http.StatusInternalServerError, gin.H{"error": "failed to update webhook"})
			return
		}
		c.JSON(http.StatusOK, gin.H{"message": "webhook updated"})
	}
}

func DeleteWebhook(db *sql.DB) gin.HandlerFunc {
	return func(c *gin.Context) {
		userID := utils.GetUserID(c)
		id := c.Param("id")
		db.Exec("DELETE FROM webhooks WHERE id = ? AND user_id = ?", id, userID)
		c.JSON(http.StatusOK, gin.H{"message": "webhook deleted"})
	}
}

// TestWebhook fires a synthetic event to the configured webhook endpoint.
// The response body and status code are returned to help the user debug connectivity.
func TestWebhook(db *sql.DB) gin.HandlerFunc {
	return func(c *gin.Context) {
		userID := utils.GetUserID(c)
		id := c.Param("id")

		var w models.Webhook
		err := db.QueryRow(`
			SELECT id, user_id, name, url, events, secret, active
			FROM webhooks WHERE id = ? AND user_id = ?
		`, id, userID).Scan(&w.ID, &w.UserID, &w.Name, &w.URL, &w.Events, &w.Secret, &w.Active)
		if err == sql.ErrNoRows {
			c.JSON(http.StatusNotFound, gin.H{"error": "webhook not found"})
			return
		}
		if err != nil {
			c.JSON(http.StatusInternalServerError, gin.H{"error": "database error"})
			return
		}

		// Validate that the stored URL uses an acceptable scheme.
		parsedURL, err := url.Parse(w.URL)
		if err != nil || (parsedURL.Scheme != "http" && parsedURL.Scheme != "https") {
			c.JSON(http.StatusBadRequest, gin.H{"error": "webhook has an invalid URL"})
			return
		}

		payload := map[string]interface{}{
			"event":     "webhook.test",
			"timestamp": time.Now().Unix(),
			"data":      gin.H{"message": "Test delivery from CRM Pro"},
		}
		payloadBytes, _ := json.Marshal(payload)

		client := &http.Client{Timeout: 15 * time.Second}
		req, err := http.NewRequest("POST", w.URL, bytes.NewReader(payloadBytes))
		if err != nil {
			c.JSON(http.StatusInternalServerError, gin.H{"error": "failed to build request"})
			return
		}
		req.Header.Set(utils.HeaderContentType, "application/json")
		req.Header.Set(utils.HeaderXCRMWebhookSecret, w.Secret)
		req.Header.Set(utils.HeaderXCRMEvent, "webhook.test")
		req.Header.Set(utils.HeaderUserAgent, "CRMPro-Webhook/2.1.4")

		resp, err := client.Do(req)
		if err != nil {
			db.Exec("UPDATE webhooks SET last_error = ? WHERE id = ?", err.Error(), w.ID)
			c.JSON(http.StatusOK, gin.H{"success": false, "error": err.Error()})
			return
		}
		defer resp.Body.Close()

		body, _ := io.ReadAll(io.LimitReader(resp.Body, 4096))
		db.Exec("UPDATE webhooks SET last_error = '', updated_at = datetime('now') WHERE id = ?", w.ID)

		c.JSON(http.StatusOK, gin.H{
			"success":     resp.StatusCode >= 200 && resp.StatusCode < 300,
			"status_code": resp.StatusCode,
			"response":    string(body),
		})
	}
}
