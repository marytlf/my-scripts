package main

import (
	"bytes"
	"crypto/tls"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"net/http/cookiejar"
	"net/url"
	"time"
)
// --- Configuration ---
const (
	Host        = "https://"
	Username    = "admin"
	Password    = ""
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

type PrincipalDetail struct {
	ID          string `json:"id"`
	DisplayName string `json:"displayName"`
	LoginName   string `json:"loginName"`
	PrincipalId string `json:"principalId"`
	Me          bool   `json:"me"`
}

type LoginPayload struct {
	Description  string `json:"description"`
	ResponseType string `json:"responseType"`
	Username     string `json:"username"`
	Password     string `json:"password"`
}
func main() {
	fmt.Printf("Starting Rancher Principal Detail Test. Running for %d seconds...\n", WaitSeconds)

	endTime := time.Now().Add(time.Duration(WaitSeconds) * time.Second)
	client := createHTTPClient()

	err := executeLoginFlow(client, Host, Username, Password)
	if err != nil {
		fmt.Printf("❌ Login failed: %v\n", err)
		return
	}
	fmt.Println("✅ Login successful.")

	iteration := 1
	for time.Now().Before(endTime) {
		fmt.Printf("\n--- Iteration %d (%s remaining) ---\n", iteration, time.Until(endTime).Round(time.Second))

		// 1. Get the bindings to find Principal IDs
		principals := getPrincipalIDsFromBindings(client, Host)

		// 2. Fetch individual details for each Principal
		for _, pID := range principals {
			fetchIndividualPrincipal(client, Host, pID)
		}

		time.Sleep(5 * time.Second)
		iteration++
	}

	fmt.Println("\nTest duration reached. Exiting.")
}

// getPrincipalIDsFromBindings collects unique userPrincipalIds from the PRTB list
func getPrincipalIDsFromBindings(client *http.Client, host string) []string {
	apiUrl := host + "/v3/projectroletemplatebindings"
	req, _ := http.NewRequest("GET", apiUrl, nil)
	req.Header.Set("Accept", "application/json")

	resp, err := client.Do(req)
	if err != nil {
		fmt.Printf("   ⚠️ Error listing bindings: %v\n", err)
		return nil
	}
	defer resp.Body.Close()

	var prtbResp PRTBBindingResponse
	body, _ := io.ReadAll(resp.Body)
	json.Unmarshal(body, &prtbResp)

	var ids []string
	seen := make(map[string]bool)
	for _, item := range prtbResp.Data {
		fmt.Printf("   👤 [UserID: %s]\n", item.UserId)
		// Filter out null or system admins and duplicates
		//if item.UserPrincipalId != "" && !seen[item.UserPrincipalId] {
		if item.UserId != "" && !seen[item.UserId] && item.UserId != "system:admin"{
			ids = append(ids, item.UserId)
			seen[item.UserId] = true
		}
	}
	return ids
}

// fetchIndividualPrincipal performs the specific GET /v3/principals/<encoded_id>
func fetchIndividualPrincipal(client *http.Client, host, principalID string) {
	// Crucial: URL Encode the Principal ID (e.g., openldap_user://... -> openldap_user%3A%2F%2F...)
	user_local := fmt.Sprintf("local://%s",principalID)
	encodedID := url.QueryEscape(user_local)
	apiUrl := fmt.Sprintf("%s/v3/principals/%s", host, encodedID)
        fmt.Printf("   URL:: %s\n",apiUrl)
	req, _ := http.NewRequest("GET", apiUrl, nil)
	req.Header.Set("Accept", "application/json")

	resp, err := client.Do(req)
	if err != nil {
		fmt.Printf("   ❌ Request failed for %s: %v\n", principalID, err)
		return
	}
	defer resp.Body.Close()

	if resp.StatusCode == http.StatusOK {
		var detail PrincipalDetail
		body, _ := io.ReadAll(resp.Body)
		json.Unmarshal(body, &detail)
		//fmt.Printf("   👤 Detail Found: %s (%s) [ID: %s]\n", detail.DisplayName, detail.LoginName, detail.PrincipalId)
		fmt.Printf("   👤 Detail Found: (%s) \n", detail)
	} else {
		fmt.Printf("   ⚠️ Could not fetch details for %s (Status: %d)\n", principalID, resp.StatusCode)
	}
}

// --- Auth & Client Helpers (Standard) ---

func executeLoginFlow(client *http.Client, host, username, password string) error {
	csrfToken, _ := getCSRFToken(client, host)
	return postLogin(client, host, username, password, csrfToken)
}

func getCSRFToken(client *http.Client, host string) (string, error) {
	req, _ := http.NewRequest("GET", host+"/v3", nil)
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
	return "", fmt.Errorf("CSRF not found")
}

func postLogin(client *http.Client, host, username, password, csrfToken string) error {
	loginUrl := host + "/v3-public/localProviders/local?action=login"
	payload := LoginPayload{Description: "UI session", ResponseType: "cookie", Username: username, Password: password}
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
	return nil
}

func createHTTPClient() *http.Client {
	tr := &http.Transport{TLSClientConfig: &tls.Config{InsecureSkipVerify: true}}
	jar, _ := cookiejar.New(nil)
	return &http.Client{Jar: jar, Transport: tr, Timeout: APITimeout}
}
