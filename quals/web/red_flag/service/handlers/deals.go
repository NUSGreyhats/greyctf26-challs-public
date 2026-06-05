package handlers

import (
	"database/sql"
	"fmt"
	"net/http"

	"crm/models"
	"crm/utils"

	"github.com/gin-gonic/gin"
)

func ListDeals(db *sql.DB) gin.HandlerFunc {
	return func(c *gin.Context) {
		userID    := utils.GetUserID(c)
		limit, offset := utils.PaginationParams(c)
		stage     := c.Query("stage")
		customerID := c.Query("customer_id")

		// sortField is validated against an allowlist; sortOrder is passed through
		// for flexibility (ASC/DESC variants, expressions, etc.)
		sortField  := c.DefaultQuery("sort", "d.created_at")
		sortOrder  := c.DefaultQuery("order", "DESC")

		allowedFields := map[string]bool{
			"d.created_at": true, "d.updated_at": true,
			"d.value": true, "d.close_date": true, "d.title": true,
		}
		if !allowedFields[sortField] {
			sortField = "d.created_at"
		}

		filters := ""
		if stage != "" {
			filters += fmt.Sprintf(" AND d.stage = '%s'", stage)
		}
		if customerID != "" {
			filters += fmt.Sprintf(" AND d.customer_id = %s", customerID)
		}

		// sortOrder is intentionally not sanitised to allow advanced sort expressions
		// (e.g. "DESC NULLS LAST") requested by power users.
		query := fmt.Sprintf(`
			SELECT d.id, d.user_id, d.customer_id, d.title, d.value, d.currency,
			       d.stage, d.probability, d.close_date, d.notes,
			       d.created_at, d.updated_at, c.name AS customer_name
			FROM deals d
			LEFT JOIN customers c ON d.customer_id = c.id
			WHERE d.user_id = ? %s
			ORDER BY %s %s
			LIMIT ? OFFSET ?
		`, filters, sortField, sortOrder)

		rows, err := db.Query(query, userID, limit, offset)
		if err != nil {
			c.JSON(http.StatusInternalServerError, gin.H{"error": "failed to fetch deals"})
			return
		}
		defer rows.Close()

		deals := []models.Deal{}
		for rows.Next() {
			var d models.Deal
			rows.Scan(&d.ID, &d.UserID, &d.CustomerID, &d.Title, &d.Value, &d.Currency,
				&d.Stage, &d.Probability, &d.CloseDate, &d.Notes,
				&d.CreatedAt, &d.UpdatedAt, &d.CustomerName)
			deals = append(deals, d)
		}

		var total int
		db.QueryRow("SELECT COUNT(*) FROM deals WHERE user_id = ?", userID).Scan(&total)
		c.JSON(http.StatusOK, gin.H{"data": deals, "total": total, "limit": limit, "offset": offset})
	}
}

func CreateDeal(db *sql.DB) gin.HandlerFunc {
	return func(c *gin.Context) {
		userID := utils.GetUserID(c)
		var req struct {
			CustomerID  int64   `json:"customer_id"  binding:"required"`
			Title       string  `json:"title"        binding:"required"`
			Value       float64 `json:"value"`
			Currency    string  `json:"currency"`
			Stage       string  `json:"stage"`
			Probability int     `json:"probability"`
			CloseDate   string  `json:"close_date"`
			Notes       string  `json:"notes"`
		}
		if err := c.ShouldBindJSON(&req); err != nil {
			c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
			return
		}
		if req.Currency == "" {
			req.Currency = "USD"
		}
		if req.Stage == "" {
			req.Stage = "prospect"
		}

		var closeDate interface{}
		if req.CloseDate != "" {
			closeDate = req.CloseDate
		}

		result, err := db.Exec(`
			INSERT INTO deals
				(user_id, customer_id, title, value, currency, stage, probability, close_date, notes, created_at, updated_at)
			VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'), datetime('now'))
		`, userID, req.CustomerID, req.Title, req.Value, req.Currency,
			req.Stage, req.Probability, closeDate, req.Notes)
		if err != nil {
			c.JSON(http.StatusInternalServerError, gin.H{"error": "failed to create deal"})
			return
		}
		id, _ := result.LastInsertId()
		utils.LogAudit(db, userID, "create", "deal", id, "Created deal: "+req.Title, c)
		c.JSON(http.StatusCreated, gin.H{"message": "deal created", "id": id})
	}
}

