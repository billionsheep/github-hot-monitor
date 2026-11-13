import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from eval.v3_budget import initialize, V3BudgetAdapter, BudgetExceeded, DefiniteModelError


class BudgetTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'ledger.json'
        with patch('eval.v3_budget.configuration', return_value={'model': 'gpt-6.1-sol', 'effort': 'low'}):
            self.adapter = V3BudgetAdapter('test', self.path)

    def data(self):
        return json.loads(self.path.read_text())

    async def invoke(self, result=None, error=None):
        with patch('eval.v3_budget.ready', return_value=True), patch('eval.v3_budget.response_request', return_value=result, side_effect=error):
            return await self.adapter.complete('sub', 'JSON', [], False)

    async def test_success_accounts_actual_usage_and_reuses_ledger(self):
        await self.invoke({'usage': {'input_tokens': 1000, 'output_tokens': 20}})
        data = initialize(self.path)
        self.assertEqual(len(data['calls']), 1)
        self.assertAlmostEqual(data['estimated_usd'], .0027)
        self.assertAlmostEqual(data['reserved_usd'], 0)

    async def test_timeout_keeps_reservation_and_definite_rejection_releases(self):
        with self.assertRaises(RuntimeError):
            await self.invoke(error=RuntimeError('timeout'))
        held = self.data()['reserved_usd']
        self.assertGreater(held, 0)
        with self.assertRaises(DefiniteModelError):
            await self.invoke(error=RuntimeError('HTTP 429'))
        self.assertAlmostEqual(self.data()['reserved_usd'], held)
        self.assertEqual([c['status'] for c in self.data()['calls']], ['unknown', 'rejected'])

    async def test_budget_blocks_before_network(self):
        data = self.data(); data['estimated_usd'] = 4.999
        self.path.write_text(json.dumps(data))
        with patch('eval.v3_budget.ready', return_value=True), patch('eval.v3_budget.response_request') as request:
            with self.assertRaises(BudgetExceeded):
                await self.adapter.complete('sub', 'JSON', [], False)
            request.assert_not_called()
        self.assertEqual(self.data()['calls'], [])

    async def test_missing_usage_keeps_full_reservation(self):
        await self.invoke({})
        self.assertGreater(self.data()['reserved_usd'], 0)
        self.assertEqual(self.data()['calls'][0]['status'], 'unknown_usage')
