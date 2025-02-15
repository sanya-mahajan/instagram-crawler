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

        caps = DesiredCapabilities.CHROME
        caps["goog:loggingPrefs"] = {"performance": "ALL"}

        # ✅ Properly Initialize Chrome WebDriver (Selenium 4+)
        self.driver = webdriver.Chrome(
            executable_path="/opt/homebrew/bin/chromedriver",
            options=chrome_options,
            desired_capabilities=caps
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
        """Retrieves GraphQL network logs from Instagram."""
        try:
            logs = self.driver.get_log("performance")  # Get browser performance logs
            print(f"🔍 Captured {len(logs)} network events.") 
            graphql_logs = []

            # return graphql_logs
            for log_entry in logs:
                log_message = json.loads(log_entry["message"])["message"]

                # Check if it's a network response event
                if "Network.responseReceived" in log_message.get("method", ""):
                    params = log_message.get("params", {})
                    response_url = params.get("response", {}).get("url", "")
                    print(f"🔗 Captured Request: {response_url}")
                    # Filter only GraphQL requests related to user timeline
                    if "graphql/query" in response_url and "feed__user_timeline_graphql_connection" in response_url:
                        request_id = params.get("requestId")

                        # Fetch full response
                        raw_response = self.driver.execute_cdp_cmd("Network.getResponseBody", {"requestId": request_id})
                        graphql_data = json.loads(raw_response.get("body", "{}"))

                        # Extract timeline posts
                        posts = graphql_data.get("data", {}).get("xdt_api__v1__feed__user_timeline_graphql_connection", {}).get("edges", [])

                        for post in posts:
                            node = post.get("node", {})

                            post_details = {
                                "post_id": node.get("id"),
                                "code": node.get("code"),
                                "media_pk": node.get("pk"),
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
            print(f"❌ Error capturing GraphQL response: {e}")
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

    