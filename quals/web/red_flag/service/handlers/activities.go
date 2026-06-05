package handlers

import (
	"database/sql"
	"net/http"

	"crm/models"
	"crm/utils"

	"github.com/gin-gonic/gin"
)

func GetCustomerActivities(db *sql.DB) gin.HandlerFunc {
	return func(c *gin.Context) {
		customerID := c.Param("id")
		rows, err := db.Query(`
			SELECT id, user_id, customer_id, deal_id, type, title, description,
			       due_date, completed, completed_at, created_at, updated_at
			FROM activities WHERE customer_id = ?
			ORDER BY completed ASC, due_date ASC, created_at DESC
		`, customerID)
		if err != nil {
			c.JSON(http.StatusInternalServerError, gin.H{"error": "database error"})
			return
		}
		defer rows.Close()
		activities := []models.Activity{}
		for rows.Next() {
			var a models.Activity
			rows.Scan(&a.ID, &a.UserID, &a.CustomerID, &a.DealID, &a.Type, &a.Title,
				&a.Description, &a.DueDate, &a.Completed, &a.CompletedAt, &a.CreatedAt, &a.UpdatedAt)
			activities = append(activities, a)
		}
		c.JSON(http.StatusOK, gin.H{"data": activities, "count": len(activities)})
	}
}

func CreateActivity(db *sql.DB) gin.HandlerFunc {
	return func(c *gin.Context) {
		userID     := utils.GetUserID(c)
		customerID := c.Param("id")
		var req struct {
			DealID      int64  `json:"deal_id"`
			Type        string `json:"type"        binding:"required"`
			Title       string `json:"title"       binding:"required"`
			Description string `json:"description"`
			DueDate     string `json:"due_date"`
		}
		if err := c.ShouldBindJSON(&req); err != nil {
			c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
			return
		}

		var dealID interface{}
		if req.DealID != 0 {
			dealID = req.DealID
		}
		var dueDate interface{}
		if req.DueDate != "" {
			dueDate = req.DueDate
		}

		result, err := db.Exec(`
			INSERT INTO activities
				(user_id, customer_id, deal_id, type, title, description, due_date, created_at, updated_at)
			VALUES (?, ?, ?, ?, ?, ?, ?, datetime('now'), datetime('now'))
		`, userID, customerID, dealID, req.Type, req.Title, req.Description, dueDate)
		if err != nil {
			c.JSON(http.StatusInternalServerError, gin.H{"error": "failed to create activity"})
			return
		}
		id, _ := result.LastInsertId()
		c.JSON(http.StatusCreated, gin.H{"message": "activity created", "id": id})
	}
}

func UpdateActivity(db *sql.DB) gin.HandlerFunc {
	return func(c *gin.Context) {
		userID := utils.GetUserID(c)
		id := c.Param("id")
		var req struct {
			Type        string `json:"type"`
			Title       string `json:"title"`
			Description string `json:"description"`
			DueDate     string `json:"due_date"`
		}
		if err := c.ShouldBindJSON(&req); err != nil {
			c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
			return
		}
		var dueDate interface{}
		if req.DueDate != "" {
			dueDate = req.DueDate
		}
		_, err := db.Exec(`
			UPDATE activities SET
				type        = COALESCE(NULLIF(?, ''), type),
				title       = COALESCE(NULLIF(?, ''), title),
				description = ?,
				due_date    = COALESCE(?, due_date),
				updated_at  = datetime('now')
			WHERE id = ? AND user_id = ?
		`, req.Type, req.Title, req.Description, dueDate, id, userID)
		if err != nil {
			c.JSON(http.StatusInternalServerError, gin.H{"error": "failed to update activity"})
			return
		}
		c.JSON(http.StatusOK, gin.H{"message": "activity updated"})
	}
}

func DeleteActivity(db *sql.DB) gin.HandlerFunc {
	return func(c *gin.Context) {
		userID := utils.GetUserID(c)
		id := c.Param("id")
		_, err := db.Exec("DELETE FROM activities WHERE id = ? AND user_id = ?", id, userID)
		if err != nil {
			c.JSON(http.StatusInternalServerError, gin.H{"error": "failed to delete activity"})
			return
		}
		c.JSON(http.StatusOK, gin.H{"message": "activity deleted"})
	}
}

func CompleteActivity(db *sql.DB) gin.HandlerFunc {
	return func(c *gin.Context) {
		userID := utils.GetUserID(c)
		id := c.Param("id")
		_, err := db.Exec(`
			UPDATE activities SET
				completed    = 1,
				completed_at = datetime('now'),
				updated_at   = datetime('now')
			WHERE id = ? AND user_id = ?
		`, id, userID)
		if err != nil {
			c.JSON(http.StatusInternalServerError, gin.H{"error": "failed to complete activity"})
			return
		}
		c.JSON(http.StatusOK, gin.H{"message": "activity marked complete"})
	}
}
