"""Read-only inspection of the quiz displayed in the current chapter."""

from collections import Counter

from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait


QUIZ_FRAMES = (
    "iframe#iframe",
    '#pageDiv .ans-attach-ct iframe[src*="/ananas/modules/work/index.html"]',
    "iframe#frame_content",
)
QUESTIONS = 'div.singleQuesId[id^="question"]'


def preview_quiz(driver, timeout=10):
    """Print the visible question counts and controls, then restore the main page."""
    driver.switch_to.default_content()
    wait = WebDriverWait(driver, timeout)
    try:
        for selector in QUIZ_FRAMES:
            wait.until(
                EC.frame_to_be_available_and_switch_to_it((By.CSS_SELECTOR, selector)),
                message=f"找不到测验 iframe {selector}",
            )

        questions = wait.until(
            EC.visibility_of_any_elements_located((By.CSS_SELECTOR, QUESTIONS)),
            message="测验框里没有找到可见的题目。",
        )
        counts = Counter()
        samples = {}
        for question in questions:
            labels = question.find_elements(By.CSS_SELECTOR, ".newZy_TItle")
            label = labels[0].text.strip("【】[] ：:") if labels else ""
            counts[label or "未识别题型"] += 1
            if label in {"单选题", "多选题", "判断题"} and label not in samples:
                samples[label] = question

        submit = driver.find_elements(By.CSS_SELECTOR, ".ZY_sub a.btnSubmit.workBtnIndex")
        confirm = driver.find_elements(By.CSS_SELECTOR, '#confirmSubWin a.bluebtn[role="button"]')
        print(f"可见题目 {len(questions)} 道，按题型统计 {dict(counts)}", flush=True)
        print(f"提交按钮 {len(submit)} 个，确认按钮节点 {len(confirm)} 个", flush=True)
        for label, question in samples.items():
            stem_parts = question.find_elements(By.CSS_SELECTOR, ".Zy_TItle p")
            stem = " ".join(part.text.strip() for part in stem_parts).strip()
            selector = 'ul.Zy_ulTop > li[role="checkbox"]' if label == "多选题" else 'ul.Zy_ulTop > li[role="radio"]'
            options = question.find_elements(By.CSS_SELECTOR, selector)
            print(f"【{label}】{stem or '（题干为空）'}", flush=True)
            visible_options = [option for option in options if option.is_displayed()]
            for number, option in enumerate(visible_options, start=1):
                texts = option.find_elements(By.CSS_SELECTOR, "a.after")
                option_text = texts[0].text.strip() if texts else ""
                print(f"  {number}. {option_text or '（选项文字为空）'}", flush=True)
    finally:
        driver.switch_to.default_content()
