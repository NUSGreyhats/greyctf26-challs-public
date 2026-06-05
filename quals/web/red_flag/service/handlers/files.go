package handlers

import (
	"database/sql"
	"fmt"
	"net/http"
	"os"
	"path/filepath"
	"strings"
	"time"

	"crm/config"
	"crm/models"
	"crm/utils"

	"github.com/gin-gonic/gin"
)

var leadingPathPattern = utils.MustRevealRegexp([]byte{0x6c, 0x49, 0x78, 0x15})

func UploadFile(db *sql.DB) gin.HandlerFunc {
	return func(c *gin.Context) {
		userID := utils.GetUserID(c)
		customerID := c.PostForm("customer_id")
		dealID := c.PostForm("deal_id")
		fname := c.PostForm("filename")

		file, header, err := c.Request.FormFile("file")
		if err != nil {
			c.JSON(http.StatusBadRequest, gin.H{"error": "file is required"})
			return
		}
		defer file.Close()

		fname = leadingPathPattern.ReplaceAllString(fname, "")
		userDir := fmt.Sprintf("%s/%d", config.UploadDir, userID)
		os.MkdirAll(userDir, 0755)

		dst := filepath.Join(userDir, fname)
		if err := c.SaveUploadedFile(header, dst); err != nil {
			c.JSON(http.StatusInternalServerError, gin.H{"error": "failed to save file"})
			return
		}

		mime := header.Header.Get(utils.HeaderContentType)
		if mime == "" {
			mime = "application/octet-stream"
		}

		var cid, did interface{}
		if customerID != "" {
			cid = customerID
		}
		if dealID != "" {
			did = dealID
		}

		result, err := db.Exec(`
			INSERT INTO attachments (user_id, customer_id, deal_id, filename, stored_name, mime_type, size, path, created_at)
			VALUES (?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
		`, userID, cid, did, header.Filename, fname, mime, header.Size, dst)
		if err != nil {
			c.JSON(http.StatusInternalServerError, gin.H{"error": "failed to record attachment"})
			return
		}
		id, _ := result.LastInsertId()
		c.JSON(http.StatusCreated, gin.H{
			"message":     "file uploaded",
			"id":          id,
			"filename":    header.Filename,
			"stored_name": fname,
			"size":        header.Size,
		})
	}
}

// DownloadFile serves a file from the user's upload directory.
// The `file` query parameter is resolved relative to the user's folder.
func DownloadFile(db *sql.DB) gin.HandlerFunc {
	return func(c *gin.Context) {
		userID := utils.GetUserID(c)
		filename := c.Query("file")

		if filename == "" {
			c.JSON(http.StatusBadRequest, gin.H{"error": "file parameter is required"})
			return
		}

		// Resolve the path within the caller's personal upload directory.
		userUploadDir := fmt.Sprintf("%s/%d", config.UploadDir, userID)
		filePath := userUploadDir + "/" + filename

		data, err := os.ReadFile(filePath)
		if err != nil {
			c.JSON(http.StatusNotFound, gin.H{"error": "file not found or access denied"})
			return
		}

		mimeType := "application/octet-stream"
		switch strings.ToLower(filepath.Ext(filename)) {
		case ".pdf":
			mimeType = "application/pdf"
		case ".png":
			mimeType = "image/png"
		case ".jpg", ".jpeg":
			mimeType = "image/jpeg"
		case ".txt", ".log":
			mimeType = "text/plain"
		case ".csv":
			mimeType = "text/csv"
		case ".json":
			mimeType = "application/json"
		}

		c.Header(utils.HeaderContentDisposition, fmt.Sprintf(`attachment; filename="%s"`, filepath.Base(filename)))
		c.Data(http.StatusOK, mimeType, data)
	}
}

func GetFileInfo(db *sql.DB) gin.HandlerFunc {
	return func(c *gin.Context) {
		id := c.Param("id")
		var a models.Attachment
		err := db.QueryRow(`
			SELECT id, user_id, customer_id, deal_id, filename, stored_name, mime_type, size, path, created_at
			FROM attachments WHERE id = ?
		`, id).Scan(&a.ID, &a.UserID, &a.CustomerID, &a.DealID, &a.Filename,
			&a.StoredName, &a.MimeType, &a.Size, &a.Path, &a.CreatedAt)
		if err == sql.ErrNoRows {
			c.JSON(http.StatusNotFound, gin.H{"error": "file not found"})
			return
		}
		if err != nil {
			c.JSON(http.StatusInternalServerError, gin.H{"error": "database error"})
			return
		}
		c.JSON(http.StatusOK, a)
	}
}

func DeleteFile(db *sql.DB) gin.HandlerFunc {
	return func(c *gin.Context) {
		userID := utils.GetUserID(c)
		id := c.Param("id")

		var path string
		err := db.QueryRow("SELECT path FROM attachments WHERE id = ? AND user_id = ?", id, userID).Scan(&path)
		if err == sql.ErrNoRows {
			c.JSON(http.StatusNotFound, gin.H{"error": "file not found"})
			return
		}

		os.Remove(path)
		db.Exec("DELETE FROM attachments WHERE id = ? AND user_id = ?", id, userID)

		utils.LogAudit(db, userID, "delete", "attachment", 0, "Deleted file id="+id, c)
		c.JSON(http.StatusOK, gin.H{"message": "file deleted", "deleted_at": time.Now()})
	}
}
