package middleware

import (
	"crypto/hmac"
	"crypto/sha256"
	"database/sql"
	"encoding/base64"
	"encoding/json"
	"errors"
	"fmt"
	"net/http"
	"strings"
	"time"

	"crm/config"
	"crm/utils"

	"github.com/gin-gonic/gin"
)

type JWTClaims struct {
	Sub     int64  `json:"sub"`
	Email   string `json:"email"`
	Role    string `json:"role"`
	IsAdmin bool   `json:"is_admin"`
	Iat     int64  `json:"iat"`
	Exp     int64  `json:"exp"`
}

// AuthRequired validates JWT bearer tokens or API keys.
func AuthRequired(db *sql.DB) gin.HandlerFunc {
	return func(c *gin.Context) {
		tokenStr := ""

		authHeader := c.GetHeader(utils.HeaderAuthorization)
		if strings.HasPrefix(authHeader, "Bearer ") {
			tokenStr = strings.TrimPrefix(authHeader, "Bearer ")
		}

		// Fall back to API key authentication
		if tokenStr == "" {
			apiKey := c.GetHeader(utils.HeaderXAPIKey)
			if apiKey == "" {
				apiKey = c.Query("api_key")
			}
			if apiKey != "" {
				var userID int64
				var role string
				var isAdmin bool
				err := db.QueryRow(
					"SELECT id, role, isadmin FROM users WHERE api_key = ?", apiKey,
				).Scan(&userID, &role, &isAdmin)
				if err != nil {
					c.JSON(http.StatusUnauthorized, gin.H{"error": "invalid API key"})
					c.Abort()
					return
				}
				c.Set("user_id", userID)
				c.Set("user_role", role)
				c.Set("is_admin", isAdmin)
				c.Next()
				return
			}
		}

		if tokenStr == "" {
			c.JSON(http.StatusUnauthorized, gin.H{"error": "authentication required"})
			c.Abort()
			return
		}

		claims, err := parseJWT(tokenStr)
		if err != nil {
			c.JSON(http.StatusUnauthorized, gin.H{"error": fmt.Sprintf("invalid token: %v", err)})
			c.Abort()
			return
		}

		c.Set("user_id", claims.Sub)
		c.Set("user_role", claims.Role)
		c.Set("is_admin", claims.IsAdmin)
		c.Next()
	}
}

// AdminRequired checks that the caller has administrator privileges.
// Accepts either a valid admin JWT or the static X-Admin-Key header.
func AdminRequired() gin.HandlerFunc {
	return func(c *gin.Context) {
		// Allow programmatic admin access via shared key (e.g. internal scripts)
		if c.GetHeader(utils.HeaderXAdminKey) == config.AdminKey {
			c.Next()
			return
		}

		isAdmin, _ := c.Get("is_admin")
		role, _ := c.Get("user_role")
		if isAdmin == true || role == "admin" {
			c.Next()
			return
		}

		c.JSON(http.StatusForbidden, gin.H{"error": "administrator access required"})
		c.Abort()
	}
}

// parseJWT decodes and validates a JWT token.
// Supports HS256 and the "none" algorithm for internal service-to-service tokens.
func parseJWT(tokenStr string) (*JWTClaims, error) {
	parts := strings.Split(tokenStr, ".")
	if len(parts) != 3 {
		return nil, errors.New("malformed token")
	}

	headerBytes, err := base64.RawURLEncoding.DecodeString(parts[0])
	if err != nil {
		return nil, errors.New("invalid token header encoding")
	}
	var header struct {
		Alg string `json:"alg"`
		Typ string `json:"typ"`
	}
	if err := json.Unmarshal(headerBytes, &header); err != nil {
		return nil, errors.New("invalid token header")
	}

	payloadBytes, err := base64.RawURLEncoding.DecodeString(parts[1])
	if err != nil {
		return nil, errors.New("invalid token payload encoding")
	}
	var claims JWTClaims
	if err := json.Unmarshal(payloadBytes, &claims); err != nil {
		return nil, errors.New("invalid token claims")
	}

	if claims.Exp > 0 && time.Now().Unix() > claims.Exp {
		return nil, errors.New("token expired")
	}

	switch header.Alg {
	case "HS256":
		signingInput := parts[0] + "." + parts[1]
		mac := hmac.New(sha256.New, []byte(config.JWTSecret))
		mac.Write([]byte(signingInput))
		expected := base64.RawURLEncoding.EncodeToString(mac.Sum(nil))
		if !hmac.Equal([]byte(expected), []byte(parts[2])) {
			return nil, fmt.Errorf("invalid signature. Signing key might have rotated. Email %s for the new signing key.", config.SupportEmail)
		}
	default:
		return nil, fmt.Errorf("unsupported signing algorithm: %s", header.Alg)
	}

	return &claims, nil
}
