import json
from pathlib import Path
from getpass import getpass
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import StaleElementReferenceException, TimeoutException
from selenium.common.exceptions import ElementClickInterceptedException
from chaoxing_quiz import complete_quiz
from deepseek_solver import solve_questions

config_path = Path(__file__).with_name("config.local.json")
if not config_path.is_file():
    raise SystemExit("Copy config.example.json to config.local.json and fill in your course settings.")
config = json.loads(config_path.read_text(encoding="utf-8"))
driver = webdriver.Edge()
url_1 = "https://i.chaoxing.com/base?ws=1"
driver.get(url_1,)
driver.find_element("id","phone").click()
driver.find_element("id","phone").send_keys("#")#输入账号（最好手机号）
driver.find_element("id","pwd").click()
driver.find_element("id","pwd").send_keys("#")#输入密码
driver.find_element(By.ID, "loginBtn").click()
WebDriverWait(driver, 15).until(
    EC.frame_to_be_available_and_switch_to_it((By.ID, "frame_content"))
)

link = WebDriverWait(driver, 15).until(
    EC.element_to_be_clickable(
        (By.CSS_SELECTOR, config["course_selector"])
    )
)
wait = WebDriverWait(driver, 15)
tabs_before = driver.window_handles
link.click()

wait.until(EC.new_window_is_opened(tabs_before))
course_tab = (set(driver.window_handles) - set(tabs_before)).pop()
driver.switch_to.window(course_tab)

chapter_link = wait.until(
    EC.element_to_be_clickable((By.CSS_SELECTOR, config["chapters_selector"]))
)
chapter_link.click()

wait = WebDriverWait(driver, 15)

driver.switch_to.default_content()
wait.until(
    EC.frame_to_be_available_and_switch_to_it(
        (By.ID, "frame_content-zj")
    )
)

chapter = wait.until(
    EC.element_to_be_clickable((By.CSS_SELECTOR, config["start_selector"]))
)
chapter.click()

driver.switch_to.default_content()
driver.find_element("id", "prevNextFocusNext").click()



ACTIVE_CHAPTER = (
    By.CSS_SELECTOR,
    "#coursetree .posCatalog_select.posCatalog_active[id^='cur']",
)
CHAPTER_TITLES = (
    By.CSS_SELECTOR,
    "#coursetree .posCatalog_select[id^='cur'] > span.posCatalog_name",
)


def read_active_chapter(driver):
    """读取目录中当前高亮的章节行 ID。"""
    rows = driver.find_elements(*ACTIVE_CHAPTER)
    return rows[0].get_attribute("id") if rows else False


def find_next_chapter(driver, current_row_id):
    """按目录顺序返回下一节的行 ID 和标题。"""
    chapters = driver.execute_script(
        """
        return Array.from(document.querySelectorAll(arguments[0]), title => [
            title.parentElement.id,
            title.getAttribute("title") || title.textContent.trim()
        ])
        """,
        CHAPTER_TITLES[1],
    )
    for index, (row_id, _) in enumerate(chapters):
        if row_id == current_row_id:
            return (chapters[index + 1] if index + 1 < len(chapters) else None,)
    return False


def start_chapter_video(driver, timeout=5):
    """尝试通过课程播放器的正常按钮开始播放。"""
    wait = WebDriverWait(driver, timeout)
    driver.switch_to.default_content()

    try:
        wait.until(
            EC.frame_to_be_available_and_switch_to_it((By.ID, "iframe"))
        )
        wait.until(
            EC.frame_to_be_available_and_switch_to_it(
                (By.CSS_SELECTOR, "iframe[src*='/ananas/modules/video/']")
            )
        )

        video = wait.until(
            EC.presence_of_element_located((By.ID, "video_html5_api"))
        )
        if not video.get_property("paused") or video.get_property("ended"):
            return

        wait.until(
            EC.element_to_be_clickable(
                (By.CSS_SELECTOR, "button.vjs-big-play-button")
            )
        ).click()
        print("已点击播放视频，等待平台更新章节状态。", flush=True)
    except TimeoutException:
        print("未找到可点击的播放按钮，继续等待章节完成。", flush=True)
    except ElementClickInterceptedException:
        print("播放按钮被遮挡，请在浏览器中手动点播放。", flush=True)
    finally:
        driver.switch_to.default_content()


def continue_completed_chapters(driver, completion_timeout=3600, navigation_timeout=90):
    driver.switch_to.default_content()
    navigation_wait = WebDriverWait(
        driver,
        navigation_timeout,
        ignored_exceptions=(StaleElementReferenceException,),
    )

    while True:
        current_row_id = navigation_wait.until(
            read_active_chapter,
            message="目录中没有找到高亮的当前章节。",
        )

        completed_icon = (
            By.CSS_SELECTOR,
            f"#coursetree #{current_row_id} > span.icon_Completed",
        )
        if not driver.find_elements(*completed_icon):
            if current_row_id == config["quiz_row_id"]:
                complete_quiz(driver, solve_questions, expected_count=config["quiz_question_count"], timeout=90)
            else:
                start_chapter_video(driver)
        print(f"等待章节 {current_row_id} 显示“已完成”……", flush=True)
        WebDriverWait(driver, completion_timeout).until(
            EC.presence_of_element_located(completed_icon),
            message=f"章节 {current_row_id} 在等待时间内没有显示“已完成”。",
        )

        (next_chapter,) = navigation_wait.until(
            lambda browser: find_next_chapter(browser, current_row_id),
            message=f"目录刷新后找不到章节 {current_row_id}。",
        )
        if next_chapter is None:
            print("目录最后一节已完成。")
            return

        next_row_id, next_title = next_chapter
        next_title_locator = (
            By.CSS_SELECTOR,
            f"#coursetree #{next_row_id} > span.posCatalog_name",
        )
        print(f"已检测到完成标记，准备点击目录中的「{next_title}」。", flush=True)
        
        click_blocked = False

        def click_next_title(browser):
            nonlocal click_blocked

            title = EC.element_to_be_clickable(next_title_locator)(browser)
            if not title:
                return False

            try:
                title.click()
            except ElementClickInterceptedException:
                if not click_blocked:
                    print(
                        f"「{next_title}」被遮挡，请在浏览器里关闭课程通知。"
                        "脚本会自动重试。",
                        flush=True,
                    )
                click_blocked = True
                return False

            return True

        navigation_wait.until(
            click_next_title,
            message=f"等待点击「{next_title}」超时，请检查课程通知是否仍在遮挡。",
        )

        navigation_wait.until(
            lambda browser: read_active_chapter(browser) == next_row_id,
            message=f"已点击「{next_title}」，但目录没有高亮这一节。",
        )
        print(f"已进入「{next_title}」。", flush=True)


# 放在进入章节详情页之后，复用现有的 driver。
try:
    continue_completed_chapters(driver)
except (TimeoutException, RuntimeError) as error:
    print(f"停止：{getattr(error, 'msg', str(error))}")
input()



    




