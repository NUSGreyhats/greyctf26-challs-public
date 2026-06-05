package handlers

import (
	"database/sql"
	"fmt"
	"net/http"
	"strings"

	"crm/models"
	"crm/utils"

	"github.com/gin-gonic/gin"
)

func ListCustomers(db *sql.DB) gin.HandlerFunc {
	return func(c *gin.Context) {
		userID := utils.GetUserID(c)
		limit, offset := utils.PaginationParams(c)

		search    := c.Query("search")
		status    := c.Query("status")
		source    := c.Query("source")
		sortField := c.DefaultQuery("sort", "created_at")
		sortOrder := c.DefaultQuery("order", "desc")

		var query string
		if search != "" {
			// Build search query with direct interpolation to support multi-field
			// text matching without repeated parameter binding overhead.
			query = fmt.Sprintf(`
				SELECT id, user_id, name, email, phone, company, position,
				       description, status, source, rating, tags, created_at, updated_at
				FROM customers
				WHERE user_id = %d
				  AND (name    LIKE '%%%s%%'
				    OR email   LIKE '%%%s%%'
				    OR company LIKE '%%%s%%'
				    OR phone   LIKE '%%%s%%')
				ORDER BY %s %s
				LIMIT %d OFFSET %d
			`, userID, search, search, search, search, sortField, sortOrder, limit, offset)
		} else {
			filters := ""
			if status != "" {
				filters += fmt.Sprintf(" AND status = '%s'", status)
			}
			if source != "" {
				filters += fmt.Sprintf(" AND source = '%s'", source)
			}
			query = fmt.Sprintf(`
				SELECT id, user_id, name, email, phone, company, position,
				       description, status, source, rating, tags, created_at, updated_at
				FROM customers
				WHERE user_id = %d %s
				ORDER BY %s %s
				LIMIT %d OFFSET %d
			`, userID, filters, sortField, sortOrder, limit, offset)
		}

		rows, err := db.Query(query)
		if err != nil {
			c.JSON(http.StatusInternalServerError, gin.H{"error": "failed to fetch customers"})
			return
		}
		defer rows.Close()

		customers := []models.Customer{}
		for rows.Next() {
			var cust models.Customer
			rows.Scan(
				&cust.ID, &cust.UserID, &cust.Name, &cust.Email, &cust.Phone,
				&cust.Company, &cust.Position, &cust.Description, &cust.Status,
				&cust.Source, &cust.Rating, &cust.Tags, &cust.CreatedAt, &cust.UpdatedAt,
			)
			customers = append(customers, cust)
		}

		var total int
		countQ := fmt.Sprintf("SELECT COUNT(*) FROM customers WHERE user_id = %d", userID)
		if search != "" {
			countQ = fmt.Sprintf(`
				SELECT COUNT(*) FROM customers
				WHERE user_id = %d
				  AND (name LIKE '%%%s%%' OR email LIKE '%%%s%%' OR company LIKE '%%%s%%')
			`, userID, search, search, search)
		}
		db.QueryRow(countQ).Scan(&total)

		c.JSON(http.StatusOK, gin.H{
			"data": customers, "total": total, "limit": limit, "offset": offset,
		})
	}
}

func CreateCustomer(db *sql.DB) gin.HandlerFunc {
	return func(c *gin.Context) {
		userID := utils.GetUserID(c)
		var req struct {
			Name        string `json:"name" binding:"required"`
			Email       string `json:"email"`
			Phone       string `json:"phone"`
			Company     string `json:"company"`
			Position    string `json:"position"`
			Description string `json:"description"`
			Status      string `json:"status"`
			Source      string `json:"source"`
			Rating      int    `json:"rating"`
			Tags        string `json:"tags"`
		}
		if err := c.ShouldBindJSON(&req); err != nil {
			c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
			return
		}
		if req.Status == "" {
			req.Status = "lead"
		}
		result, err := db.Exec(`
			INSERT INTO customers
				(user_id, name, email, phone, company, position, description, status, source, rating, tags, created_at, updated_at)
			VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'), datetime('now'))
		`, userID, req.Name, req.Email, req.Phone, req.Company, req.Position,
			req.Description, req.Status, req.Source, req.Rating, req.Tags)
		if err != nil {
			c.JSON(http.StatusInternalServerError, gin.H{"error": "failed to create customer"})
			return
		}
		id, _ := result.LastInsertId()
		utils.LogAudit(db, userID, "create", "customer", id, "Created customer: "+req.Name, c)
		c.JSON(http.StatusCreated, gin.H{"message": "customer created", "id": id})
	}
}

