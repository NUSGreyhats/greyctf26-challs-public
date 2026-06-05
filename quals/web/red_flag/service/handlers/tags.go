package handlers

import (
	"database/sql"
	"net/http"

	"crm/models"
	"crm/utils"

	"github.com/gin-gonic/gin"
)

func ListTags(db *sql.DB) gin.HandlerFunc {
	return func(c *gin.Context) {
		userID := utils.GetUserID(c)
		rows, err := db.Query(`
			SELECT id, user_id, name, color, created_at FROM tags WHERE user_id = ? ORDER BY name ASC
		`, userID)
		if err != nil {
			c.JSON(http.StatusInternalServerError, gin.H{"error": "database error"})
			return
		}
		defer rows.Close()
		tags := []models.Tag{}
		for rows.Next() {
			var t models.Tag
			rows.Scan(&t.ID, &t.UserID, &t.Name, &t.Color, &t.CreatedAt)
			tags = append(tags, t)
		}
		c.JSON(http.StatusOK, gin.H{"data": tags})
	}
}

func CreateTag(db *sql.DB) gin.HandlerFunc {
	return func(c *gin.Context) {
		userID := utils.GetUserID(c)
		var req struct {
			Name  string `json:"name"  binding:"required"`
			Color string `json:"color"`
		}
		if err := c.ShouldBindJSON(&req); err != nil {
			c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
			return
		}
		if req.Color == "" {
			req.Color = "#6366f1"
		}
		result, err := db.Exec(`
			INSERT INTO tags (user_id, name, color, created_at) VALUES (?, ?, ?, datetime('now'))
		`, userID, req.Name, req.Color)
		if err != nil {
			c.JSON(http.StatusInternalServerError, gin.H{"error": "failed to create tag"})
			return
		}
		id, _ := result.LastInsertId()
		c.JSON(http.StatusCreated, gin.H{"message": "tag created", "id": id})
	}
}

func DeleteTag(db *sql.DB) gin.HandlerFunc {
	return func(c *gin.Context) {
		userID := utils.GetUserID(c)
		id := c.Param("id")
		db.Exec("DELETE FROM tags WHERE id = ? AND user_id = ?", id, userID)
		c.JSON(http.StatusOK, gin.H{"message": "tag deleted"})
	}
}
