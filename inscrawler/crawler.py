from __future__ import unicode_literals

import glob
import json
import os
import re
import sys
import time
import traceback
from builtins import open
from time import sleep

from tqdm import tqdm

from .secret import secret
from .browser import Browser
from .exceptions import RetryException
from .fetch import fetch_caption
from .fetch import fetch_comments
from .fetch import fetch_datetime
from .fetch import fetch_imgs
from .fetch import fetch_likers
from .fetch import fetch_likes_plays
from .fetch import fetch_details
from .utils import instagram_int
from .utils import randmized_sleep
from .utils import retry

from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import NoSuchElementException, TimeoutException


class Logging(object):
    PREFIX = "instagram-crawler"

    def __init__(self):
        try:
            timestamp = int(time.time())
            self.cleanup(timestamp)
            self.logger = open("/tmp/%s-%s.log" % (Logging.PREFIX, timestamp), "w")
            self.log_disable = False
        except Exception:
            self.log_disable = True

    def cleanup(self, timestamp):
        days = 86400 * 7
        days_ago_log = "/tmp/%s-%s.log" % (Logging.PREFIX, timestamp - days)
        for log in glob.glob("/tmp/instagram-crawler-*.log"):
            if log < days_ago_log:
                os.remove(log)

    def log(self, msg):
        if self.log_disable:
            return

        self.logger.write(msg + "\n")
        self.logger.flush()

    def __del__(self):
        if self.log_disable:
            return
        self.logger.close()


