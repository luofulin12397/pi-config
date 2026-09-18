#!/usr/bin/env python3
"""
控制台交互操作冒烟（Playwright）：真实点击各页操作按钮，捕获 JS 错误。
覆盖：沉淀页（挖掘/加候选/发布/驳回/缓存开关/缺口转任务）、知识页（权限弹窗/切片/启停/编辑）、组织页（角色权限编辑）。
运行：python3 scripts/console_ops_smoke.py
"""
import sys
from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:55001"
errs = []


def main():
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True)
        page = b.new_page(viewport={"width": 1440, "height": 900})
        page.on("pageerror", lambda e: errs.append(f"[pageerror] {e}"))
        page.on("console", lambda m: errs.append(f"[console.{m.type}] {m.text}") if m.type == "error" else None)
        page.add_init_script("window.__errs=[];window.onerror=function(m,s,l){window.__errs.push(m+' @'+l)};")
        # prompt/confirm 自动确认（统一 handler，避免重复 accept）
        def on_dialog(d):
            msg = d.message
            if "问法" in msg:
                d.accept("生鲜商品破损/变质如何申请退款？")
            elif "答案" in msg:
                d.accept("生鲜商品签收后 24 小时内拍照申请仅退款，1-3 个工作日原路退回。")
            elif "新密码" in msg:
                d.accept("test123456")
            else:
                d.accept()
        page.on("dialog", on_dialog)

        page.goto(f"{BASE}/console/")
        page.wait_for_selector(".login-card")
        page.fill(".login-card input.ipt", "admin")
        page.fill(".login-card input[type=password]", "admin123")
        page.click(".login-card .btn")
        page.wait_for_selector(".sidenav")

        # ---------- 沉淀与运营 ----------
        page.click("text=沉淀与运营")
        page.wait_for_selector(".tabs")

        # 1) 触发挖掘
        page.click("text=立即挖掘")
        page.wait_for_timeout(4000)
        print("✓ 触发挖掘")

        # 2) 手动添加候选
        page.click(".tabs a:has-text('FAQ 候选')")
        page.wait_for_timeout(300)
        btn = page.locator("text=新建候选 FAQ")
        if btn.count():
            btn.click()
            page.fill("input[placeholder*='标准问题']", "冒烟测试问题（可删）")
            page.fill("input[placeholder*='标准答案']", "冒烟测试答案")
            page.click("button:has-text('添加')")
            page.wait_for_timeout(1500)
            print("✓ 添加候选")

        # 3) 发布第一个待审核候选（走 prompt 确认）
        page.wait_for_timeout(500)
        pub = page.locator("a:has-text('审核发布')")
        if pub.count():
            pub.first.click()
            page.wait_for_timeout(2000)
            print("✓ 审核发布（prompt 确认）")

        # 4) 驳回（若还有待审核）
        rej = page.locator("a:has-text('驳回')")
        if rej.count():
            rej.first.click()
            page.wait_for_timeout(1200)
            print("✓ 驳回候选")

        # 5) 已发布 FAQ：缓存开关
        page.click(".tabs a:has-text('已发布 FAQ')")
        page.wait_for_timeout(600)
        sw = page.locator("table .switch")
        if sw.count():
            sw.first.click(force=True)
            page.wait_for_timeout(900)
            sw.first.click(force=True)
            page.wait_for_timeout(700)
            print("✓ FAQ 缓存开关")

        # 6) 缺口转补全任务
        page.click(".tabs a:has-text('知识缺口')")
        page.wait_for_timeout(600)
        conv = page.locator("a:has-text('转知识补全任务')")
        if conv.count():
            conv.first.click()
            page.wait_for_selector(".modal")
            page.click(".modal button:has-text('创建任务')")
            page.wait_for_timeout(1500)
            print("✓ 缺口转补全任务")

        # 7) 审计 tab
        page.click(".tabs a:has-text('问答审计')")
        page.wait_for_timeout(800)
        print("✓ 审计 tab")

        # ---------- 知识中心 ----------
        page.click("text=知识维护与导入")
        page.wait_for_timeout(1000)
        # 权限弹窗
        page.locator("a:has-text('权限')").first.click()
        page.wait_for_selector(".perm-grid")
        page.wait_for_timeout(800)
        page.click(".modal button:has-text('保存并生效')")
        page.wait_for_timeout(1500)
        print("✓ 四维权限弹窗保存")
        # 切片预览
        page.locator("a:has-text('切片')").first.click()
        page.wait_for_selector(".drawer")
        page.wait_for_timeout(800)
        page.click(".drawer .x")
        page.wait_for_timeout(300)
        print("✓ 切片预览")
        # 启停开关
        sw2 = page.locator("table .switch").first
        sw2.click(force=True); page.wait_for_timeout(1000); sw2.click(force=True); page.wait_for_timeout(1000)
        print("✓ 知识启停")
        # 编辑弹窗
        page.locator("a:has-text('编辑')").first.click()
        page.wait_for_selector(".modal")
        page.click(".modal button:has-text('保存')")
        page.wait_for_timeout(1200)
        print("✓ 编辑保存")

        # ---------- 组织与系统配置 ----------
        page.click("text=组织与系统配置")
        page.wait_for_timeout(1200)
        # 角色权限编辑：切换角色 + 勾选 + 保存
        sel = page.locator("select").first
        if sel.count():
            sel.select_option(index=1)
            page.wait_for_timeout(800)
            page.locator(".pt-btns input").first.click()
            page.wait_for_timeout(300)
            page.locator(".pt-btns input").first.click()
            page.wait_for_timeout(300)
            save_btn = page.locator("button:has-text('保存角色权限')")
            if save_btn.count():
                save_btn.click()
                page.wait_for_timeout(1200)
            print("✓ 角色权限编辑")
        # 新增用户弹窗开/关
        nb = page.locator("button:has-text('新增用户')")
        if nb.count():
            nb.click()
            page.wait_for_selector(".modal")
            page.click(".modal button:has-text('取消')")
            page.wait_for_timeout(300)
            print("✓ 用户弹窗")

        page.screenshot(path="/tmp/ops-smoke-final.png", full_page=True)
        errs.extend(page.evaluate("window.__errs"))
        b.close()

    print("=" * 50)
    if errs:
        print(f"⚠ 捕获 {len(errs)} 条错误：")
        for e in errs[:15]:
            print("  -", str(e)[:200])
        sys.exit(1)
    print("交互操作冒烟通过：无 JS 错误 ✓")


if __name__ == "__main__":
    main()
