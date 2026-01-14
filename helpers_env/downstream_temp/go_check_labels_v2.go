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
	"sync"
	"time"
)

// --- Configuration ---
const (
	Host  = "https://myrancher.org.internal:8443"
	Username= "admin"
	Password= "y8qDDA5gklq9NLDS"
	NumUsers= 1
	APITimeout   = 30 * time.Second
	// API to get all nodes/machines, which contain the cluster ID
	ManagementNodeAPI = "/v1/management.cattle.io.nodes?pagesize=100000&exclude=metadata.managedFields"
)

// Modified: Replaced single constant with a slice of required labels
var TARGET_NODE_LABELS = []string{
	"node-role.kubernetes.io/worker",
	"node-role.kubernetes.io/etcd",
	"node-role.kubernetes.io/control-plane",
}

// --- API Response Structures ---
type LoginPayload struct {
	Description string `json:"description"`
	ResponseType string `json:"responseType"`
	Username  string `json:"username"`
	Password  string `json:"password"`
}

type NodeList struct {
  Items []struct {
Metadata struct {
  Name string `json:"name"`
  Labels map[string]string `json:"labels"`
} `json:"metadata"`
  } `json:"items"`
}


type ManagementNodeList struct {
  Data []struct {
// We only care about the metadata sub-field for the namespace (Cluster ID)
Metadata struct {
  Namespace string `json:"namespace"`
	  Labels map[string]string `json:"labels"`
} `json:"metadata"`
  } `json:"data"`
}
// --- Main Execution ---
func main() {
	fmt.Printf("Starting Rancher multi-cluster node check with %d concurrent users...\n", NumUsers)
	
	var wg sync.WaitGroup
	startTime := time.Now()

	for i := 1; i <= NumUsers; i++ {
		wg.Add(1)
		go func(userNum int) {
			defer wg.Done()
			client := createHTTPClient()

			err := executeLoginFlow(client, Host, Username, Password, userNum)
			if err != nil {
				fmt.Printf("[User %02d] ❌ Login/Check failed: %v\n", userNum, err)
			} else {
				fmt.Printf("[User %02d] ✅ Login successful and all clusters checked.\n", userNum)
			}
		}(i)
	}

	wg.Wait()
	fmt.Printf("\nAll checks completed in %v.\n", time.Since(startTime))
}

// --- Login Flow Implementation (Modified) ---
func executeLoginFlow(client *http.Client, host, username, password string, userNum int) error {
  // 1. Login/CSRF/Validation steps (must pass before proceeding)
  csrfToken, err := getCSRFToken(client, host)
  if err != nil {
return fmt.Errorf("CSRF GET failed: %w", err)
  }
  if err := postLogin(client, host, username, password, csrfToken); err != nil {
return fmt.Errorf("login POST failed: %w", err)
  }
  if err := validateSession(client, host); err != nil {
return fmt.Errorf("session validation failed: %w", err)
  }
 
  // 2. Retrieve ALL Cluster IDs
  clusterIDs, err := getAllClusterIDs(client, host)
  if err != nil {
return fmt.Errorf("failed to retrieve cluster IDs: %w", err)
  }
  // 3. Check Nodes in ALL Discovered Clusters
 
  // Use a variable to track if ANY cluster check failed during the iteration
  var checkErr error
  for _, clusterID := range clusterIDs {
// If the check fails for ANY cluster, the function will return an error,
// but we want to check ALL clusters before returning the final status.
if err := checkNodeLabels(client, host, userNum, clusterID); err != nil {
  // Print the failure immediately
  fmt.Printf("[User %02d] ❌ Cluster %s reported errors during node check.\n", userNum, clusterID)
  checkErr = err // Store the error state
}
  }
 
  // Return the specific error if any check failed, or nil if all passed.
  return checkErr
}

// --- Dynamic Cluster Discovery (Unchanged) ---

