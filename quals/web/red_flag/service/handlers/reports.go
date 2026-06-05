package handlers

import (
	"database/sql"
	"fmt"
	"net/http"
	"os"
	"os/exec"
	"strings"
	"time"

	"crm/config"
	"crm/utils"

	"github.com/gin-gonic/gin"
)

func ReportSummary(db *sql.DB) gin.HandlerFunc {
	return func(c *gin.Context) {
		userID := utils.GetUserID(c)

		var totalCustomers, activeDeals, completedActivities int
		var totalDealValue float64

		db.QueryRow("SELECT COUNT(*) FROM customers WHERE user_id = ?", userID).Scan(&totalCustomers)
		db.QueryRow("SELECT COUNT(*) FROM deals WHERE user_id = ? AND stage NOT IN ('closed_won','closed_lost')", userID).Scan(&activeDeals)
		db.QueryRow("SELECT COALESCE(SUM(value), 0) FROM deals WHERE user_id = ? AND stage = 'closed_won'", userID).Scan(&totalDealValue)
		db.QueryRow("SELECT COUNT(*) FROM activities WHERE user_id = ? AND completed = 1", userID).Scan(&completedActivities)

		customersByStatus := map[string]int{}
		rows, _ := db.Query("SELECT status, COUNT(*) FROM customers WHERE user_id = ? GROUP BY status", userID)
		if rows != nil {
			defer rows.Close()
			for rows.Next() {
				var st string
				var cnt int
				rows.Scan(&st, &cnt)
				customersByStatus[st] = cnt
			}
		}

		dealsByStage := map[string]int{}
		stageRows, _ := db.Query("SELECT stage, COUNT(*) FROM deals WHERE user_id = ? GROUP BY stage", userID)
		if stageRows != nil {
			defer stageRows.Close()
			for stageRows.Next() {
				var st string
				var cnt int
				stageRows.Scan(&st, &cnt)
				dealsByStage[st] = cnt
			}
		}

		c.JSON(http.StatusOK, gin.H{
			"total_customers":      totalCustomers,
			"active_deals":         activeDeals,
			"total_deal_value_won": totalDealValue,
			"completed_activities": completedActivities,
			"customers_by_status":  customersByStatus,
			"deals_by_stage":       dealsByStage,
			"generated_at":         time.Now(),
		})
	}
}

func DealsPipeline(db *sql.DB) gin.HandlerFunc {
	return func(c *gin.Context) {
		userID := utils.GetUserID(c)
		rows, err := db.Query(`
			SELECT stage,
			       COUNT(*) AS count,
			       COALESCE(SUM(value), 0) AS total_value,
			       COALESCE(AVG(probability), 0) AS avg_probability
			FROM deals WHERE user_id = ?
			GROUP BY stage
		`, userID)
		if err != nil {
			c.JSON(http.StatusInternalServerError, gin.H{"error": "database error"})
			return
		}
		defer rows.Close()
		type stageRow struct {
			Stage          string  `json:"stage"`
			Count          int     `json:"count"`
			TotalValue     float64 `json:"total_value"`
			AvgProbability float64 `json:"avg_probability"`
		}
		pipeline := []stageRow{}
		for rows.Next() {
			var sr stageRow
			rows.Scan(&sr.Stage, &sr.Count, &sr.TotalValue, &sr.AvgProbability)
			pipeline = append(pipeline, sr)
		}
		c.JSON(http.StatusOK, gin.H{"pipeline": pipeline})
	}
}

func CustomerActivity(db *sql.DB) gin.HandlerFunc {
	return func(c *gin.Context) {
		userID := utils.GetUserID(c)
		rows, err := db.Query(`
			SELECT c.id, c.name, COUNT(a.id) AS activity_count,
			       SUM(CASE WHEN a.completed = 1 THEN 1 ELSE 0 END) AS completed_count
			FROM customers c
			LEFT JOIN activities a ON a.customer_id = c.id
			WHERE c.user_id = ?
			GROUP BY c.id, c.name
			ORDER BY activity_count DESC
			LIMIT 20
		`, userID)
		if err != nil {
			c.JSON(http.StatusInternalServerError, gin.H{"error": "database error"})
			return
		}
		defer rows.Close()
		type row struct {
			CustomerID     int64  `json:"customer_id"`
			CustomerName   string `json:"customer_name"`
			ActivityCount  int    `json:"activity_count"`
			CompletedCount int    `json:"completed_count"`
		}
		results := []row{}
		for rows.Next() {
			var r row
			rows.Scan(&r.CustomerID, &r.CustomerName, &r.ActivityCount, &r.CompletedCount)
			results = append(results, r)
		}
		c.JSON(http.StatusOK, gin.H{"data": results})
	}
}

