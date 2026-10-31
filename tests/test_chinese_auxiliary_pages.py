from __future__ import annotations

import unittest

import server


class ChineseAuxiliaryPageTests(unittest.TestCase):
    def setUp(self):
        self.client = server.app.test_client()

    def test_readiness_page_contains_complete_client_side_chinese_locale(self):
        response = self.client.get("/status?lang=zh")
        self.assertEqual(response.status_code, 200)
        page = response.get_data(as_text=True)
        self.assertIn("new URLSearchParams(window.location.search).get('lang')", page)
        self.assertIn("localStorage.getItem('cdc_lang')", page)
        self.assertIn("localStorage.setItem('cdc_lang', requestedLocale)", page)
        self.assertIn("dashboardLink.href = currentLanguage === 'zh' ? '/zh' : '/'", page)
        self.assertIn("currentLanguage === 'zh' && data.msg_zh", page)
        self.assertIn("已经就绪，可以开始。", page)
        self.assertIn("剧本包验证失败。技术详情", page)
        self.assertIn("window.history.replaceState", page)
        self.assertIn("无法复制诊断信息", page)
        self.assertIn('id="language-toggle"', page)

    def test_chinese_dashboard_has_a_persisted_entry_route_and_localized_controls(self):
        response = self.client.get("/zh")
        self.assertEqual(response.status_code, 200)
        page = response.get_data(as_text=True)
        self.assertIn('<html lang="zh-CN">', page)
        self.assertIn("localStorage.setItem('cdc_lang', 'zh')", page)
        self.assertIn("window.location.href = lang === 'zh' ? '/zh' : '/'", page)
        self.assertIn('data-zh="默认"', page)
        self.assertIn('data-zh-placeholder="公开更新／指令标题"', page)
        self.assertIn('/static/js/tactical_engine.js', page)

    def test_chinese_chair_guide_covers_current_operating_workflow(self):
        response = self.client.get("/chair_guide_zh")
        self.assertEqual(response.status_code, 200)
        page = response.get_data(as_text=True)
        for expected in (
            "辩论期间的基本流程",
            "合理的裁定幅度",
            "导出态势报告",
            "/status?lang=zh",
            "支援任务不可用",
            'href="/chair_guide"',
        ):
            self.assertIn(expected, page)
        self.assertNotIn("http://127.0.0.1:5000/status", page)


if __name__ == "__main__":
    unittest.main()
