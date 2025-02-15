import os

from selenium import webdriver
from selenium.common.exceptions import NoSuchElementException
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.common.desired_capabilities import DesiredCapabilities
from selenium.webdriver.chrome.service import Service
import json,time
from fake_useragent import UserAgent
from .utils import randmized_sleep

class Browser:
    def __init__(self, has_screen):
        chrome_options = Options()
        
        if not has_screen:
            chrome_options.add_argument("--headless")  # Run in headless mode

        chrome_options.add_argument("--start-maximized")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--auto-open-devtools-for-tabs") 
        chrome_options.add_argument("--enable-logging")
        chrome_options.set_capability("goog:loggingPrefs", {"performance": "ALL"})
        
        self.driver = webdriver.Chrome(
            service=Service("/opt/homebrew/bin/chromedriver"),
            options=chrome_options,
        )

        self.driver.implicitly_wait(5)

    def enable_network_logging(self):
        """Enable Network Logging using Chrome DevTools Protocol (CDP)."""
        try:
            self.driver.execute_script("window.performance_log = [];")
            self.driver.execute_script("""
                (function() {
                    var oldXHR = window.XMLHttpRequest;
                    function newXHR() {
                        var realXHR = new oldXHR();
                        realXHR.addEventListener("readystatechange", function() {
                            if(realXHR.readyState == 4 && realXHR.responseURL.includes("graphql/query")) {
                                window.performance_log.push(realXHR.responseURL);
                            }
                        }, false);
                        return realXHR;
                    }
                    window.XMLHttpRequest = newXHR;
                })();
            """)
            print("✅ Network logging enabled via DevTools.")
        except Exception as e:
            print(f"❌ Error enabling network logging: {e}")


    def get_network_logs(self):
        """Retrieves GraphQL XHR network logs from Instagram and saves them to a file."""
        try:
            logs = self.driver.get_log("performance")  # Get browser performance logs
            print(f"🔍 Captured {len(logs)} network events.")  
            graphql_logs = []

            for log_entry in logs:
                try:
                    log_message = json.loads(log_entry["message"])["message"]

                    # ✅ Ensure log_message is valid
                    if not log_message or not isinstance(log_message, dict):
                        continue

                    # ✅ Check if it's a network response event
                    if log_message.get("method", "") == "Network.responseReceived":
                        params = log_message.get("params", {})
                        
                        # ✅ Ensure params is valid
                        if not params or not isinstance(params, dict):
                            continue

                        response_url = params.get("response", {}).get("url", "")
                        resource_type = params.get("type", "")

                        # ✅ Filter only **XHR requests**
                        if resource_type != "XHR":
                            continue  # Skip non-XHR requests

                        print(f"🔗 Captured XHR Request: {response_url}")  # Debugging output

                        # ✅ Filter only GraphQL requests
                        if "graphql/query" in response_url:
                            request_id = params.get("requestId")
                            print(f"📡 GraphQL Request ID: {request_id}")  # Debugging output

                            # Fetch full response using Chrome DevTools Protocol (CDP)
                            raw_response = self.driver.execute_cdp_cmd(
                                "Network.getResponseBody", {"requestId": request_id}
                            )

                            # ✅ Ensure raw_response is valid before parsing JSON
                            if not raw_response or "body" not in raw_response:
                                print(f"⚠️ Skipping empty response for {request_id}")
                                continue

                            graphql_data = json.loads(raw_response.get("body", "{}"))

                            # ✅ Append raw GraphQL response to the list
                            graphql_logs.append(graphql_data)

                except Exception as e:
                    print(f"⚠️ Skipping invalid log entry: {e}")
                    continue  # Skip and continue with the next log

            if graphql_logs:
                print("✅ Extracted GraphQL XHR Post Data.")
                
                # ✅ Dump all responses to a JSON file
                file_name = "graphql_logs.json"
                with open(file_name, "w", encoding="utf-8") as file:
                    json.dump(graphql_logs, file, indent=2)

                print(f"📂 GraphQL responses saved to {file_name}")
            else:
                print("⚠️ No valid GraphQL logs found.")

            return graphql_logs

        except Exception as e:
            print(f"❌ Error capturing GraphQL XHR response: {e}")
            return []


    @property
    def page_height(self):
        return self.driver.execute_script("return document.body.scrollHeight")

    def get(self, url):
        self.driver.get(url)

    @property
    def current_url(self):
        return self.driver.current_url

    def implicitly_wait(self, t):
        self.driver.implicitly_wait(t)

    def find_one(self, css_selector, elem=None, waittime=0):
        obj = elem or self.driver

        if waittime:
            WebDriverWait(obj, waittime).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, css_selector))
            )

        try:
            return obj.find_element(By.CSS_SELECTOR, css_selector)
        except NoSuchElementException:
            return None

    def find(self, css_selector, elem=None, waittime=0):
        obj = elem or self.driver

        try:
            if waittime:
                WebDriverWait(obj, waittime).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, css_selector))
                )
        except TimeoutException:
            return None

        try:
            return obj.find_elements(By.CSS_SELECTOR, css_selector)
        except NoSuchElementException:
            return None

    def scroll_down(self, wait=0.3):
        self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight)")
        randmized_sleep(wait)

    def scroll_up(self, offset=-1, wait=2):
        if offset == -1:
            self.driver.execute_script("window.scrollTo(0, 0)")
        else:
            self.driver.execute_script("window.scrollBy(0, -%s)" % offset)
        randmized_sleep(wait)

    def js_click(self, elem):
        self.driver.execute_script("arguments[0].click();", elem)

    def open_new_tab(self, url):
        self.driver.execute_script("window.open('%s');" %url)
        self.driver.switch_to.window(self.driver.window_handles[1])

    def close_current_tab(self):
        self.driver.close()

        self.driver.switch_to.window(self.driver.window_handles[0])

    def __del__(self):
        try:
            self.driver.quit()
        except Exception:
            pass

    def send(driver, cmd, params={}):
        resource = "/session/%s/chromium/send_command_and_get_result" % driver.session_id
        url = driver.command_executor._url + resource
        body = json.dumps({'cmd': cmd, 'params': params})
        response = driver.command_executor._request('POST', url, body)
        return response.get('value')

        