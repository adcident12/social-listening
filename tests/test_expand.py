"""_expand_collapsed re-pass — ปุ่มที่เกิน limit / คลิกหลุดระหว่าง DOM re-render ต้องถูกคลิกซ้ำ, ไม่ loop เดด (stub page, ไม่ต้อง browser)"""
from fetch import _expand_collapsed


class _StubBtns:
    def __init__(self, shared, page):
        self.shared = shared
        self.page = page

    def count(self):
        return self.shared["n"]

    def nth(self, i):
        shared, page = self.shared, self.page

        class _C:
            def click(self, timeout=None):
                page.attempts += 1
                if not shared["stuck"]:
                    shared["n"] -= 1
        return _C()


class _StubPage:
    """ปุ่มทั้งหมดอยู่ใน selector แรก (เหมือน DOM จริง — label เดิมเกิน limit)"""

    def __init__(self, n, stuck=False):
        self.pools = {}
        self.n, self.stuck = n, stuck
        self.attempts = 0

    def locator(self, sel):
        if sel not in self.pools:
            self.pools[sel] = {"n": self.n if not self.pools else 0, "stuck": self.stuck}
        return _StubBtns(self.pools[sel], self)

    def wait_for_timeout(self, ms):
        pass


def test_second_pass_covers_buttons_left_after_limit():
    page = _StubPage(12)  # 12 ปุ่ม label เดิม, limit=10 → ต้องมีผ่านที่ 2
    _expand_collapsed(page)
    assert page.pools and list(page.pools.values())[0]["n"] == 0
    assert page.attempts == 12


def test_stuck_buttons_stop_at_max_passes():
    page = _StubPage(3, stuck=True)  # คลิกไม่หาย — ต้องหยุดที่ cap ไม่ loop เดด
    _expand_collapsed(page)
    assert page.attempts <= 3 * 10  # max_passes(3) × limit(10)