class InsCrawler(Logging):
    URL = "https://www.instagram.com"
    RETRY_LIMIT = 10

    def __init__(self, has_screen=False):
        super(InsCrawler, self).__init__()
        self.browser = Browser(has_screen)
        self.page_height = 0
        self.login()

    def _dismiss_login_prompt(self):
        try:
            # Wait for the pop-up if it appears
            WebDriverWait(self.browser.driver, 5).until(
                EC.element_to_be_clickable((By.XPATH, "//button[contains(text(), 'Not Now')]"))
            ).click()
            print("Dismissed login prompt")
        except TimeoutException:
            print("No login prompt detected")

    def login(self):
        browser = self.browser
        try:
            url = "%s/accounts/login/" % (InsCrawler.URL)
            browser.driver.get(url)
            time.sleep(3)  # Add a delay to reduce bot detection

            # Enter Username :
            u_input = browser.find_one('input[name="username"]')
            u_input.send_keys(secret['username'])

            # Enter Password
            p_input = browser.find_one('input[name="password"]') 
            p_input.send_keys(secret['password'])

            # Pressing login button
            login_btn = browser.find_one(".L3NKy")
            login_btn = WebDriverWait(browser.driver, 10).until(
                EC.element_to_be_clickable((By.XPATH, "//button[@type='submit']"))
            )
            browser.driver.execute_script("arguments[0].click();", login_btn)
            time.sleep(1)  # Wait before interacting with elements
            login_btn.click()

            # Block further login prompts
            self._dismiss_login_prompt()

        except Exception as e:
            print(f" Error in logging in : {e}")    

        @retry()
        def check_login():
            if browser.find_one('input[name="username"]'):
                raise RetryException()

        check_login()

    def get_user_profile(self, username):
        browser = self.browser
        url = "%s/%s/" % (InsCrawler.URL, username)
        browser.get(url)
        
        time.sleep(5)  # Ensures all elements load

        try:
            # Wait for the h2 tag that contains the username
            WebDriverWait(browser.driver, 15).until(
                EC.presence_of_element_located((By.TAG_NAME, "h2"))
            )

            # Extract h2
            h2_element = browser.find_one("h2")

            if h2_element:
                # Extract the span inside h2
                name_span = h2_element.find_element(By.TAG_NAME, "span")
                profile_name = name_span.text if name_span else "N/A"
            else:
                profile_name = "N/A"

            # Extract bio description
            desc = browser.find_one(".-vDIg span")  
            bio_text = desc.text if desc else "N/A"

            # Extract profile picture
            photo = browser.find_one("._6q-tv")
            photo_url = photo.get_attribute("src") if photo else "N/A"

            # Wait for statistics section (posts, followers, following)
            WebDriverWait(browser.driver, 20).until(
                EC.presence_of_element_located((By.CLASS_NAME, "xc3tme8"))
            )
            stats_section = browser.find_one(".xc3tme8")

            if not stats_section:
                raise ValueError("Profile statistics section not found")

            statistics = [ele.text for ele in stats_section.find_elements(By.TAG_NAME, "span")]

            if len(statistics) < 3:
                raise ValueError("Profile statistics did not load correctly")

            post_num, follower_num, following_num = statistics[:3]

        except TimeoutException as e:
            raise ValueError(f"Profile elements did not load in time: {e}")

        except Exception as e:
            print(f"Error retrieving profile details: {e}")
            post_num, follower_num, following_num = "N/A", "N/A", "N/A"

        return {
            "name": profile_name,
            "desc": bio_text,
            "photo_url": photo_url,
            "post_num": post_num,
            "follower_num": follower_num,
            "following_num": following_num,
        }


    def get_user_profile_from_script_shared_data(self, username):
        browser = self.browser
        url = "%s/%s/" % (InsCrawler.URL, username)
        browser.get(url)
        source = browser.driver.page_source
        p = re.compile(r"window._sharedData = (?P<json>.*?);</script>", re.DOTALL)
        json_data = re.search(p, source).group("json")
        data = json.loads(json_data)

        user_data = data["entry_data"]["ProfilePage"][0]["graphql"]["user"]

        return {
            "name": user_data["full_name"],
            "desc": user_data["biography"],
            "photo_url": user_data["profile_pic_url_hd"],
            "post_num": user_data["edge_owner_to_timeline_media"]["count"],
            "follower_num": user_data["edge_followed_by"]["count"],
            "following_num": user_data["edge_follow"]["count"],
            "website": user_data["external_url"],
        }

    def get_user_posts(self, handle, number=None, detail=False):
        user_profile = self.get_user_profile(handle)
        if not number:
            number = instagram_int(user_profile["post_num"])

        self._dismiss_login_prompt()

        if detail:
            return self._get_posts_full(number)
        else:
            return self._get_posts(number,handle)

    def get_latest_posts_by_tag(self, tag, num,handle):
        url = "%s/explore/tags/%s/" % (InsCrawler.URL, tag)
        self.browser.get(url)
        return self._get_posts(num,handle)

    def auto_like(self, tag="", maximum=1000):
        self.login()
        browser = self.browser
        if tag:
            url = "%s/explore/tags/%s/" % (InsCrawler.URL, tag)
        else:
            url = "%s/explore/" % (InsCrawler.URL)
        self.browser.get(url)

        ele_post = browser.find_one(".v1Nh3 a")
        ele_post.click()

        for _ in range(maximum):
            heart = browser.find_one(".dCJp8 .glyphsSpriteHeart__outline__24__grey_9")
            if heart:
                heart.click()
                randmized_sleep(2)

            left_arrow = browser.find_one(".HBoOv")
            if left_arrow:
                left_arrow.click()
                randmized_sleep(2)
            else:
                break

    def _get_posts_full(self, num,handle):
        @retry()
        def check_next_post(cur_key):
            ele_a_datetime = browser.find_one(".eo2As .c-Yi7")

            # It takes time to load the post for some users with slow network
            if ele_a_datetime is None:
                raise RetryException()

            next_key = ele_a_datetime.get_attribute("href")
            if cur_key == next_key:
                raise RetryException()

        browser = self.browser
        browser.implicitly_wait(1)
        browser.scroll_down()
        ele_post = browser.find_one(".v1Nh3 a")
        ele_post.click()
        dict_posts = {}

        pbar = tqdm(total=num)
        pbar.set_description("fetching")
        cur_key = None

        all_posts = self._get_posts(num,handle)
        i = 1

        # Fetching all posts
        for _ in range(num):
            dict_post = {}

            # Fetching post detail
            try:
                if(i < num):
                    check_next_post(all_posts[i]['key'])
                    i = i + 1

                # Fetching datetime and url as key
                ele_a_datetime = browser.find_one(".eo2As .c-Yi7")
                cur_key = ele_a_datetime.get_attribute("href")
                dict_post["key"] = cur_key
                fetch_datetime(browser, dict_post)
                fetch_imgs(browser, dict_post)
                fetch_likes_plays(browser, dict_post)
                fetch_likers(browser, dict_post)
                fetch_caption(browser, dict_post)
                fetch_comments(browser, dict_post)

            except RetryException:
                sys.stderr.write(
                    "\x1b[1;31m"
                    + "Failed to fetch the post: "
                    + cur_key or 'URL not fetched'
                    + "\x1b[0m"
                    + "\n"
                )
                break

            except Exception:
                sys.stderr.write(
                    "\x1b[1;31m"
                    + "Failed to fetch the post: "
                    + cur_key if isinstance(cur_key,str) else 'URL not fetched'
                    + "\x1b[0m"
                    + "\n"
                )
                traceback.print_exc()

            self.log(json.dumps(dict_post, ensure_ascii=False))
            dict_posts[browser.current_url] = dict_post

            pbar.update(1)

        pbar.close()
        posts = list(dict_posts.values())
        if posts:
            posts.sort(key=lambda post: post["datetime"], reverse=True)
        return posts



    def _get_posts(self, num,handle):
        """
        Extracts posts, including images, captions, collaborators, and timestamps.
        Ensures posts belong to the correct profile and prevents scraping from other profiles.
        """
        from selenium.webdriver.common.by import By
        from selenium.webdriver.support.ui import WebDriverWait
        from selenium.webdriver.support import expected_conditions as EC

        TIMEOUT = 600
        browser = self.browser
        key_set = set()
        posts = []
        pre_post_num = 0
        wait_time = 1
        pbar = tqdm(total=num)

        profile_url_prefix = f"https://www.instagram.com/{handle}/"  # Ensure posts belong to the correct user

        def close_post_modal():
            """Clicks the close button to close the post modal before navigating to the next post."""
            try:
                close_button = WebDriverWait(browser.driver, 3).until(
                    EC.element_to_be_clickable((By.CSS_SELECTOR, "div.x6s0dn4 svg[aria-label='Close']"))
                )
                close_button.click()
                print("✅ Closed post modal")
                time.sleep(2)  # Allow time for the page to reset
            except Exception as e:
                print(f"⚠️ Warning: Close button not found or not clickable: {e}")

        def start_fetching(pre_post_num, wait_time):
            nonlocal num  # Ensure we track the remaining posts correctly
            scrolled = False  # Keep track if we need to scroll down

            while len(posts) < num:
                # ✅ Find only posts that belong to the target profile
                ele_posts = browser.find("div.x1lliihq")  # Updated selector for posts
                print(f"DEBUG: Found {len(ele_posts)} posts on the page")  # Debugging output

                for ele in ele_posts:
                    try:
                        # ✅ Extract post link and check if it belongs to the correct profile
                        post_link = ele.find_element(By.TAG_NAME, "a").get_attribute("href")

                        if not post_link.startswith(profile_url_prefix):  # Ensure it's from the target username
                            print(f"❌ Skipping non-profile post: {post_link}")
                            continue  # Skip posts from other profiles

                        if post_link not in key_set:
                            dict_post = {"key": post_link}

                            # ✅ Click to open the post modal
                            browser.js_click(ele.find_element(By.TAG_NAME, "a"))
                            time.sleep(2)  # Allow time for modal to open

                            # ✅ Extract image inside the post
                            try:
                                img = WebDriverWait(browser.driver, 5).until(
                                    EC.presence_of_element_located((By.CSS_SELECTOR, "div._aagv img"))
                                )
                                dict_post["img_url"] = img.get_attribute("src") if img else "N/A"
                            except:
                                dict_post["img_url"] = "N/A"

                            # ✅ Extract timestamp (post date & time)
                            try:
                                time_elem = WebDriverWait(browser.driver, 5).until(
                                    EC.presence_of_element_located((By.CSS_SELECTOR, "time.x1p4m5qa"))
                                )
                                dict_post["timestamp"] = time_elem.get_attribute("datetime")  # Format: 2025-02-02T09:57:16.000Z
                            except Exception as e:
                                print(f"Error extracting timestamp: {e}")
                                dict_post["timestamp"] = "N/A"

                            # ✅ Extract collaborators from the **header section** (`_aaqt _aaqu`)
                            try:
                                header_section = WebDriverWait(browser.driver, 5).until(
                                    EC.presence_of_element_located((By.CSS_SELECTOR, "div._aaqt._aaqu"))
                                )
                                creator_links = header_section.find_elements(By.TAG_NAME, "a")
                                creators = [link.text.strip() for link in creator_links if link.text.strip()]  # Get account names
                            except Exception as e:
                                print(f"Error extracting creators from header: {e}")
                                creators = []

                            # ✅ Extract caption (within post modal)
                            try:
                                caption_elem = WebDriverWait(browser.driver, 5).until(
                                    EC.presence_of_element_located((By.CSS_SELECTOR, "div.xt0psk2 h1"))
                                )
                                dict_post["caption"] = caption_elem.text if caption_elem else "N/A"

                                # ✅ Extract @mentions inside the caption
                                collab_links = caption_elem.find_elements(By.TAG_NAME, "a")
                                mentioned_collaborators = [link.text.strip() for link in collab_links if link.text.startswith("@")]

                            except Exception as e:
                                print(f"Error extracting caption or mentions: {e}")
                                dict_post["caption"] = "N/A"
                                mentioned_collaborators = []

                            # ✅ Ensure unique collaborators (avoid duplicates)
                            dict_post["collaborators"] = list(set(creators + mentioned_collaborators))  # Remove duplicates

                            # ✅ Close the post modal before moving to the next post
                            close_post_modal()

                            key_set.add(dict_post["key"])
                            posts.append(dict_post)

                            if len(posts) >= num:
                                return pre_post_num, wait_time  # Stop if we reached the required number

                    except Exception as e:
                        print(f"Error extracting post data: {e}")

                # ✅ Scroll down if we need more posts
                if len(posts) < num and not scrolled:
                    browser.scroll_down()
                    time.sleep(2)
                    scrolled = True  # Ensure we don't scroll too frequently

            return pre_post_num, wait_time

        pbar.set_description("fetching")
        while len(posts) < num and wait_time < TIMEOUT:
            post_num, wait_time = start_fetching(pre_post_num, wait_time)
            pbar.update(post_num - pre_post_num)
            pre_post_num = post_num

            loading = browser.find_one(".W1Bne")
            if not loading and wait_time > TIMEOUT / 2:
                break

        pbar.close()
        print("✅ Done. Successfully fetched", len(posts), "posts.")
        return posts[:num]