// Retrieves all unique cluster IDs (c-m-...) the user has access to.
func getAllClusterIDs(client *http.Client, host string) ([]string, error) {
	url := host + ManagementNodeAPI
	req, err := http.NewRequest("GET", url, nil)
	if err != nil {
		return nil, err
	}
	req.Header.Set("Accept", "application/json")

	resp, err := client.Do(req)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		body, _ := io.ReadAll(resp.Body)
		return nil, fmt.Errorf("failed to get cluster IDs (status %d): %s", resp.StatusCode, body)
	}

	var nodeList ManagementNodeList
	if err := json.NewDecoder(resp.Body).Decode(&nodeList); err != nil {
		return nil, fmt.Errorf("failed to decode management node list: %w", err)
	}
 
	// Use a map to ensure we only get unique cluster IDs
	idMap := make(map[string]bool)
	var uniqueIDs []string
	for _, item := range nodeList.Data {
	  // 1. Get the cluster ID from the metadata.namespace field
	  clusterID := item.Metadata.Namespace

	  if clusterID != "" {
		// 2. Filter out the local cluster, which usually has namespace "local"
		if clusterID == "local" {
		  continue
		}
		
		// 3. Add to map only if unique
		if _, exists := idMap[clusterID]; !exists {
		  idMap[clusterID] = true
		  uniqueIDs = append(uniqueIDs, clusterID)
		}
	  }
	}
	return uniqueIDs, nil
}


// --- Check Node Labels via API Proxy (Uses Dynamic Cluster ID) ---
func checkNodeLabels(client *http.Client, host string, userNum int, clusterID string) error {
	// Target the specific downstream cluster using its ID in the proxy path
	url := fmt.Sprintf("%s/k8s/clusters/%s/api/v1/nodes?page=1&pagesize=100", host, clusterID)
	
	req, err := http.NewRequest("GET", url, nil)
	if err != nil {
		fmt.Printf("ERRORRRR")
		return err
	}
	req.Header.Set("Accept", "application/json")

	resp, err := client.Do(req)
	if err != nil {
		fmt.Printf("ERRRROOOR RESP")
		return err
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		body, _ := io.ReadAll(resp.Body)
		return fmt.Errorf("API proxy access failed for %s (status %d): %s", clusterID, resp.StatusCode, body)
	}
	var nodeList NodeList
	if err := json.NewDecoder(resp.Body).Decode(&nodeList); err != nil {
		return fmt.Errorf("failed to decode NodeList JSON for %s: %w", clusterID, err)
	}
 
	nodesMissingRole := 0
	
	// --- Start Output Generation for this Cluster ---
	
	// Print cluster summary header
	clusterStatus := "✅ All required roles found"
	
	for _, item := range nodeList.Items {
		nodeName := item.Metadata.Name
		
		// New logic: Check if ANY of the required labels are present
		hasRequiredRole := false
		var missingLabels []string
		
		for _, requiredLabel := range TARGET_NODE_LABELS {
			if _, exists := item.Metadata.Labels[requiredLabel]; exists {
				hasRequiredRole = true
				break // Found one, no need to check the rest for this node
			} else {
				// Keep track of which required labels are missing
				missingLabels = append(missingLabels, requiredLabel)
			}
		}
		
		if !hasRequiredRole {
			// Label is NOT found: Change cluster status and print details.
			clusterStatus = "❌ Missing required roles"
			
			// Print the cluster, node, and the specific label that is missing
			fmt.Printf("[User %02d] ⚠️ Node %s in %s is MISSING ALL required roles (%s). Current Labels: %v\n",
				userNum, nodeName, clusterID, missingLabels, item.Metadata.Labels)
			
			nodesMissingRole++
		}
	}
	
	// --------------------------------------------------------------------------
	// Print the final status for the cluster:
	if clusterStatus == "✅ All required roles found" {
		fmt.Printf("[User %02d] %s Cluster %s (%d nodes checked).\n",
			userNum, clusterStatus, clusterID, len(nodeList.Items))
	}
	// Note: If errors occurred, the detailed error messages were already printed in the loop above.
	// --------------------------------------------------------------------------

	if nodesMissingRole > 0 {
		return fmt.Errorf("found %d nodes missing a required role label in cluster %s", nodesMissingRole, clusterID)
	}
	return nil
}
// --- HTTP Client Setup (Unchanged) ---
func createHTTPClient() *http.Client {
  // ... (createHTTPClient remains the same)
	tr := &http.Transport{
		TLSClientConfig: &tls.Config{InsecureSkipVerify: true},
	}
	jar, _ := cookiejar.New(nil)
	client := &http.Client{
		Jar:		 jar,
		Transport: tr,
		Timeout: APITimeout,
	}
	urlObj, err := url.Parse(Host)
	if err != nil {
		panic(fmt.Sprintf("Failed to parse Host URL: %v", err))
	}
	cookies := []*http.Cookie{
		{Name: "R_PCS", Value: "light"},
		{Name: "R_REDIRECTED", Value: "true"},
		{Name: "R_LOCALE", Value: "en-us"},
	}
	client.Jar.SetCookies(urlObj, cookies)
	return client
}

