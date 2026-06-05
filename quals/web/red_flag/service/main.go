package main

import (
	"log"
	"os"

	"crm/config"
	"crm/database"
	"crm/handlers"
	"crm/middleware"

	"github.com/gin-gonic/gin"
)

func main() {
	db, err := database.Init()
	if err != nil {
		log.Fatalf("Failed to initialise database: %v", err)
	}
	defer db.Close()

	os.MkdirAll(config.UploadDir, 0755)
	os.MkdirAll("./data", 0755)

	if !config.Debug {
		gin.SetMode(gin.ReleaseMode)
	}

	r := gin.New()
	r.Use(gin.Logger())
	r.Use(gin.Recovery())
	r.Use(middleware.CORS())

	r.GET("/", func(c *gin.Context) {
		c.File("./static/index.html")
	})
	r.Static("/static", "./static")

	api := r.Group("/api")

	// ── Public ────────────────────────────────────────────────────────────────
	auth := api.Group("/auth")
	{
		auth.POST("/register",       handlers.Register(db))
		auth.POST("/login",          handlers.Login(db))
		auth.POST("/forgot-password", handlers.ForgotPassword(db))
		auth.POST("/reset-password", handlers.ResetPassword(db))
	}

	// Debug / health (unauthenticated; disabled in production via APP_ENV)
	if config.Debug {
		api.GET("/debug/health", handlers.HealthCheck(db))
		api.GET("/debug/info",   handlers.DebugInfo(db))
	}

	// ── Protected ─────────────────────────────────────────────────────────────
	v1 := api.Group("/")
	v1.Use(middleware.AuthRequired(db))
	{
		// Profile & keys
		v1.GET("/auth/me",                handlers.GetMe(db))
		v1.POST("/auth/logout",           handlers.Logout(db))
		v1.PUT("/users/profile",          handlers.UpdateProfile(db))
		v1.GET("/users/apikey",           handlers.GetAPIKey(db))
		v1.POST("/users/apikey/regenerate", handlers.RegenerateAPIKey(db))

		// Customers
		v1.GET("/customers",              handlers.ListCustomers(db))
		v1.POST("/customers",             handlers.CreateCustomer(db))
		v1.GET("/customers/:id",          handlers.GetCustomer(db))
		v1.PUT("/customers/:id",          handlers.UpdateCustomer(db))
		v1.DELETE("/customers/:id",       handlers.DeleteCustomer(db))

		// Customer sub-resources
		v1.GET("/customers/:id/notes",      handlers.GetCustomerNotes(db))
		v1.POST("/customers/:id/notes",     handlers.CreateNote(db))
		v1.GET("/customers/:id/activities", handlers.GetCustomerActivities(db))
		v1.POST("/customers/:id/activities", handlers.CreateActivity(db))
		v1.GET("/customers/:id/files",      handlers.GetCustomerFiles(db))
		v1.GET("/customers/:id/deals",      handlers.GetCustomerDeals(db))

		// Notes
		v1.PUT("/notes/:id",    handlers.UpdateNote(db))
		v1.DELETE("/notes/:id", handlers.DeleteNote(db))

		// Activities
		v1.PUT("/activities/:id",          handlers.UpdateActivity(db))
		v1.DELETE("/activities/:id",       handlers.DeleteActivity(db))
		v1.POST("/activities/:id/complete", handlers.CompleteActivity(db))

		// Deals
		v1.GET("/deals",              handlers.ListDeals(db))
		v1.POST("/deals",             handlers.CreateDeal(db))
		v1.GET("/deals/:id",          handlers.GetDeal(db))
		v1.PUT("/deals/:id",          handlers.UpdateDeal(db))
		v1.DELETE("/deals/:id",       handlers.DeleteDeal(db))
		v1.PUT("/deals/:id/stage",    handlers.UpdateDealStage(db))

		// File attachments
		v1.POST("/files/upload",    handlers.UploadFile(db))
		v1.GET("/files/download",   handlers.DownloadFile(db))
		v1.GET("/files/:id",        handlers.GetFileInfo(db))
		v1.DELETE("/files/:id",     handlers.DeleteFile(db))

		// Reports & analytics
		v1.GET("/reports/summary",  handlers.ReportSummary(db))
		v1.GET("/reports/pipeline", handlers.DealsPipeline(db))
		v1.GET("/reports/activity", handlers.CustomerActivity(db))
		v1.POST("/reports/export",  handlers.ExportReport(db))

		// Email templates
		v1.GET("/email-templates",             handlers.ListEmailTemplates(db))
		v1.POST("/email-templates",            handlers.CreateEmailTemplate(db))
		v1.GET("/email-templates/:id",         handlers.GetEmailTemplate(db))
		v1.PUT("/email-templates/:id",         handlers.UpdateEmailTemplate(db))
		v1.DELETE("/email-templates/:id",      handlers.DeleteEmailTemplate(db))
		v1.POST("/email-templates/:id/preview", handlers.PreviewEmailTemplate(db))

		// Webhooks
		v1.GET("/webhooks",          handlers.ListWebhooks(db))
		v1.POST("/webhooks",         handlers.CreateWebhook(db))
		v1.GET("/webhooks/:id",      handlers.GetWebhook(db))
		v1.PUT("/webhooks/:id",      handlers.UpdateWebhook(db))
		v1.DELETE("/webhooks/:id",   handlers.DeleteWebhook(db))
		v1.POST("/webhooks/:id/test", handlers.TestWebhook(db))

		// Tags
		v1.GET("/tags",          handlers.ListTags(db))
		v1.POST("/tags",         handlers.CreateTag(db))
		v1.DELETE("/tags/:id",   handlers.DeleteTag(db))
	}

	// ── Admin ─────────────────────────────────────────────────────────────────
	admin := api.Group("/admin")
	admin.Use(middleware.AuthRequired(db))
	admin.Use(middleware.AdminRequired())
	{
		admin.GET("/users",                   handlers.AdminListUsers(db))
		admin.GET("/users/:id",               handlers.AdminGetUser(db))
		admin.PUT("/users/:id/role",          handlers.AdminUpdateUserRole(db))
		admin.DELETE("/users/:id",            handlers.AdminDeleteUser(db))
		admin.GET("/audit-logs",              handlers.GetAuditLogs(db))
		admin.POST("/impersonate/:user_id",   handlers.ImpersonateUser(db))
		admin.GET("/stats",                   handlers.AdminStats(db))
	}

	port := os.Getenv("PORT")
	if port == "" {
		port = "8080"
	}
	log.Printf("[CRM Pro v%s] Listening on :%s  debug=%v", config.AppVersion, port, config.Debug)
	if err := r.Run(":" + port); err != nil {
		log.Fatalf("Server error: %v", err)
	}
}