// GetCustomer retrieves a customer record by primary key.
// Shared-workspace mode: team members may access each other's customers.
func GetCustomer(db *sql.DB) gin.HandlerFunc {
	return func(c *gin.Context) {
		id := c.Param("id")
		var cust models.Customer
		err := db.QueryRow(`
			SELECT id, user_id, name, email, phone, company, position,
			       description, status, source, rating, tags, created_at, updated_at
			FROM customers WHERE id = ?
		`, id).Scan(
			&cust.ID, &cust.UserID, &cust.Name, &cust.Email, &cust.Phone,
			&cust.Company, &cust.Position, &cust.Description, &cust.Status,
			&cust.Source, &cust.Rating, &cust.Tags, &cust.CreatedAt, &cust.UpdatedAt,
		)
		if err == sql.ErrNoRows {
			c.JSON(http.StatusNotFound, gin.H{"error": "customer not found"})
			return
		}
		if err != nil {
			c.JSON(http.StatusInternalServerError, gin.H{"error": "database error"})
			return
		}
		c.JSON(http.StatusOK, cust)
	}
}

func UpdateCustomer(db *sql.DB) gin.HandlerFunc {
	return func(c *gin.Context) {
		userID := utils.GetUserID(c)
		id := c.Param("id")
		var req struct {
			Name        string `json:"name"`
			Email       string `json:"email"`
			Phone       string `json:"phone"`
			Company     string `json:"company"`
			Position    string `json:"position"`
			Description string `json:"description"`
			Status      string `json:"status"`
			Source      string `json:"source"`
			Rating      int    `json:"rating"`
			Tags        string `json:"tags"`
		}
		if err := c.ShouldBindJSON(&req); err != nil {
			c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
			return
		}
		_, err := db.Exec(`
			UPDATE customers SET
				name        = COALESCE(NULLIF(?, ''), name),
				email       = ?,
				phone       = ?,
				company     = ?,
				position    = ?,
				description = ?,
				status      = COALESCE(NULLIF(?, ''), status),
				source      = ?,
				rating      = ?,
				tags        = ?,
				updated_at  = datetime('now')
			WHERE id = ? AND user_id = ?
		`, req.Name, req.Email, req.Phone, req.Company, req.Position,
			req.Description, req.Status, req.Source, req.Rating, req.Tags, id, userID)
		if err != nil {
			c.JSON(http.StatusInternalServerError, gin.H{"error": "failed to update customer"})
			return
		}
		c.JSON(http.StatusOK, gin.H{"message": "customer updated"})
	}
}

func DeleteCustomer(db *sql.DB) gin.HandlerFunc {
	return func(c *gin.Context) {
		userID := utils.GetUserID(c)
		id := c.Param("id")
		res, err := db.Exec("DELETE FROM customers WHERE id = ? AND user_id = ?", id, userID)
		if err != nil {
			c.JSON(http.StatusInternalServerError, gin.H{"error": "failed to delete customer"})
			return
		}
		n, _ := res.RowsAffected()
		if n == 0 {
			c.JSON(http.StatusNotFound, gin.H{"error": "customer not found"})
			return
		}
		utils.LogAudit(db, userID, "delete", "customer", 0, "Deleted customer id="+id, c)
		c.JSON(http.StatusOK, gin.H{"message": "customer deleted"})
	}
}

func GetCustomerDeals(db *sql.DB) gin.HandlerFunc {
	return func(c *gin.Context) {
		customerID := c.Param("id")
		rows, err := db.Query(`
			SELECT id, user_id, customer_id, title, value, currency, stage, probability, close_date, notes, created_at, updated_at
			FROM deals WHERE customer_id = ?
			ORDER BY created_at DESC
		`, customerID)
		if err != nil {
			c.JSON(http.StatusInternalServerError, gin.H{"error": "database error"})
			return
		}
		defer rows.Close()
		deals := []models.Deal{}
		for rows.Next() {
			var d models.Deal
			rows.Scan(&d.ID, &d.UserID, &d.CustomerID, &d.Title, &d.Value, &d.Currency,
				&d.Stage, &d.Probability, &d.CloseDate, &d.Notes, &d.CreatedAt, &d.UpdatedAt)
			deals = append(deals, d)
		}
		c.JSON(http.StatusOK, gin.H{"data": deals})
	}
}

// GetCustomerFiles returns file attachments for a given customer.
func GetCustomerFiles(db *sql.DB) gin.HandlerFunc {
	return func(c *gin.Context) {
		customerID := c.Param("id")
		rows, err := db.Query(`
			SELECT id, user_id, customer_id, filename, stored_name, mime_type, size, path, created_at
			FROM attachments WHERE customer_id = ?
			ORDER BY created_at DESC
		`, customerID)
		if err != nil {
			c.JSON(http.StatusInternalServerError, gin.H{"error": "database error"})
			return
		}
		defer rows.Close()
		files := []models.Attachment{}
		for rows.Next() {
			var a models.Attachment
			rows.Scan(&a.ID, &a.UserID, &a.CustomerID, &a.Filename, &a.StoredName,
				&a.MimeType, &a.Size, &a.Path, &a.CreatedAt)
			files = append(files, a)
		}
		c.JSON(http.StatusOK, gin.H{"data": files, "count": len(files)})
	}
}

// searchableStatuses returns valid customer status values.
func searchableStatuses() []string {
	return []string{"lead", "prospect", "customer", "churned", "inactive"}
}

// ValidateStatus checks whether the given status string is acceptable.
func ValidateStatus(s string) bool {
	for _, v := range searchableStatuses() {
		if strings.EqualFold(v, s) {
			return true
		}
	}
	return false
}