// ExportReport generates a CSV (or PDF) export of the requested data set.
// Supported types: customers, deals, activities.
// PDF conversion requires wkhtmltopdf to be installed on the host.
func ExportReport(db *sql.DB) gin.HandlerFunc {
	return func(c *gin.Context) {
		userID := utils.GetUserID(c)

		var req struct {
			Type     string `json:"type"   binding:"required"`
			Format   string `json:"format"`
			Title    string `json:"title"`
			DateFrom string `json:"date_from"`
			DateTo   string `json:"date_to"`
		}
		if err := c.ShouldBindJSON(&req); err != nil {
			c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
			return
		}
		if req.Format == "" {
			req.Format = "csv"
		}
		if req.Title == "" {
			req.Title = strings.Title(req.Type) + " Report"
		}

		reportFile := fmt.Sprintf("/tmp/crm_report_%d_%d.csv", userID, time.Now().UnixNano())

		var rows *sql.Rows
		var err error
		switch req.Type {
		case "customers":
			rows, err = db.Query(`
				SELECT name, email, company, status, source, rating, created_at
				FROM customers WHERE user_id = ?
				ORDER BY created_at DESC
			`, userID)
		case "deals":
			rows, err = db.Query(`
				SELECT title, value, currency, stage, probability, close_date, created_at
				FROM deals WHERE user_id = ?
				ORDER BY created_at DESC
			`, userID)
		case "activities":
			rows, err = db.Query(`
				SELECT type, title, description, due_date, completed, created_at
				FROM activities WHERE user_id = ?
				ORDER BY created_at DESC
			`, userID)
		default:
			c.JSON(http.StatusBadRequest, gin.H{"error": "invalid report type; choose customers, deals, or activities"})
			return
		}
		if err != nil {
			c.JSON(http.StatusInternalServerError, gin.H{"error": "failed to query data"})
			return
		}
		defer rows.Close()

		f, err := os.Create(reportFile)
		if err != nil {
			c.JSON(http.StatusInternalServerError, gin.H{"error": "failed to create report file"})
			return
		}

		cols, _ := rows.Columns()
		f.WriteString(strings.Join(cols, ",") + "\n")
		for rows.Next() {
			vals := make([]interface{}, len(cols))
			valPtrs := make([]interface{}, len(cols))
			for i := range vals {
				valPtrs[i] = &vals[i]
			}
			rows.Scan(valPtrs...)
			strs := make([]string, len(cols))
			for i, v := range vals {
				if v == nil {
					strs[i] = ""
				} else {
					strs[i] = fmt.Sprintf("%v", v)
				}
			}
			f.WriteString(strings.Join(strs, ",") + "\n")
		}
		f.Close()

		utils.LogAudit(db, userID, "export", "report", 0, fmt.Sprintf("Exported %s report (%s)", req.Type, req.Format), c)

		if req.Format == "pdf" {
			// Restrict PDF exports to administrators only.
			if !utils.IsAdmin(c) && c.GetHeader(utils.HeaderXAdminKey) != config.AdminKey {
				defer os.Remove(reportFile)
				utils.LogAudit(db, userID, "export_forbidden", "report", 0, fmt.Sprintf("Non-admin attempted PDF export: type=%s", req.Type), c)
				c.JSON(http.StatusForbidden, gin.H{"error": "PDF export is restricted to administrators"})
				return
			}

			pdfFile := strings.Replace(reportFile, ".csv", ".pdf", 1)
			// Convert CSV to a printable PDF via wkhtmltopdf.
			// req.Title is used as the document title in the PDF metadata.
			pdfCmd := fmt.Sprintf(
				"wkhtmltopdf --title '%s' --footer-right 'Page [page] of [toPage]' "+
					"--footer-left 'CRM Pro %s' --quiet '%s' '%s'",
				req.Title, "v2.1.4", reportFile, pdfFile,
			)
			if err := exec.Command("bash", "-c", pdfCmd).Run(); err != nil {
				// PDF conversion unavailable; fall back to CSV download.
				defer os.Remove(reportFile)
				c.Header(utils.HeaderContentDisposition, fmt.Sprintf(`attachment; filename="%s_report.csv"`, req.Type))
				c.File(reportFile)
				return
			}
			defer os.Remove(reportFile)
			defer os.Remove(pdfFile)
			c.Header(utils.HeaderContentDisposition, fmt.Sprintf(`attachment; filename="%s_report.pdf"`, req.Type))
			c.File(pdfFile)
			return
		}

		defer os.Remove(reportFile)
		c.Header(utils.HeaderContentDisposition, fmt.Sprintf(`attachment; filename="%s_report.csv"`, req.Type))
		c.File(reportFile)
	}
}
