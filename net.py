import json
import time
import os
from inscrawler.browser import Browser
from inscrawler.secret import secret
from selenium.webdriver.common.desired_capabilities import DesiredCapabilities

class InstagramScraper:
    def __init__(self, has_screen=False):
        """Initialize the scraper with a browser instance."""
        self.browser = Browser(has_screen)
    
    def login_instagram(self):
        """Logs into Instagram using saved credentials."""
        browser = self.browser
        try:
            url = "https://www.instagram.com/accounts/login/"
            browser.get(url)
            time.sleep(3)  # Allow page to load

            # Enter Username & Password
            u_input = browser.find_one('input[name="username"]')
            p_input = browser.find_one('input[name="password"]')

            if u_input and p_input:
                u_input.send_keys(secret['username'])
                p_input.send_keys(secret['password'])

                # Press Login Button
                login_btn = browser.find_one("button[type='submit']")
                if login_btn:
                    login_btn.click()
                    print("✅ Successfully logged in to Instagram.")
                    time.sleep(2)  # Allow login to process
                else:
                    print("❌ Login button not found.")
            else:
                print("❌ Username or password field not found.")

        except Exception as e:
            print(f"❌ Error in login: {e}")

    def visit_profile(self, handle):
        """Navigates to the specified Instagram profile and captures network logs."""
        browser = self.browser
        profile_url = f"https://www.instagram.com/{handle}/"
        browser.get(profile_url)
        time.sleep(2)  # Allow profile page to load

        print(f"✅ Navigated to {handle}'s profile.")

        # ✅ Enable Network Logging via DevTools Protocol
        self.browser.enable_network_logging()

        # ✅ Capture GraphQL Requests
        logs = self.extract_graphql_data()

        if logs:
            self.save_to_json(logs)  # ✅ Ensure this function runs

    def extract_graphql_data(self):
        """Captures Instagram GraphQL API response and extracts post data."""
        try:
            logs = self.browser.get_network_logs()  # Capture Network Logs
            graphql_logs = []

            if not logs:
                print("⚠️ No GraphQL logs captured. The network logs might be empty.")
                return []

            for log_entry in logs:
                log_message = json.loads(log_entry["message"])["message"]

                # Check if it's a network response event
                if "Network.responseReceived" in log_message.get("method", ""):
                    params = log_message.get("params", {})
                    response_url = params.get("response", {}).get("url", "")

                    # Filter only GraphQL requests related to user timeline
                    if "graphql/query" in response_url and "feed__user_timeline_graphql_connection" in response_url:
                        request_id = params.get("requestId")

                        # Fetch full response
                        raw_response = self.browser.driver.execute_cdp_cmd("Network.getResponseBody", {"requestId": request_id})
                        graphql_data = json.loads(raw_response.get("body", "{}"))

                        # Extract timeline posts
                        posts = graphql_data.get("data", {}).get("xdt_api__v1__feed__user_timeline_graphql_connection", {}).get("edges", [])

                        for post in posts:
                            node = post.get("node", {})

                            post_details = {
                                "post_id": node.get("id", "N/A"),
                                "code": node.get("code", "N/A"),
                                "media_pk": node.get("pk", "N/A"),
                                "caption": node.get("caption", {}).get("text", "N/A"),
                                "timestamp": time.strftime('%Y-%m-%d %H:%M:%S', time.gmtime(node.get("caption", {}).get("created_at", 0))),
                                "mentions": [],  # To be extracted later
                            }

                            graphql_logs.append(post_details)

            if graphql_logs:
                print("✅ Extracted GraphQL Post Data:")
                print(json.dumps(graphql_logs, indent=2))

            return graphql_logs

        except Exception as e:
            print(f"❌ Error extracting GraphQL response: {e}")
            return []

    def save_to_json(self, data):
        """Writes the extracted GraphQL post data to a JSON file."""
        file_name = "graphql_logs.json"
        
        try:
            if not data:
                print("⚠️ No data to save. Skipping JSON file creation.")
                return

            print(f"📁 Writing {len(data)} posts to {file_name}...")

            # Load existing data if the file exists
            try:
                with open(file_name, "r", encoding="utf-8") as file:
                    existing_data = json.load(file)
            except (FileNotFoundError, json.JSONDecodeError):
                existing_data = []

            # Append new data
            existing_data.extend(data)

            # Save back to file
            with open(file_name, "w", encoding="utf-8") as file:
                json.dump(existing_data, file, indent=2)

            print(f"✅ Data successfully saved to {file_name}")

        except Exception as e:
            print(f"❌ Error saving data to JSON: {e}")

    def run(self, handle):
        """Runs the Instagram scraper."""
        try:
            self.login_instagram()
            self.visit_profile(handle)
        finally:
            self.browser.driver.quit()


# Run the script
if __name__ == "__main__":
    INSTAGRAM_HANDLE = "cristiano"

    scraper = InstagramScraper(has_screen=False)
    scraper.run(INSTAGRAM_HANDLE)
