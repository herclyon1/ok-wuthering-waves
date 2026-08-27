import inspect
import unittest

from src.task.DailyTask import DailyTask


class TestDailyTaskRewardOrder(unittest.TestCase):
    """Additional tasks must run before the rewards are claimed.

    The weekly garden is the obvious case: it is an additional task, and
    finishing it leaves rewards on the daily screen. With claiming done
    first, those rewards are never collected - there is no second pass.

    run() cannot be driven without a live game, and the guarantee here is
    purely about ordering, so the assertion is made against the source of
    run() itself.
    """

    def test_additional_tasks_run_before_claiming(self):
        src = inspect.getsource(DailyTask.run)
        self.assertLess(src.index('self.run_additional_tasks()'),
                        src.index('self.claim_daily()'),
                        'run_additional_tasks() must come before claim_daily()')

    def test_claiming_is_still_last(self):
        src = inspect.getsource(DailyTask.run)
        for name in ('self.claim_daily()', 'self.claim_mail()',
                     'self.claim_battle_pass()'):
            self.assertLess(src.index('self.run_additional_tasks()'),
                            src.index(name), f'{name} must come after')
