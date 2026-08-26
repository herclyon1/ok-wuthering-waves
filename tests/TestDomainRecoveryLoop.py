import ast
import unittest
from pathlib import Path


class TestDomainRecoveryLoop(unittest.TestCase):
    def setUp(self):
        module = ast.parse(Path("src/task/DomainTask.py").read_text(encoding="utf-8"))
        class_node = next(
            node for node in module.body
            if isinstance(node, ast.ClassDef) and node.name == "DomainTask"
        )
        self.method_node = next(
            node for node in class_node.body
            if isinstance(node, ast.FunctionDef) and node.name == "farm_domain_with_recovery_loop"
        )
        self.farm_in_domain_node = next(
            node for node in class_node.body
            if isinstance(node, ast.FunctionDef) and node.name == "farm_in_domain"
        )

    def test_method_has_retry_parameter_with_default(self):
        args = self.method_node.args.args
        self.assertEqual(args[-1].arg, "max_recovery_retries")
        self.assertEqual(len(self.method_node.args.defaults), 1)
        default_value = self.method_node.args.defaults[0]
        self.assertIsInstance(default_value, ast.Constant)
        self.assertEqual(default_value.value, 3)

    def test_method_increments_retries(self):
        has_increment = any(
            isinstance(node, ast.AugAssign)
            and isinstance(node.target, ast.Name)
            and node.target.id == "recovery_retries"
            and isinstance(node.op, ast.Add)
            and isinstance(node.value, ast.Constant)
            and node.value.value == 1
            for node in ast.walk(self.method_node)
        )
        self.assertTrue(has_increment)

    def test_method_stops_when_retry_budget_exceeded(self):
        has_retry_guard = any(
            isinstance(node, ast.Compare)
            and isinstance(node.left, ast.Name)
            and node.left.id == "recovery_retries"
            and any(isinstance(op, ast.GtE) for op in node.ops)
            and any(
                isinstance(comp, ast.Name) and comp.id == "max_recovery_retries"
                for comp in node.comparators
            )
            for node in ast.walk(self.method_node)
        )
        self.assertTrue(has_retry_guard)

        has_make_sure_in_world_call = any(
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id == "self"
            and node.func.attr == "make_sure_in_world"
            for node in ast.walk(self.method_node)
        )
        self.assertTrue(has_make_sure_in_world_call)

    def test_loop_unpacks_must_use_from_farm_in_domain(self):
        has_unpack = any(
            isinstance(node, ast.Assign)
            and len(node.targets) == 1
            and isinstance(node.targets[0], ast.Tuple)
            and len(node.targets[0].elts) == 2
            and {elt.id for elt in node.targets[0].elts if isinstance(elt, ast.Name)} == {"finished", "must_use"}
            and isinstance(node.value, ast.Call)
            and isinstance(node.value.func, ast.Attribute)
            and node.value.func.attr == "farm_in_domain"
            for node in ast.walk(self.method_node)
        )
        self.assertTrue(has_unpack)


    def _farm_in_domain_handlers(self):
        return [
            node for node in ast.walk(self.farm_in_domain_node)
            if isinstance(node, ast.ExceptHandler)
        ]

    def test_failed_attempt_is_recoverable_instead_of_aborting_the_task(self):
        """副本没打通不该把整个 DailyTask 带走。

        打不通时不会掉宝箱，walk_to_treasure 会抛 WaitFailedException。
        它必须和死亡一样被当成“这一局没打成”，交给 farm_domain_with_recovery_loop
        重试；否则它会一路穿到 DailyTask.run，后面的领奖和附加任务全被跳过。
        """
        caught = set()
        for handler in self._farm_in_domain_handlers():
            if handler.type is None:
                continue
            names = handler.type.elts if isinstance(handler.type, ast.Tuple) else [handler.type]
            caught.update(n.id for n in names if isinstance(n, ast.Name))
        self.assertIn("WaitFailedException", caught)
        self.assertIn("NotInCombatException", caught)
        self.assertIn("CharDeadException", caught)

    def test_walk_to_treasure_is_inside_the_guarded_block(self):
        """守卫要真的盖住抛异常的那一句，不然加了也白加。"""
        guarded = any(
            any(
                isinstance(call, ast.Call)
                and isinstance(call.func, ast.Attribute)
                and call.func.attr == "walk_to_treasure"
                for stmt in node.body
                for call in ast.walk(stmt)
            )
            and any(
                isinstance(handler.type, ast.Tuple)
                and any(
                    isinstance(n, ast.Name) and n.id == "WaitFailedException"
                    for n in handler.type.elts
                )
                for handler in node.handlers
            )
            for node in ast.walk(self.farm_in_domain_node)
            if isinstance(node, ast.Try)
        )
        self.assertTrue(guarded)

    def test_failed_attempt_returns_not_finished_so_the_loop_retries(self):
        """返回 False 才会进入外层重试；返回 True 会被当成正常结束。"""
        returns = [
            node for handler in self._farm_in_domain_handlers()
            for node in ast.walk(handler)
            if isinstance(node, ast.Return)
        ]
        self.assertTrue(returns)
        for node in returns:
            self.assertIsInstance(node.value, ast.Tuple)
            first = node.value.elts[0]
            self.assertIsInstance(first, ast.Constant)
            self.assertIs(first.value, False)


if __name__ == "__main__":
    unittest.main()
