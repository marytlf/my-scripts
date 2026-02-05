package main

import (
	"bytes"
	"crypto/tls"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"net/http/cookiejar"
	"time"
)
// --- Configuration ---
const (
	Host        = "https://ec2-54-172-174-114.compute-1.amazonaws.com"
	Username    = "admin"
	Password    = "akV3vIVVxM7gTTwo"
	WaitSeconds = 30
	APITimeout  = 30 * time.Second
)

// --- Payload Structures ---

type PRTBBindingResponse struct {
	Data []struct {
		ID              string `json:"id"`
		UserId          string `json:"userId"`
		UserPrincipalId string `json:"userPrincipalId"`
	} `json:"data"`
}

type LoginPayload struct {
	Description  string `json:"description"`
	ResponseType string `json:"responseType"`
	Username     string `json:"username"`
	Password     string `json:"password"`
}

func main() {
	fmt.Printf("Starting Rancher test. Running for %d seconds...\n", WaitSeconds)

	endTime := time.Now().Add(time.Duration(WaitSeconds) * time.Second)
	client := createHTTPClient()

	// 1. Login Flow (with aggressive CSRF handling)
	err := executeLoginFlow(client, Host, Username, Password)
	if err != nil {
		fmt.Printf("❌ Login failed: %v\n", err)
		return
	}
	fmt.Println("✅ Login successful.")

	iteration := 1
	for time.Now().Before(endTime) {
		fmt.Printf("\n--- Iteration %d (%s remaining) ---\n", iteration, time.Until(endTime).Round(time.Second))

		// 2. Retrieve User Principal IDs from Bindings
		fmt.Println("🔗 Fetching Project Role Template Bindings...")
		err = getProjectRoleBindings(client, Host)
		if err != nil {
			fmt.Printf("⚠️ Error fetching bindings: %v\n", err)
		}

		time.Sleep(5 * time.Second)
		iteration++
	}

	fmt.Println("\nTest duration reached. Exiting.")
}

// --- New Function: Get Project Role Bindings ---

func getProjectRoleBindings(client *http.Client, host string) error {
	url := fmt.Sprintf("%s/v3/projectroletemplatebindings", host)
	
	req, _ := http.NewRequest("GET", url, nil)
	req.Header.Set("Accept", "application/json")

	resp, err := client.Do(req)
	if err != nil {
		return err
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		return fmt.Errorf("server returned status %d", resp.StatusCode)
	}

	var prtbResp PRTBBindingResponse
	body, _ := io.ReadAll(resp.Body)
	if err := json.Unmarshal(body, &prtbResp); err != nil {
		return fmt.Errorf("failed to parse JSON: %w", err)
	}

	if len(prtbResp.Data) == 0 {
		fmt.Println("   (No bindings found)")
		return nil
	}

	for _, item := range prtbResp.Data {
		pID := item.UserPrincipalId
		if pID == "" {
			pID = "<null/system>"
		}
		fmt.Printf("   -> Found User: %-12s | PrincipalID: %s\n", item.UserId, pID)
	}

	return nil
}

// --- Auth & Client Helpers ---

func executeLoginFlow(client *http.Client, host, username, password string) error {
	// 1. Get CSRF (Non-fatal if missing, as some local providers allow initial POST without it)
	csrfToken, _ := getCSRFToken(client, host)
	
	// 2. Perform Login
	return postLogin(client, host, username, password, csrfToken)
}

func getCSRFToken(client *http.Client, host string) (string, error) {
	// Hit v3 to initialize session cookies
	url := host + "/v3"
	req, _ := http.NewRequest("GET", url, nil)
	resp, err := client.Do(req)
	if err != nil {
		return "", err
	}
	defer resp.Body.Close()

	for _, cookie := range client.Jar.Cookies(req.URL) {
		if cookie.Name == "CSRF" {
			return cookie.Value, nil
		}
	}
	return "", fmt.Errorf("CSRF cookie not found")
}

func postLogin(client *http.Client, host, username, password, csrfToken string) error {
	loginUrl := host + "/v3-public/localProviders/local?action=login"
	payload := LoginPayload{
		Description:  "Automation Session",
		ResponseType: "cookie",
		Username:     username,
		Password:     password,
	}
	
	jsonData, _ := json.Marshal(payload)
	req, _ := http.NewRequest("POST", loginUrl, bytes.NewBuffer(jsonData))
	req.Header.Set("Content-Type", "application/json")
	if csrfToken != "" {
		req.Header.Set("X-Api-Csrf", csrfToken)
	}

	resp, err := client.Do(req)
	if err != nil {
		return err
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		body, _ := io.ReadAll(resp.Body)
		return fmt.Errorf("status %d: %s", resp.StatusCode, string(body))
	}
	return nil
}

func createHTTPClient() *http.Client {
	tr := &http.Transport{
		TLSClientConfig: &tls.Config{InsecureSkipVerify: true},
	}
	jar, _ := cookiejar.New(nil)
	return &http.Client{
		Jar:       jar,
		Transport: tr,
		Timeout:   APITimeout,
	}
}
