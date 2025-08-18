from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import NoSuchElementException, StaleElementReferenceException, TimeoutException
import time
import random
import sqlite3
import shutil
import os

PAGES = {
    "1": {
        "db": "golfvids.db",
        "search_terms": ["golfing memes", "funny golf videos", "golfing tips", "golfing videos"]
    },
    "2": {
        "db": "foodvids.db",
        "search_terms": ["low calorie meals", "low calorie recipes", "low calorie meal prep", "low calorie what i eat in a day"]
    },
    "3": {
        "db": "mensfashionvids.db",
        "search_terms": ["old money style men", "starboy style", "grisch style", "stockholm style men"]
    }
}

1
# Delete Selenium cache folder to prevent errors
cache_folder = r"C:\Users\ssjag\.cache\selenium"
if os.path.exists(cache_folder):
    shutil.rmtree(cache_folder)  # Remove cache to fix os error 183

# Initialize WebDriver with options
options = webdriver.ChromeOptions()
options.add_argument("--user-data-dir=C:/Users/ssjag/AppData/Local/Google/Chrome/User Data/SeleniumProfile")

# Start a new instance of Chrome WebDriver
driver = webdriver.Chrome(options=options)

# Database setup
def setup_database(db):
    conn = sqlite3.connect(db)
    cursor = conn.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS videos
                      (link TEXT PRIMARY KEY, creator TEXT, posted TEXT)''')
    conn.commit()
    return conn, cursor

def link_exists(cursor, link):
    cursor.execute("SELECT 1 FROM videos WHERE link = ?", (link,))
    return cursor.fetchone() is not None

def insert_into_database(cursor, link, creator):
    if link != "N/A" and not link_exists(cursor, link):
        cursor.execute("INSERT INTO videos (link, creator, posted) VALUES (?, ?, ?)", (link, creator, 0))
    else:
        print(f"Skipping duplicate link: {link}")

def close_database(conn):
    conn.commit()
    conn.close()

def login_tiktok():
    """Logs into TikTok and waits for search bar to appear."""
    driver.get("https://www.tiktok.com/login/phone-or-email/email")
    WebDriverWait(driver, 300).until(EC.presence_of_element_located((By.XPATH, "//input[@placeholder='Search']")))

def click_search_button():
    """Clicks the search button."""
    try:
        search_button = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.XPATH, "//*[@id='app']/div[2]/div/div/div[2]/div[2]/button/div/div[1]/div"))
        )
        search_button.click()
        print("Search button clicked.")
    except TimeoutException:
        print("Error: Search button did not appear in time.")

def search_tiktok(search_term):
    """Clears the search bar and types the new search term."""
    try:
        time.sleep(1)  # Ensure input is focused
        search_bar = driver.switch_to.active_element

        # Clear existing text
        search_bar.send_keys(Keys.CONTROL + "a")  
        search_bar.send_keys(Keys.BACKSPACE)  
        
        # Enter new search term
        for char in search_term:
            search_bar.send_keys(char)
            time.sleep(random.uniform(0.05, 0.15))  
        search_bar.send_keys(Keys.ENTER)
        time.sleep(5)
        print(f"Searching for: {search_term}")
    except Exception as e:
        print(f"Error typing search term: {e}")

from selenium.common.exceptions import ElementClickInterceptedException

def click_video_tab():
    """Clicks the 'Videos' tab, waiting if an overlay blocks it."""
    try:
        video_tab = WebDriverWait(driver, 20).until(
            EC.element_to_be_clickable((By.XPATH, "//*[@id='tabs-0-tab-search_video']"))
        )
        video_tab.click()
        print("Navigated to videos tab.")
    except ElementClickInterceptedException:
        print("Element click intercepted. Waiting 15 seconds before retrying...")
        time.sleep(15)  # Wait for overlay to disappear
        try:
            video_tab = WebDriverWait(driver, 20).until(
                EC.element_to_be_clickable((By.XPATH, "//*[@id='tabs-0-tab-search_video']"))
            )
            video_tab.click()
            print("Navigated to videos tab after waiting.")
        except Exception as e:
            print(f"Failed to click video tab after waiting: {e}")


def scrape_tiktok(search_term, num_videos, cursor):
    try:
        driver.refresh()
        click_search_button()  
        search_tiktok(search_term)  

        # Wait for search results to load
        WebDriverWait(driver, 20).until(
            EC.presence_of_element_located((By.XPATH, "//*[@id='tabs-0-tab-search_video']"))
        )
        print("Search results loaded.")

        # Click the "Videos" tab
        click_video_tab()


        # Wait for videos to load
        time.sleep(5)

        # Scroll to load more videos
        print("Scrolling to load videos...")
        previous_count = 0
        max_scrolls = 15  

        for _ in range(max_scrolls):
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(2)  
            
            video_elements = driver.find_elements(By.XPATH, "//*[@id='tabs-0-panel-search_video']/div/div/div")
            
            if len(video_elements) > previous_count:
                previous_count = len(video_elements)
            else:
                break  

        # Get video elements after scrolling
        video_elements = driver.find_elements(By.XPATH, "//*[@id='tabs-0-panel-search_video']/div/div/div")
        print(f"Found {len(video_elements)} video elements.")

        if not video_elements:
            print("No videos found for this search term.")
            return  

        # Limit to available videos to prevent index errors
        num_videos_to_scrape = min(num_videos, len(video_elements))

        for i in range(num_videos_to_scrape):
            try:
                try:
                    video_element = video_elements[i]
                except StaleElementReferenceException:
                    video_elements = driver.find_elements(By.XPATH, "//*[@id='tabs-0-panel-search_video']/div/div/div")
                    if i >= len(video_elements):
                        continue
                    video_element = video_elements[i]

                # Skip verified accounts
                try:
                    _ = video_element.find_element(By.XPATH, ".//*[name()='circle' and @fill='#20D5EC']")
                    continue
                except NoSuchElementException:
                    pass

                # Get video link
                try:
                    vid_link = video_element.find_element(By.XPATH, ".//a").get_attribute("href")
                except NoSuchElementException:
                    vid_link = "N/A"

                # Get username
                try:
                    username = video_element.find_element(By.CSS_SELECTOR, ".css-2zn17v-PUniqueId.etrd4pu6").text
                except NoSuchElementException:
                    username = "N/A"

                # Get caption (skip if contains restricted words)
                try:
                    cap = video_element.find_element(By.CSS_SELECTOR, ".css-j2a19r-SpanText.efbd9f0").text
                    if any(word in cap.lower() for word in ["via", "credit", "🎥"]):
                        continue
                    caption = cap
                except NoSuchElementException:
                    caption = "N/A"

                # Insert into database
                insert_into_database(cursor, vid_link, username)

            except StaleElementReferenceException:
                video_elements = driver.find_elements(By.XPATH, "//*[@id='tabs-0-panel-search_video']/div/div/div")
                continue

        print(f"Video details for search term '{search_term}' inserted into database.")

    except (NoSuchElementException, TimeoutException) as e:
        print(f"Error: {e}")

def main():
    print("Available pages:", ", ".join(PAGES.keys()))
    choice = input("Enter the page number (1 for golf, 2 for low calorie food, 3 for mens fashion)").strip().lower()

    if choice not in PAGES:
        print("Invalid selection.")
        return
    time.sleep(5)
    login_tiktok()

    db = PAGES[choice]["db"]
    search_terms = PAGES[choice]["search_terms"]

    conn, cursor = setup_database(db)

    for term in search_terms:
        scrape_tiktok(term, 50, cursor)

    close_database(conn)
    driver.quit()

main()