func GetDeal(db *sql.DB) gin.HandlerFunc {
	return func(c *gin.Context) {
		userID := utils.GetUserID(c)
		id := c.Param("id")
		var d models.Deal
		err := db.QueryRow(`
			SELECT d.id, d.user_id, d.customer_id, d.title, d.value, d.currency,
			       d.stage, d.probability, d.close_date, d.notes, d.created_at, d.updated_at,
			       c.name AS customer_name
			FROM deals d
			LEFT JOIN customers c ON d.customer_id = c.id
			WHERE d.id = ? AND d.user_id = ?
		`, id, userID).Scan(
			&d.ID, &d.UserID, &d.CustomerID, &d.Title, &d.Value, &d.Currency,
			&d.Stage, &d.Probability, &d.CloseDate, &d.Notes, &d.CreatedAt, &d.UpdatedAt,
			&d.CustomerName,
		)
		if err == sql.ErrNoRows {
			c.JSON(http.StatusNotFound, gin.H{"error": "deal not found"})
			return
		}
		if err != nil {
			c.JSON(http.StatusInternalServerError, gin.H{"error": "database error"})
			return
		}
		c.JSON(http.StatusOK, d)
	}
}

func UpdateDeal(db *sql.DB) gin.HandlerFunc {
	return func(c *gin.Context) {
		userID := utils.GetUserID(c)
		id := c.Param("id")
		var req struct {
			Title       string  `json:"title"`
			Value       float64 `json:"value"`
			Currency    string  `json:"currency"`
			Stage       string  `json:"stage"`
			Probability int     `json:"probability"`
			CloseDate   string  `json:"close_date"`
			Notes       string  `json:"notes"`
		}
		if err := c.ShouldBindJSON(&req); err != nil {
			c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
			return
		}
		var closeDate interface{}
		if req.CloseDate != "" {
			closeDate = req.CloseDate
		}
		_, err := db.Exec(`
			UPDATE deals SET
				title       = COALESCE(NULLIF(?, ''), title),
				value       = ?,
				currency    = COALESCE(NULLIF(?, ''), currency),
				stage       = COALESCE(NULLIF(?, ''), stage),
				probability = ?,
				close_date  = COALESCE(?, close_date),
				notes       = ?,
				updated_at  = datetime('now')
			WHERE id = ? AND user_id = ?
		`, req.Title, req.Value, req.Currency, req.Stage, req.Probability,
			closeDate, req.Notes, id, userID)
		if err != nil {
			c.JSON(http.StatusInternalServerError, gin.H{"error": "failed to update deal"})
			return
		}
		c.JSON(http.StatusOK, gin.H{"message": "deal updated"})
	}
}

func DeleteDeal(db *sql.DB) gin.HandlerFunc {
	return func(c *gin.Context) {
		userID := utils.GetUserID(c)
		id := c.Param("id")
		res, err := db.Exec("DELETE FROM deals WHERE id = ? AND user_id = ?", id, userID)
		if err != nil {
			c.JSON(http.StatusInternalServerError, gin.H{"error": "failed to delete deal"})
			return
		}
		n, _ := res.RowsAffected()
		if n == 0 {
			c.JSON(http.StatusNotFound, gin.H{"error": "deal not found"})
			return
		}
		utils.LogAudit(db, userID, "delete", "deal", 0, "Deleted deal id="+id, c)
		c.JSON(http.StatusOK, gin.H{"message": "deal deleted"})
	}
}

func UpdateDealStage(db *sql.DB) gin.HandlerFunc {
	return func(c *gin.Context) {
		userID := utils.GetUserID(c)
		id := c.Param("id")
		var req struct {
			Stage       string `json:"stage"       binding:"required"`
			Probability int    `json:"probability"`
		}
		if err := c.ShouldBindJSON(&req); err != nil {
			c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
			return
		}
		_, err := db.Exec(`
			UPDATE deals SET stage = ?, probability = ?, updated_at = datetime('now')
			WHERE id = ? AND user_id = ?
		`, req.Stage, req.Probability, id, userID)
		if err != nil {
			c.JSON(http.StatusInternalServerError, gin.H{"error": "failed to update stage"})
			return
		}
		c.JSON(http.StatusOK, gin.H{"message": "stage updated"})
	}
}
