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

    # def get_user_profile(self, username):
    #     browser = self.browser
    #     url = "%s/%s/" % (InsCrawler.URL, username)
    #     browser.get(url)
    #     name = browser.find_one(".rhpdm")
    #     desc = browser.find_one(".-vDIg span")
    #     photo = browser.find_one("._6q-tv")
    #     # Statistics data old 
    #     # statistics = [ele.text for ele in browser.find(".g47SY")]
    #     # post_num, follower_num, following_num = statistics
    #     try:
    #         # Wait for the profile statistics section to be visible
    #         WebDriverWait(browser.driver, 20).until(
    #             EC.presence_of_element_located((By.CLASS_NAME, "xc3tme8"))
    #         )

    #         # Now extract the values inside the section
    #         stats_section = browser.find_one(".xc3tme8")

    #         if not stats_section:
    #             raise ValueError("Profile statistics section not found")

    #         # Find all number elements inside the section
    #         statistics = [ele.text for ele in stats_section.find_elements(By.TAG_NAME, "span")]

    #         if len(statistics) < 3:
    #             raise ValueError("Profile statistics did not load correctly")

    #         post_num, follower_num, following_num = statistics[:3]  # Extract first 3 values

    #     except TimeoutException:
    #         raise ValueError("Profile statistics did not load in time")

    #     except Exception as e:
    #         print(f"Error retrieving profile statistics: {e}")
    #         post_num, follower_num, following_num = "N/A", "N/A", "N/A"  # Return placeholders

    #     return {
    #         "name": name.text,
    #         "desc": desc.text if desc else None,
    #         "photo_url": photo.get_attribute("src"),
    #         "post_num": post_num,
    #         "follower_num": follower_num,
    #         "following_num": following_num,
    #     }

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

    def get_user_posts(self, username, number=None, detail=False):
        user_profile = self.get_user_profile(username)
        if not number:
            number = instagram_int(user_profile["post_num"])

        self._dismiss_login_prompt()

        if detail:
            return self._get_posts_full(number)
        else:
            return self._get_posts(number)

    def get_latest_posts_by_tag(self, tag, num):
        url = "%s/explore/tags/%s/" % (InsCrawler.URL, tag)
        self.browser.get(url)
        return self._get_posts(num)

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

    def _get_posts_full(self, num):
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

        all_posts = self._get_posts(num)
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

    # def _get_posts(self, num):
    #     """
    #         To get posts, we have to click on the load more
    #         button and make the browser call post api.
    #     """
    #     TIMEOUT = 600
    #     browser = self.browser
    #     key_set = set()
    #     posts = []
    #     pre_post_num = 0
    #     wait_time = 1

    #     pbar = tqdm(total=num)

    #     def start_fetching(pre_post_num, wait_time):
    #     # Find all post containers
    #         ele_posts = browser.find("div.x1lliihq")  # Updated selector

    #         print(f"DEBUG: Found {len(ele_posts)} posts on the page")  # 🔍 Debugging line

    #         for ele in ele_posts:
    #             try:
    #                 # Extract post link
    #                 post_link = ele.find_element(By.TAG_NAME, "a").get_attribute("href")

    #                 if post_link not in key_set:
    #                     dict_post = {"key": post_link}

    #                     # Extract image inside the post
    #                     try:
    #                         img = ele.find_element(By.CSS_SELECTOR, "div._aagv img")
    #                         dict_post["img_url"] = img.get_attribute("src") if img else "N/A"
    #                     except:
    #                         dict_post["img_url"] = "N/A"

    #                     key_set.add(post_link)
    #                     posts.append(dict_post)

    #                     if len(posts) == num:
    #                         break
    #             except Exception as e:
    #                 print(f"Error extracting post data: {e}")

                  

    #         if pre_post_num == len(posts):
    #             pbar.set_description("Wait for %s sec" % (wait_time))
    #             sleep(wait_time)
    #             pbar.set_description("fetching")

    #             wait_time *= 2
    #             browser.scroll_up(300)
    #         else:
    #             wait_time = 1

    #         pre_post_num = len(posts)
    #         browser.scroll_down()

    #         return pre_post_num, wait_time


    #     # def start_fetching(pre_post_num, wait_time):
    #     #     ele_posts = browser.find(".v1Nh3 a")

    #     #     print(f"DEBUG: Found {len(ele_posts)} posts on the page")  # Debugging line
    #     #     for ele in ele_posts:
    #     #         key = ele.get_attribute("href")
    #     #         if key not in key_set:
    #     #             dict_post = { "key": key }
    #     #             ele_img = browser.find_one(".KL4Bh img", ele)
    #     #             dict_post["caption"] = ele_img.get_attribute("alt")
    #     #             dict_post["img_url"] = ele_img.get_attribute("src")

    #     #             fetch_details(browser, dict_post)

    #     #             key_set.add(key)
    #     #             posts.append(dict_post)

    #     #             if len(posts) == num:
    #     #                 break

    #     #     if pre_post_num == len(posts):
    #     #         pbar.set_description("Wait for %s sec" % (wait_time))
    #     #         sleep(wait_time)
    #     #         pbar.set_description("fetching")

    #     #         wait_time *= 2
    #     #         browser.scroll_up(300)
    #     #     else:
    #     #         wait_time = 1

    #     #     pre_post_num = len(posts)
    #     #     browser.scroll_down()

    #     #     return pre_post_num, wait_time

    #     pbar.set_description("fetching")
    #     while len(posts) < num and wait_time < TIMEOUT:
    #         post_num, wait_time = start_fetching(pre_post_num, wait_time)
    #         pbar.update(post_num - pre_post_num)
    #         pre_post_num = post_num

    #         loading = browser.find_one(".W1Bne")
    #         if not loading and wait_time > TIMEOUT / 2:
    #             break

    #     pbar.close()
    #     print("Done. Fetched %s posts." % (min(len(posts), num)))
    #     return posts[:num]
    # def _get_posts(self, num):
    #     """
    #     Extracts posts, including images, captions, and collaborators.
    #     """
    #     TIMEOUT = 600
    #     browser = self.browser
    #     key_set = set()
    #     posts = []
    #     pre_post_num = 0
    #     wait_time = 1

    #     pbar = tqdm(total=num)

    #     def start_fetching(pre_post_num, wait_time):
    #         # Find all post containers
    #         ele_posts = browser.find("div.x1lliihq")    # Updated selector

    #         print(f"DEBUG: Found {len(ele_posts)} posts on the page")  # 🔍 Debugging line

    #         for ele in ele_posts:
    #             try:
    #                 # Extract post link
    #                 post_link = ele.find_element(By.TAG_NAME, "a").get_attribute("href")

    #                 if post_link not in key_set:
    #                     dict_post = {"key": post_link}

    #                     # Extract image inside the post
    #                     try:
    #                         img = ele.find_element(By.CSS_SELECTOR, "div._aagv img")
    #                         dict_post["img_url"] = img.get_attribute("src") if img else "N/A"
    #                     except:
    #                         dict_post["img_url"] = "N/A"

    #                     # Extract caption
    #                     try:
    #                         caption_elem = ele.find_element(By.CSS_SELECTOR, "h1")
    #                         dict_post["caption"] = caption_elem.text if caption_elem else "N/A"

    #                         # Extract collaborators (user mentions in <a> tags)
    #                         collab_links = caption_elem.find_elements(By.TAG_NAME, "a")
    #                         collaborators = [link.text for link in collab_links if link.text.startswith("@")]
    #                         dict_post["collaborators"] = collaborators if collaborators else "None"
    #                     except Exception as e:
    #                         print(f"Error extracting caption or collaborators: {e}")
    #                         dict_post["caption"] = "N/A"
    #                         dict_post["collaborators"] = "None"

    #                     key_set.add(post_link)
    #                     posts.append(dict_post)

    #                     if len(posts) == num:
    #                         break
    #             except Exception as e:
    #                 print(f"Error extracting post data: {e}")

    #         if pre_post_num == len(posts):
    #             pbar.set_description("Wait for %s sec" % (wait_time))
    #             sleep(wait_time)
    #             pbar.set_description("fetching")

    #             wait_time *= 2
    #             browser.scroll_up(300)
    #         else:
    #             wait_time = 1

    #         pre_post_num = len(posts)
    #         browser.scroll_down()

    #         return pre_post_num, wait_time

    #     pbar.set_description("fetching")
    #     while len(posts) < num and wait_time < TIMEOUT:
    #         post_num, wait_time = start_fetching(pre_post_num, wait_time)
    #         pbar.update(post_num - pre_post_num)
    #         pre_post_num = post_num

    #         loading = browser.find_one(".W1Bne")
    #         if not loading and wait_time > TIMEOUT / 2:
    #             break

    #     pbar.close()
    #     print("Done. Fetched %s posts." % (min(len(posts), num)))
    #     return posts[:num]


    # def _get_posts(self, num):
    #     """
    #     Extracts posts, including images, captions, and collaborators.
    #     """
    #     from selenium.webdriver.common.by import By
    #     from selenium.webdriver.support.ui import WebDriverWait
    #     from selenium.webdriver.support import expected_conditions as EC

    #     TIMEOUT = 600
    #     browser = self.browser
    #     key_set = set()
    #     posts = []
    #     pre_post_num = 0
    #     wait_time = 1

    #     pbar = tqdm(total=num)

    #     def start_fetching(pre_post_num, wait_time):
    #         # Find all post containers
    #         ele_posts = browser.find("div.x1lliihq")  # Updated selector

    #         print(f"DEBUG: Found {len(ele_posts)} posts on the page")  # 🔍 Debugging line

    #         for ele in ele_posts:
    #             try:
    #                 # Extract post link
    #                 post_link = ele.find_element(By.TAG_NAME, "a").get_attribute("href")

    #                 if post_link not in key_set:
    #                     dict_post = {"key": post_link}

    #                     # Extract image inside the post
    #                     try:
    #                         img = ele.find_element(By.CSS_SELECTOR, "div._aagv img")
    #                         dict_post["img_url"] = img.get_attribute("src") if img else "N/A"
    #                     except:
    #                         dict_post["img_url"] = "N/A"

    #                     # Extract caption and collaborators
    #                     try:
    #                         # Wait until the caption appears
    #                         caption_elem = WebDriverWait(ele, 5).until(
    #                             EC.presence_of_element_located((By.CSS_SELECTOR, "div.xt0psk2 h1"))
    #                         )
    #                         dict_post["caption"] = caption_elem.text if caption_elem else "N/A"

    #                         # Extract collaborator mentions
    #                         collab_links = caption_elem.find_elements(By.TAG_NAME, "a")
    #                         collaborators = [link.text for link in collab_links if link.text.startswith("@")]
    #                         dict_post["collaborators"] = collaborators if collaborators else "None"

    #                     except Exception as e:
    #                         print(f"Error extracting caption or collaborators: {e}")
    #                         dict_post["caption"] = "N/A"
    #                         dict_post["collaborators"] = "None"

    #                     key_set.add(post_link)
    #                     posts.append(dict_post)

    #                     if len(posts) == num:
    #                         break
    #             except Exception as e:
    #                 print(f"Error extracting post data: {e}")

    #         if pre_post_num == len(posts):
    #             pbar.set_description("Wait for %s sec" % (wait_time))
    #             sleep(wait_time)
    #             pbar.set_description("fetching")

    #             wait_time *= 2
    #             browser.scroll_up(300)
    #         else:
    #             wait_time = 1

    #         pre_post_num = len(posts)
    #         browser.scroll_down()

    #         return pre_post_num, wait_time

    #     pbar.set_description("fetching")
    #     while len(posts) < num and wait_time < TIMEOUT:
    #         post_num, wait_time = start_fetching(pre_post_num, wait_time)
    #         pbar.update(post_num - pre_post_num)
    #         pre_post_num = post_num

    #         loading = browser.find_one(".W1Bne")
    #         if not loading and wait_time > TIMEOUT / 2:
    #             break

    #     pbar.close()
    #     print("Done. Fetched %s posts." % (min(len(posts), num)))
    #     return posts[:num]


    def _get_posts(self, num):
        """
        Extracts posts, including images, captions, and collaborators.
        Since collaborator info is inside the post, each post must be clicked and opened.
        """
        TIMEOUT = 600
        browser = self.browser
        key_set = set()
        posts = []
        pre_post_num = 0
        wait_time = 1

        pbar = tqdm(total=num)

        def start_fetching(pre_post_num, wait_time):
            # Find all post containers
            ele_posts = browser.find("div.x1lliihq")  # Updated selector

            print(f"DEBUG: Found {len(ele_posts)} posts on the page")  # Debugging line

            for ele in ele_posts:
                try:
                    # Extract post link
                    post_link = ele.find_element(By.TAG_NAME, "a").get_attribute("href")

                    if post_link not in key_set:
                        dict_post = {"key": post_link}

                        # Extract image inside the post
                        try:
                            img = ele.find_element(By.CSS_SELECTOR, "div._aagv img")
                            dict_post["img_url"] = img.get_attribute("src") if img else "N/A"
                        except:
                            dict_post["img_url"] = "N/A"

                        # Visit the post to extract caption & collaborators
                        try:
                            browser.get(post_link)
                            time.sleep(2)  # Allow time for content to load

                            # Extract caption
                            caption_elem = browser.find_one("h1._ap3a")  # Check selector accuracy
                            dict_post["caption"] = caption_elem.text if caption_elem else "N/A"

                            # Extract collaborators (user mentions in <a> tags)
                            collab_links = caption_elem.find_elements(By.TAG_NAME, "a") if caption_elem else []
                            collaborators = [link.text for link in collab_links if link.text.startswith("@")]
                            dict_post["collaborators"] = collaborators if collaborators else "None"
                        except Exception as e:
                            print(f"Error extracting caption or collaborators: {e}")
                            dict_post["caption"] = "N/A"
                            dict_post["collaborators"] = "None"

                        key_set.add(post_link)
                        posts.append(dict_post)

                        if len(posts) == num:
                            break
                except Exception as e:
                    print(f"Error extracting post data: {e}")

            if pre_post_num == len(posts):
                pbar.set_description("Wait for %s sec" % (wait_time))
                sleep(wait_time)
                pbar.set_description("fetching")

                wait_time *= 2
                browser.scroll_up(300)
            else:
                wait_time = 1

            pre_post_num = len(posts)
            browser.scroll_down()

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
        print("Done. Fetched %s posts." % (min(len(posts), num)))
        return posts[:num]