// --- CSRF, POST Login, and Validation (Unchanged) ---

func getCSRFToken(client *http.Client, host string) (string, error) {
  // Simplified function to remove userNum argument, assuming it's not strictly needed for logging inside helpers
	url := host + "/v1/management.cattle.io.settings?exclude=metadata.managedFields"
	req, err := http.NewRequest("GET", url, nil)
	if err != nil {
		return "", err
	}
	req.Header.Set("Accept", "application/json")
	req.Header.Set("Accept-Language", "en-US,en;q=0.9,pt-BR;q=0.8,pt;q=0.7")
	req.Header.Set("User-Agent", "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Safari/537.36 OPR/121.0.0.0")
	req.Header.Set("Referer", host+"/dashboard/auth/login?logged-out")
	req.Header.Set("Sec-Fetch-Site", "same-origin")

	resp, err := client.Do(req)
	if err != nil {
		return "", err
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		body, _ := io.ReadAll(resp.Body)
		return "", fmt.Errorf("expected status 200, got %d. Body: %s", resp.StatusCode, body)
	}

	for _, cookie := range client.Jar.Cookies(req.URL) {
		if cookie.Name == "CSRF" {
			return cookie.Value, nil
		}
	}

	return "", fmt.Errorf("CSRF cookie not found in response")
}

func postLogin(client *http.Client, host, username, password, csrfToken string) error {
	url := host + "/v3-public/localProviders/local?action=login"
	payload := LoginPayload{Description: "UI session", ResponseType: "cookie", Username: username, Password: password}
	jsonPayload, err := json.Marshal(payload)
	if err != nil {
		return err
	}
	req, err := http.NewRequest("POST", url, bytes.NewBuffer(jsonPayload))
	if err != nil {
		return err
	}
	req.Header.Set("Accept", "application/json")
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("X-Api-Csrf", csrfToken)
	req.Header.Set("Referer", host+"/dashboard/auth/login?logged-out")
	req.Header.Set("Origin", host)

	resp, err := client.Do(req)
	if err != nil {
		return err
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		body, _ := io.ReadAll(resp.Body)
		return fmt.Errorf("login failed with status %d. Response: %s", resp.StatusCode, body)
	}
	rSess := ""
	for _, cookie := range client.Jar.Cookies(req.URL) {
		if cookie.Name == "R_SESS" {
			rSess = cookie.Value
			break
		}
	}
	if rSess == "" {
		return fmt.Errorf("R_SESS token missing after successful 200 OK")
	}
	return nil
}

func validateSession(client *http.Client, host string) error {
	url := host + "/v3/users?me=true"
	req, err := http.NewRequest("GET", url, nil)
	if err != nil {
		return err
	}
	req.Header.Set("Accept", "application/json")
	resp, err := client.Do(req)
	if err != nil {
		return err
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		return fmt.Errorf("session validation failed, status %d", resp.StatusCode)
	}
	return nil
}
