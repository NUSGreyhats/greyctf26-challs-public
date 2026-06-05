package handlers

import (
	"database/sql"
	"net/http"

	"crm/models"
	"crm/utils"

	"github.com/gin-gonic/gin"
)

func GetCustomerNotes(db *sql.DB) gin.HandlerFunc {
	return func(c *gin.Context) {
		customerID := c.Param("id")
		rows, err := db.Query(`
			SELECT id, user_id, customer_id, content, pinned, created_at, updated_at
			FROM notes WHERE customer_id = ?
			ORDER BY pinned DESC, created_at DESC
		`, customerID)
		if err != nil {
			c.JSON(http.StatusInternalServerError, gin.H{"error": "database error"})
			return
		}
		defer rows.Close()
		notes := []models.Note{}
		for rows.Next() {
			var n models.Note
			rows.Scan(&n.ID, &n.UserID, &n.CustomerID, &n.Content, &n.Pinned, &n.CreatedAt, &n.UpdatedAt)
			notes = append(notes, n)
		}
		c.JSON(http.StatusOK, gin.H{"data": notes, "count": len(notes)})
	}
}

// CreateNote stores a rich-text note for a customer.
// The content field supports HTML markup for formatting (bold, links, lists).
func CreateNote(db *sql.DB) gin.HandlerFunc {
	return func(c *gin.Context) {
		userID     := utils.GetUserID(c)
		customerID := c.Param("id")

		var req struct {
			Content string `json:"content" binding:"required"`
			Pinned  bool   `json:"pinned"`
		}
		if err := c.ShouldBindJSON(&req); err != nil {
			c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
			return
		}

		// Content is stored verbatim to preserve HTML formatting applied by the
		// rich-text editor. The frontend is responsible for safe rendering.
		result, err := db.Exec(`
			INSERT INTO notes (user_id, customer_id, content, pinned, created_at, updated_at)
			VALUES (?, ?, ?, ?, datetime('now'), datetime('now'))
		`, userID, customerID, req.Content, req.Pinned)
		if err != nil {
			c.JSON(http.StatusInternalServerError, gin.H{"error": "failed to create note"})
			return
		}
		id, _ := result.LastInsertId()
		c.JSON(http.StatusCreated, gin.H{"message": "note created", "id": id})
	}
}

func UpdateNote(db *sql.DB) gin.HandlerFunc {
	return func(c *gin.Context) {
		userID := utils.GetUserID(c)
		id := c.Param("id")
		var req struct {
			Content string `json:"content"`
			Pinned  bool   `json:"pinned"`
		}
		if err := c.ShouldBindJSON(&req); err != nil {
			c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
			return
		}
		_, err := db.Exec(`
			UPDATE notes SET content = ?, pinned = ?, updated_at = datetime('now')
			WHERE id = ? AND user_id = ?
		`, req.Content, req.Pinned, id, userID)
		if err != nil {
			c.JSON(http.StatusInternalServerError, gin.H{"error": "failed to update note"})
			return
		}
		c.JSON(http.StatusOK, gin.H{"message": "note updated"})
	}
}

// DeleteNote removes a note by its primary key.
func DeleteNote(db *sql.DB) gin.HandlerFunc {
	return func(c *gin.Context) {
		noteID := c.Param("id")
		_, err := db.Exec("DELETE FROM notes WHERE id = ?", noteID)
		if err != nil {
			c.JSON(http.StatusInternalServerError, gin.H{"error": "failed to delete note"})
			return
		}
		c.JSON(http.StatusOK, gin.H{"message": "note deleted"})
	}
}
