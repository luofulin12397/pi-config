#!/usr/bin/env python3
"""
控制台前端冒烟测试（Playwright 无头浏览器）。
自动：登录 → 遍历各页 → 收集页面 console 错误与未处理异常 → 截图。
运行：python3 scripts/console_smoke.py [base_url]（默认 http://127.0.0.1:55001）
"""
import sys
from playwright.sync_api import sync_playwright

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:55001"
errors = []


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 900})
        page.on("console", lambda m: errors.append(f"[console.{m.type}] {m.text}") if m.type == "error" else None)
        page.on("pageerror", lambda e: errors.append(f"[pageerror] {e}"))

        # 1. 登录页
        page.goto(f"{BASE}/console/")
        page.wait_for_selector(".login-card", timeout=8000)
        print("✓ 登录页渲染")
        page.screenshot(path="/tmp/smoke-1-login.png")

        # 2. admin 登录
        page.fill(".login-card input.ipt", "admin")
        page.fill(".login-card input[type=password]", "admin123")
        page.click(".login-card .btn")
        page.wait_for_selector(".sidenav", timeout=8000)
        print("✓ 登录进入控制台")

        # 3. 问答工作台
        page.wait_for_selector(".chat-welcome", timeout=5000)
        print("✓ 问答工作台渲染")
        # 发一问（走真实管线）
        page.fill(".composer textarea", "差旅报销的住宿标准和餐补是多少？")
        page.press(".composer textarea", "Enter")
        page.wait_for_selector(".msg-ai .md", timeout=60000)
        page.wait_for_timeout(2000)
        print("✓ 流式问答产出（source 见审计）")
        page.screenshot(path="/tmp/smoke-2-chat.png")

        # 4. 知识中心
        page.click("text=知识维护与导入")
        page.wait_for_selector("table", timeout=8000)
        print("✓ 知识中心渲染（台账行数：", page.locator("tbody tr").count(), "）")
        page.screenshot(path="/tmp/smoke-3-knowledge.png")

        # 5. 沉淀与运营（4 tab 遍历）
        page.click("text=沉淀与运营")
        page.wait_for_selector(".tabs", timeout=8000)
        for tab in ["FAQ 候选", "已发布 FAQ", "知识缺口", "问答审计"]:
            page.click(f".tabs a:has-text('{tab}')")
            page.wait_for_timeout(400)
        print("✓ 沉淀与运营 4 tab 遍历")
        page.screenshot(path="/tmp/smoke-4-ops.png")

        # 6. 运营看板
        page.click("text=运营看板")
        page.wait_for_selector(".kpi-grid", timeout=8000)
        page.wait_for_timeout(1200)  # 等 ECharts 渲染
        print("✓ 看板渲染（KPI 卡数：", page.locator(".kpi").count(), "）")
        page.screenshot(path="/tmp/smoke-5-dashboard.png")

        # 7. 组织与系统配置
        page.click("text=组织与系统配置")
        page.wait_for_selector("table", timeout=8000)
        print("✓ 组织与系统配置渲染")
        page.screenshot(path="/tmp/smoke-6-org.png")

        browser.close()

    print(f"\n{'=' * 50}")
    if errors:
        print(f"捕获 {len(errors)} 条页面错误：")
        for e in errors[:20]:
            print("  -", e[:160])
        sys.exit(1)
    print("页面 console 无错误 ✓ 冒烟通过")
    sys.exit(0)


if __name__ == "__main__":
    main()
