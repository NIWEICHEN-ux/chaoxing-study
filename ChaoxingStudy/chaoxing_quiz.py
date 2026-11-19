"""Answer a quiz through its normal browser controls."""

import re
from concurrent.futures import ThreadPoolExecutor, as_completed

from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from chaoxing_quiz_preview import QUESTIONS, QUIZ_FRAMES


def solve_quiz_batches(questions, solve_questions, max_workers=4):
    """Run independent model batches concurrently without sharing WebDriver."""
    batches = [questions[offset:offset + 10] for offset in range(0, len(questions), 10)]
    answers = {}
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        pending = [executor.submit(solve_questions, batch) for batch in batches]
        try:
            for future in as_completed(pending):
                answers.update(future.result())
                print(f"已获得 {len(answers)}/{len(questions)} 道题的模型答案。", flush=True)
        finally:
            for future in pending:
                future.cancel()
    return answers


def complete_quiz(driver, solve_questions, expected_count=None, timeout=20):
    """Prepare all answers, fill the quiz and confirm once."""
    driver.switch_to.default_content()
    wait = WebDriverWait(driver, timeout)
    try:
        for selector in QUIZ_FRAMES:
            wait.until(EC.frame_to_be_available_and_switch_to_it((By.CSS_SELECTOR, selector)))

        submit = (By.CSS_SELECTOR, ".ZY_sub a.btnSubmit.workBtnIndex")
        wait.until(EC.visibility_of_element_located(submit))
        rows = driver.find_elements(By.CSS_SELECTOR, QUESTIONS)
        if not rows or (expected_count is not None and len(rows) != expected_count):
            raise ValueError(f"当前加载了 {len(rows)} 道题，与预期不符。")

        questions = []
        controls = {}
        for row in rows:
            question_id = row.get_dom_attribute("id")
            kind = row.find_element(By.CSS_SELECTOR, ".newZy_TItle").text.strip("【】[] ：:")
            if kind not in {"单选题", "多选题", "判断题"} or question_id in controls:
                raise ValueError(f"无法处理题目 {question_id} 的题型或重复 ID。")
            role = "checkbox" if kind == "多选题" else "radio"
            options = [
                option for option in row.find_elements(By.CSS_SELECTOR, f'ul.Zy_ulTop > li[role="{role}"]')
                if option.is_displayed()
            ]
            if len(options) < 2:
                raise ValueError(f"题目 {question_id} 的选项未加载完整。")
            stem = " ".join(node.text for node in row.find_elements(By.CSS_SELECTOR, ".Zy_TItle p"))
            values = [
                option.find_element(By.CSS_SELECTOR, "label span[data]").get_dom_attribute("data")
                for option in options
            ]
            if any(not value for value in values) or len(set(values)) != len(values):
                raise ValueError(f"题目 {question_id} 的选项标识无效。")
            field = row.find_element(By.ID, "answer" + question_id.removeprefix("question"))
            controls[question_id] = (options, values, field)
            questions.append({
                "id": question_id,
                "type": kind,
                "stem": stem,
                "options": [
                    {"number": number, "text": option.find_element(By.CSS_SELECTOR, "a.after").text}
                    for number, option in enumerate(options, start=1)
                ],
            })

        answers = solve_quiz_batches(questions, solve_questions)
        if not rows[0].is_displayed() or not EC.element_to_be_clickable(submit)(driver):
            raise RuntimeError("等待模型期间原测验页面已失效，请重新打开测验。")

        for question in questions:
            options, values, field = controls[question["id"]]
            desired = {values[number - 1] for number in answers[question["id"]]}
            raw_value = field.get_property("value") or ""
            if question["type"] == "多选题":
                current = set(re.findall(r"[A-Z]", raw_value))
                if re.sub(r"[A-Z,;\s]", "", raw_value) or current - set(values):
                    raise ValueError(f"无法核对多选题 {question['id']} 的已选项。")
                for option, value in zip(options, values):
                    if (value in current) != (value in desired):
                        option.click()
                recorded = set(re.findall(r"[A-Z]", field.get_property("value") or ""))
            else:
                wanted = next(iter(desired))
                if raw_value != wanted:
                    options[values.index(wanted)].click()
                recorded = {field.get_property("value")}
            if recorded != desired:
                raise ValueError(f"题目 {question['id']} 的选中状态与模型输出不一致。")

        wait.until(EC.element_to_be_clickable(submit)).click()
        driver.switch_to.default_content()
        confirm = (
            By.XPATH,
            '//*[@id="workpop"][.//*[@id="popcontent"][normalize-space(.)="确认提交？" or normalize-space(.)="确认提交?"]]//a[@id="popok"]',
        )
        wait.until(
            EC.element_to_be_clickable(confirm),
            message="主页面没有出现“确认提交？”弹窗的提交按钮。",
        ).click()
        print("已点击确认提交，等待平台更新章节状态。", flush=True)
    finally:
        driver.switch_to.default_content()
