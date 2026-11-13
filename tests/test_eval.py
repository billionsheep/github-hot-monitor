"""Regression checks for the evaluation protocol, not measured model accuracy."""
import json
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch
from eval.run_eval import (HERE, AuditDB, Settings, LedgerAdapter, BudgetExceeded,
                           full_text_baseline, register, offline, score)

class EvalProtocolTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.db = AuditDB(replace(Settings(), data_dir=Path(self.temp.name)))
        self.cases = json.loads((HERE/'golden_cases.json').read_text())['cases']
        self.fixtures = json.loads((HERE/'fixtures/repositories.json').read_text())

    async def test_full_text_baseline_is_application_evidence(self):
        case = self.cases[0]
        register(self.db, case)
        class Adapter:
            async def complete(_, role, instructions, inputs, allow_tools):
                self.assertFalse(allow_tools)
                self.assertIn('应用已通过相同只读工具获取', instructions)
                self.assertNotIn('六个工具是唯一读取途径', instructions)
                self.assertNotIn('expected_status', json.dumps(inputs))
                self.assertNotIn('evidence_contract', json.dumps(inputs))
                return {'output':[{'type':'message','content':[{'type':'output_text','text':'{"rows":[]}'}]}], 'usage':{}}
        result = await full_text_baseline(case, self.fixtures, self.db, Adapter())
        self.assertEqual(result['grading']['score'], 0)

    async def test_corpus_mutation_fails_offline(self):
        case = self.cases[0]
        path = next(iter(self.fixtures[case['repo']]['files']))
        self.fixtures[case['repo']]['files'][path] += '\ntampered'
        with self.assertRaises(AssertionError):
            await offline(case, self.fixtures, self.db)

    async def test_exhausted_budget_never_sends_request(self):
        manifest = {'requests':0,'max_requests':1,'estimated_usd':0.,'reserved_usd':0.,'max_usd':0.}
        adapter = LedgerAdapter(manifest, Path(self.temp.name)/'manifest.json')
        with patch('eval.run_eval.ready', return_value=True), patch('eval.run_eval.response_request') as send:
            with self.assertRaises(BudgetExceeded):
                await adapter.complete('lead', 'JSON', [{'role':'user','content':'hello'}], False)
            send.assert_not_called()
        self.assertEqual(manifest['requests'], 0)

    def test_correct_label_without_key_evidence_is_not_full_credit(self):
        case = self.cases[0]
        result = score(case, [{'status':case['expected_status'][0], 'citations':[]}], self.db)
        self.assertEqual(result['score'], 1)

    def test_wrong_status_or_empty_report_fails(self):
        case = self.cases[0]
        self.assertEqual(score(case, [], self.db)['score'], 0)
        self.assertEqual(score(case, [{'status':'FAIL', 'citations':[]}], self.db)['score'], 0)
