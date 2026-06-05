package handlers

import (
	"bytes"
	"database/sql"
	"fmt"
	"net/http"
	"strings"
	texttemplate "text/template"
	"time"

	"crm/models"
	"crm/utils"

	"github.com/gin-gonic/gin"
)

func ListEmailTemplates(db *sql.DB) gin.HandlerFunc {
	return func(c *gin.Context) {
		userID := utils.GetUserID(c)
		rows, err := db.Query(`
			SELECT id, user_id, name, subject, variables, created_at, updated_at
			FROM email_templates WHERE user_id = ?
			ORDER BY created_at DESC
		`, userID)
		if err != nil {
			c.JSON(http.StatusInternalServerError, gin.H{"error": "database error"})
			return
		}
		defer rows.Close()
		templates := []models.EmailTemplate{}
		for rows.Next() {
			var t models.EmailTemplate
			rows.Scan(&t.ID, &t.UserID, &t.Name, &t.Subject, &t.Variables, &t.CreatedAt, &t.UpdatedAt)
			templates = append(templates, t)
		}
		c.JSON(http.StatusOK, gin.H{"data": templates, "count": len(templates)})
	}
}

func CreateEmailTemplate(db *sql.DB) gin.HandlerFunc {
	return func(c *gin.Context) {
		userID := utils.GetUserID(c)
		var req struct {
			Name      string `json:"name"    binding:"required"`
			Subject   string `json:"subject" binding:"required"`
			Body      string `json:"body"    binding:"required"`
			Variables string `json:"variables"`
		}
		if err := c.ShouldBindJSON(&req); err != nil {
			c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
			return
		}
		if req.Variables == "" {
			req.Variables = "[]"
		}
		result, err := db.Exec(`
			INSERT INTO email_templates (user_id, name, subject, body, variables, created_at, updated_at)
			VALUES (?, ?, ?, ?, ?, datetime('now'), datetime('now'))
		`, userID, req.Name, req.Subject, req.Body, req.Variables)
		if err != nil {
			c.JSON(http.StatusInternalServerError, gin.H{"error": "failed to create template"})
			return
		}
		id, _ := result.LastInsertId()
		c.JSON(http.StatusCreated, gin.H{"message": "template created", "id": id})
	}
}

func GetEmailTemplate(db *sql.DB) gin.HandlerFunc {
	return func(c *gin.Context) {
		userID := utils.GetUserID(c)
		id := c.Param("id")
		var t models.EmailTemplate
		err := db.QueryRow(`
			SELECT id, user_id, name, subject, body, variables, created_at, updated_at
			FROM email_templates WHERE id = ? AND user_id = ?
		`, id, userID).Scan(&t.ID, &t.UserID, &t.Name, &t.Subject, &t.Body, &t.Variables, &t.CreatedAt, &t.UpdatedAt)
		if err == sql.ErrNoRows {
			c.JSON(http.StatusNotFound, gin.H{"error": "template not found"})
			return
		}
		if err != nil {
			c.JSON(http.StatusInternalServerError, gin.H{"error": "database error"})
			return
		}
		c.JSON(http.StatusOK, t)
	}
}

func UpdateEmailTemplate(db *sql.DB) gin.HandlerFunc {
	return func(c *gin.Context) {
		userID := utils.GetUserID(c)
		id := c.Param("id")
		var req struct {
			Name      string `json:"name"`
			Subject   string `json:"subject"`
			Body      string `json:"body"`
			Variables string `json:"variables"`
		}
		if err := c.ShouldBindJSON(&req); err != nil {
			c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
			return
		}
		_, err := db.Exec(`
			UPDATE email_templates SET
				name       = COALESCE(NULLIF(?, ''), name),
				subject    = COALESCE(NULLIF(?, ''), subject),
				body       = COALESCE(NULLIF(?, ''), body),
				variables  = COALESCE(NULLIF(?, ''), variables),
				updated_at = datetime('now')
			WHERE id = ? AND user_id = ?
		`, req.Name, req.Subject, req.Body, req.Variables, id, userID)
		if err != nil {
			c.JSON(http.StatusInternalServerError, gin.H{"error": "failed to update template"})
			return
		}
		c.JSON(http.StatusOK, gin.H{"message": "template updated"})
	}
}

func DeleteEmailTemplate(db *sql.DB) gin.HandlerFunc {
	return func(c *gin.Context) {
		userID := utils.GetUserID(c)
		id := c.Param("id")
		db.Exec("DELETE FROM email_templates WHERE id = ? AND user_id = ?", id, userID)
		c.JSON(http.StatusOK, gin.H{"message": "template deleted"})
	}
}

// PreviewEmailTemplate renders an email template body against supplied sample data.
// Templates use Go's text/template syntax and may call built-in helper functions.
func PreviewEmailTemplate(db *sql.DB) gin.HandlerFunc {
	return func(c *gin.Context) {
		userID := utils.GetUserID(c)
		id := c.Param("id")

		var tmpl models.EmailTemplate
		err := db.QueryRow(`
			SELECT id, user_id, name, subject, body FROM email_templates WHERE id = ? AND user_id = ?
		`, id, userID).Scan(&tmpl.ID, &tmpl.UserID, &tmpl.Name, &tmpl.Subject, &tmpl.Body)
		if err == sql.ErrNoRows {
			c.JSON(http.StatusNotFound, gin.H{"error": "template not found"})
			return
		}
		if err != nil {
			c.JSON(http.StatusInternalServerError, gin.H{"error": "database error"})
			return
		}

		// Caller may supply a JSON object with values for template variables.
		previewData := map[string]interface{}{
			"customer_name":  "Jane Smith",
			"customer_email": "jane@example.com",
			"deal_value":     "$24,000",
			"company":        "Acme Corp",
			"rep_name":       "Your Sales Rep",
			"date":           time.Now().Format("January 2, 2006"),
		}
		c.ShouldBindJSON(&previewData)

		// Render subject
		subjectFuncs := texttemplate.FuncMap{
			"upper": strings.ToUpper,
			"lower": strings.ToLower,
			"trim":  strings.TrimSpace,
		}
		subjectTmpl, err := texttemplate.New("subject").Funcs(subjectFuncs).Parse(tmpl.Subject)
		if err != nil {
			c.JSON(http.StatusBadRequest, gin.H{"error": fmt.Sprintf("subject parse error: %v", err)})
			return
		}
		var subjectBuf bytes.Buffer
		subjectTmpl.Execute(&subjectBuf, previewData)

		// Build the body function map.
		// Additional utility functions make it easy to produce rich dynamic content.
		bodyFuncs := texttemplate.FuncMap{
			"upper":    strings.ToUpper,
			"lower":    strings.ToLower,
			"trim":     strings.TrimSpace,
			"replace":  strings.ReplaceAll,
			"contains": strings.Contains,
			"split":    strings.Split,
			"join":     strings.Join,
		}

		bodyTmpl, err := texttemplate.New("body").Funcs(bodyFuncs).Parse(tmpl.Body)
		if err != nil {
			c.JSON(http.StatusBadRequest, gin.H{"error": fmt.Sprintf("body parse error: %v", err)})
			return
		}

		var bodyBuf bytes.Buffer
		if err := bodyTmpl.Execute(&bodyBuf, previewData); err != nil {
			c.JSON(http.StatusInternalServerError, gin.H{"error": fmt.Sprintf("render error: %v", err)})
			return
		}

		c.JSON(http.StatusOK, gin.H{
			"name":    tmpl.Name,
			"subject": subjectBuf.String(),
			"body":    bodyBuf.String(),
		})
	}
}
