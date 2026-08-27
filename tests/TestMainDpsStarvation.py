import time
import unittest

from src.task.BaseCombatTask import BaseCombatTask


class FakeChar:

    def __init__(self, index, role, last_switch_in_time, buff=False,
                 buff_time=5):
        self.index = index
        self.char_type = role
        self.is_main_dps = role == 'MainDps'
        self.is_healer = role == 'Healer'
        self.is_sub_dps = role == 'SubDps'
        self.last_switch_in_time = last_switch_in_time
        self.buff_time = buff_time
        self._buff = buff

    def has_buff(self):
        return self._buff

    def __repr__(self):
        return f'{self.char_type}#{self.index}'


class TestMainDpsStarvation(unittest.TestCase):
    """When concerto never fills, the two supports swap forever.

    `_unbuffed_support_target` picks whichever support lacks its buff. With
    the bar stuck, that is always one of them, so the main DPS - the only
    character able to build concerto - never gets on screen and the deadlock
    keeps itself alive. #1626.
    """

    def _task(self):
        task = BaseCombatTask.__new__(BaseCombatTask)
        return task

    def test_starved_main_dps_is_pulled_in(self):
        now = time.time()
        task = self._task()
        main = FakeChar(1, 'MainDps', now - 60)          # off screen a minute
        healer = FakeChar(2, 'Healer', now - 1)
        sub = FakeChar(3, 'SubDps', now - 2)
        target = task._choose_switch_target_by_buff_time(healer, [main, healer, sub])
        self.assertIs(main, target)

    def test_main_dps_on_screen_is_left_alone(self):
        now = time.time()
        task = self._task()
        main = FakeChar(1, 'MainDps', now - 60)
        healer = FakeChar(2, 'Healer', now - 1)
        # 主C自己在场时不该被这条兜底影响，照常走原有逻辑。
        target = task._choose_switch_target_by_buff_time(main, [main, healer])
        self.assertIsNot(main, target)

    def test_recently_used_main_dps_is_not_forced_in(self):
        now = time.time()
        task = self._task()
        main = FakeChar(1, 'MainDps', now - 3)           # just had its turn
        healer = FakeChar(2, 'Healer', now - 1)
        target = task._choose_switch_target_by_buff_time(healer, [main, healer])
        self.assertIsNot(main, target)

    def test_never_switched_in_counts_as_starved(self):
        # last_switch_in_time < 0 means "has not been on screen at all".
        task = self._task()
        main = FakeChar(1, 'MainDps', -1)
        healer = FakeChar(2, 'Healer', time.time() - 1)
        self.assertIs(main, task._starved_main_dps_target([main, healer]))

    def test_no_candidates_returns_current(self):
        task = self._task()
        healer = FakeChar(2, 'Healer', time.time())
        self.assertIs(healer, task._choose_switch_target_by_buff_time(healer, []))
