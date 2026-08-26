import unittest
import re
from pathlib import Path

from src.task.NightmareNestTask import NestTarget, NightmareNestTask


class FakeBox:

    def __init__(self, name, x=0, y=0, width=20, height=10):
        self.name = name
        self.x = x
        self.y = y
        self.width = width
        self.height = height


class TestNightmareNestTask(unittest.TestCase):

    def test_nest_is_checked_before_nightmare_changes_book_scroll(self):
        task = NightmareNestTask.__new__(NightmareNestTask)
        task.config = {'Which to Farm': ['Nightmare Purification', 'Tacet Discord Nest']}
        task._init_queue()
        self.assertEqual(['go_nest', 'go_nightmare', 'go_nightmare_scroll'],
                         [action.__name__ for action in task.queues])

    def test_capture_success_clears_combat_before_post_combat_waits(self):
        task = NightmareNestTask.__new__(NightmareNestTask)
        task._capture_mode = True
        task._in_combat = True
        picked = []

        task.pick_f = lambda handle_claim=True: picked.append(handle_claim)
        task.has_echo_notification = lambda: True

        def reset_to_false(reason=''):
            task._in_combat = False
            task.out_of_combat_reason = reason
            return False

        task.reset_to_false = reset_to_false

        self.assertFalse(task.on_combat_check())
        self.assertEqual([False], picked)
        self.assertFalse(task._in_combat)
        self.assertEqual('echo captured', task.out_of_combat_reason)

    def test_combat_nest_rechecks_after_pickup_in_team_and_open_world(self):
        for feature_name in ('team_close', 'fast_travel_custom'):
            with self.subTest(feature_name=feature_name):
                task = NightmareNestTask.__new__(NightmareNestTask)
                task._capture_mode = False
                task._capture_success = False
                combat_calls = []
                pickup_calls = []
                combat_results = iter([True, False])

                task.click = lambda *args, **kwargs: None
                task.wait_feature = lambda *args, **kwargs: FakeBox(feature_name)
                task.click_team_challenge = lambda: None
                task.wait_in_team_and_world = lambda *args, **kwargs: True
                task._travel_to_nest_or_skip = lambda nest: True
                task.sleep = lambda *args, **kwargs: None
                task.find_f_with_text = lambda: False
                task.run_until = lambda *args, **kwargs: None
                task.combat_once = lambda **kwargs: combat_calls.append(kwargs) or True
                task.walk_find_echo = lambda **kwargs: pickup_calls.append(kwargs) or True
                task.wait_combat = lambda **kwargs: next(combat_results)
                task.log_info = lambda *args, **kwargs: None
                task.send_key = lambda *args, **kwargs: None
                task.esc_world_confirm = lambda *args, **kwargs: None

                task.combat_nest(FakeBox('nest'))

                self.assertEqual([10, 1], [call['wait_combat_time'] for call in combat_calls])
                self.assertEqual(2, len(pickup_calls))

    def test_capture_mode_does_not_check_combat_after_pickup(self):
        task = NightmareNestTask.__new__(NightmareNestTask)
        task._capture_mode = True
        task.wait_combat = lambda **kwargs: self.fail('capture mode should leave after obtaining an echo')

        self.assertFalse(task._should_continue_combat_after_pickup())

    def test_unreachable_nest_is_cached_when_travel_does_not_enter_world(self):
        task = NightmareNestTask.__new__(NightmareNestTask)
        task._unreachable_nests = set()
        backs = []
        clicks = []
        wait_timeouts = []
        world_waits = []
        travel = FakeBox('fast_travel_custom')

        task.wait_until = lambda *args, **kwargs: wait_timeouts.append(kwargs['time_out']) or travel
        task.find_one = lambda name, **kwargs: travel if name == travel.name else None
        task.click = lambda box, **kwargs: clicks.append((box, kwargs))
        task.wait_in_team_and_world = lambda *args, **kwargs: world_waits.append(kwargs) or False
        task.back = lambda *args, **kwargs: backs.append(kwargs)
        task.log_info = lambda *args, **kwargs: None

        target = NestTarget(object(), 'go_nightmare:36:0.205')

        self.assertFalse(task._travel_to_nest_or_skip(target))
        self.assertIn(target.cache_key, task._unreachable_nests)
        self.assertEqual([1], wait_timeouts)
        self.assertEqual([(travel, {'after_sleep': 1})], clicks)
        self.assertEqual([], world_waits)
        self.assertEqual([{'after_sleep': 1}], backs)

    def test_travel_waits_up_to_120_seconds_for_loading(self):
        task = NightmareNestTask.__new__(NightmareNestTask)
        task._unreachable_nests = set()
        travel = FakeBox('fast_travel_custom')
        world_waits = []

        task.wait_until = lambda *args, **kwargs: travel
        task.find_one = lambda *args, **kwargs: None
        task.click = lambda *args, **kwargs: None
        task.wait_in_team_and_world = lambda *args, **kwargs: world_waits.append(kwargs) or True

        self.assertTrue(task._travel_to_nest_or_skip(NestTarget(object(), 'go_nest:36:10')))
        self.assertEqual([{'time_out': 120, 'raise_if_not_found': False}], world_waits)

    def test_find_nest_skips_cached_unreachable_row(self):
        task = NightmareNestTask.__new__(NightmareNestTask)
        task.count_re = re.compile(r"(\d{1,2})/(\d{1,2})")
        task.queues = [lambda: None]
        task._unreachable_nests = {'<lambda>:36:10'}
        task.log_info = lambda *args, **kwargs: None
        task.height_of_screen = lambda value: 1000 * value
        task.width_of_screen = lambda value: 2000 * value
        ocr_calls = []

        count_boxes = [
            FakeBox('0/36', y=200),
            FakeBox('0/36', y=300),
        ]

        def ocr(*args, **kwargs):
            ocr_calls.append((args, kwargs))
            return count_boxes

        task.ocr = ocr

        target = task.find_nest()

        self.assertIsInstance(target, NestTarget)
        self.assertIs(target.box, count_boxes[1])
        self.assertEqual('<lambda>:36:15', target.cache_key)
        self.assertEqual(1800, target.box.x)
        self.assertEqual(1, len(ocr_calls))

    def test_cache_key_ignores_small_ocr_position_jitter(self):
        task = NightmareNestTask.__new__(NightmareNestTask)
        task.queues = [lambda: None]
        task.height_of_screen = lambda value: 1000 * value

        first = task._make_nest_cache_key(FakeBox('0/36', y=200), '36')
        shifted = task._make_nest_cache_key(FakeBox('0/36', y=202), '36')

        self.assertEqual(first, shifted)

    def _task_with_nests(self, nests):
        """把 get_nest_to_go 换成一个按 nests 顺序吐目标的桩。

        真实的 get_nest_to_go 每轮都重新 OCR 一次列表，所以同一个没打动的
        巢穴会被反复吐出来——这里照这个语义来。
        """
        task = NightmareNestTask.__new__(NightmareNestTask)
        task._unreachable_nests = set()
        task._attempted_nests = set()
        task.logs = []
        task.log_info = lambda msg, **kwargs: task.logs.append(msg)

        pending = list(nests)

        def get_nest_to_go():
            while pending:
                nest = pending[0]
                key = nest.cache_key if isinstance(nest, NestTarget) else None
                if key in task._unreachable_nests:
                    pending.pop(0)
                    continue
                return nest
            return None

        task.get_nest_to_go = get_nest_to_go
        task._pending = pending
        return task

    def test_nest_without_progress_is_skipped_instead_of_retried_forever(self):
        """打不过的巢穴（游戏弹「挑战失败」）不能无限重进。

        find_nest 只挑「已击败 0/N」的巢穴，所以一局打完计数没涨的话，
        下一轮还会选中同一个，两分钟一轮地空转。
        """
        stuck = NestTarget(FakeBox('0/36', y=300), 'go_nightmare:36:15')
        task = self._task_with_nests([stuck])

        first = task._next_nest_with_progress()
        self.assertIs(first, stuck)                      # 第一次照打

        second = task._next_nest_with_progress()
        self.assertIsNone(second)                        # 第二次不再给同一个
        self.assertIn(stuck.cache_key, task._unreachable_nests)
        self.assertTrue(any('no progress' in log for log in task.logs))

    def test_skipping_a_stuck_nest_moves_on_to_the_next_one(self):
        stuck = NestTarget(FakeBox('0/36', y=300), 'go_nightmare:36:15')
        other = NestTarget(FakeBox('0/48', y=400), 'go_nest:48:20')
        task = self._task_with_nests([stuck, other])

        self.assertIs(task._next_nest_with_progress(), stuck)
        # 第二轮：stuck 没进展 → 拉黑 → 换下一个，而不是原地卡住
        self.assertIs(task._next_nest_with_progress(), other)
        self.assertIn(stuck.cache_key, task._unreachable_nests)

    def test_a_nest_that_made_progress_is_not_blacklisted(self):
        """打完计数涨了，find_nest 就不会再吐同一个 key，正常继续。"""
        first = NestTarget(FakeBox('0/36', y=300), 'go_nightmare:36:15')
        after = NestTarget(FakeBox('0/48', y=400), 'go_nest:48:20')
        task = self._task_with_nests([first])

        self.assertIs(task._next_nest_with_progress(), first)
        task._pending[:] = [after]                       # 计数涨了，换成别的目标
        self.assertIs(task._next_nest_with_progress(), after)
        self.assertEqual(set(), task._unreachable_nests)

    def test_attempt_memory_is_cleared_between_runs(self):
        """上一轮拉黑的巢穴，下一轮（比如第二天）要重新给机会。"""
        task = NightmareNestTask.__new__(NightmareNestTask)
        task._unreachable_nests = {'go_nightmare:36:15'}
        task._attempted_nests = {'go_nightmare:36:15'}

        source = Path('src/task/NightmareNestTask.py').read_text(encoding='utf-8')
        for method in ('def run(self):', 'def run_capture_mode(self):'):
            start = source.index(method)
            body = source[start:start + 600]
            self.assertIn('self._unreachable_nests.clear()', body)
            self.assertIn('self._attempted_nests.clear()', body)



if __name__ == '__main__':
    unittest.main()
