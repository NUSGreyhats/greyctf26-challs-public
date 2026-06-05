package middleware

import (
	"crm/utils"

	"github.com/gin-gonic/gin"
)

func CORS() gin.HandlerFunc {
	return func(c *gin.Context) {
		c.Header(utils.HeaderAccessControlAllowOrigin, "*")
		c.Header(utils.HeaderAccessControlAllowMethods, "GET, POST, PUT, DELETE, OPTIONS, PATCH")
		c.Header(utils.HeaderAccessControlAllowHeaders, utils.CORSAllowedHeadersValue)
		c.Header(utils.HeaderAccessControlMaxAge, "86400")
		if c.Request.Method == "OPTIONS" {
			c.AbortWithStatus(204)
			return
		}
		c.Next()
	}
}
