"""One durable USD ceiling shared by every v3 evaluation and recording run."""
import asyncio
from contextlib import contextmanager
from datetime import datetime, timezone
import fcntl
import hashlib
import json
from pathlib import Path
import re
import time
import uuid

from evidence.agent import configuration, ready, response_request
from evidence.agent_harness import BudgetExceeded, DefiniteModelError, ResponsesAdapter, make_payload

PRICE_SOURCE = 'https://developers.openai.com/api/docs/models/gpt-6.1-sol'
# Conservative: charge every input token at the 30m cache-write rate; no cache discount.
INPUT_RATE, OUTPUT_RATE = 2.50 / 1_000_000, 10.0 / 1_000_000
DEFAULT_PATH = Path(__file__).resolve().parents[1] / '.evidence-data/v3-budget.json'


def now():
    return datetime.now(timezone.utc).isoformat()


@contextmanager
def locked_ledger(path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.with_suffix('.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        data = json.loads(path.read_text())
        yield data
        temp = path.with_suffix('.tmp')
        temp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n')
        temp.replace(path)


def initialize(path=DEFAULT_PATH):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    # Exclusive creation prevents accidental budget resets when a run is restarted.
    try:
        with path.open('x') as f:
            json.dump({'version': 1, 'created_at': now(), 'model': 'gpt-6.1-sol', 'effort': 'low',
                       'service_tier': 'default', 'max_usd': 5.0, 'price_source': PRICE_SOURCE,
                       'price_checked_at': '2026-11-13', 'input_usd_per_million': 2.5,
                       'output_usd_per_million': 10.0, 'pricing_basis': 'all input at 30m cache-write rate; no cache discount',
                       'estimated_usd': 0.0, 'reserved_usd': 0.0, 'calls': []}, f, ensure_ascii=False, indent=2)
    except FileExistsError:
        # Reuse the entire prior ledger, including unknown requests.
        return json.loads(path.read_text())
    return json.loads(path.read_text())


class V3BudgetAdapter(ResponsesAdapter):
    def __init__(self, label, path=DEFAULT_PATH):
        self.label, self.path, self.config = label, Path(path), configuration()
        self.v3_tools = True
        initialize(self.path)

    async def complete(self, role, instructions, inputs, allow_tools):
        if not ready(self.config):
            raise DefiniteModelError('本机模型配置不可用。')
        if (self.config['model'], self.config['effort']) != ('gpt-6.1-sol', 'low'):
            raise DefiniteModelError('v3 评测模型必须为 gpt-6.1-sol / low。')
        payload = make_payload(self.config['model'], self.config['effort'], role, instructions, inputs, allow_tools, v3_tools=True)
        payload['service_tier'] = 'default'
        raw = json.dumps(payload, ensure_ascii=False).encode()
        if len(raw) > 24000:
            raise BudgetExceeded('评测请求超过 24000 bytes 上限。')
        reserve = (len(raw) + 512) * INPUT_RATE + 2048 * OUTPUT_RATE
        call_id = uuid.uuid4().hex
        with locked_ledger(self.path) as ledger:
            if ledger['estimated_usd'] + ledger['reserved_usd'] + reserve > min(5.0, ledger['max_usd']):
                raise BudgetExceeded('v3 全局 5 美元预算不足；停止追加调用。')
            ledger['reserved_usd'] += reserve
            ledger['calls'].append({'id': call_id, 'label': self.label, 'role': role, 'started_at': now(),
                                    'status': 'reserved', 'reserved_usd': reserve, 'request_bytes': len(raw),
                                    'request_sha256': hashlib.sha256(raw).hexdigest()})
        started = time.monotonic()
        try:
            response = await asyncio.to_thread(response_request, self.config, payload)
        except Exception as exc:
            definite = bool(re.search(r'HTTP 4[0-9]{2}', str(exc)))
            with locked_ledger(self.path) as ledger:
                entry = next(c for c in ledger['calls'] if c['id'] == call_id)
                entry.update(status='rejected' if definite else 'unknown', elapsed_ms=round((time.monotonic()-started)*1000))
                if definite:
                    ledger['reserved_usd'] -= reserve
                    entry['reserved_usd'] = 0.0
            if definite:
                raise DefiniteModelError(str(exc)) from None
            raise
        usage = response.get('usage', {})
        valid_usage = all(isinstance(usage.get(k), int) and usage[k] >= 0 for k in ('input_tokens', 'output_tokens'))
        with locked_ledger(self.path) as ledger:
            entry = next(c for c in ledger['calls'] if c['id'] == call_id)
            entry.update(status='completed' if valid_usage else 'unknown_usage', elapsed_ms=round((time.monotonic()-started)*1000))
            if valid_usage:
                cost = usage['input_tokens'] * INPUT_RATE + usage['output_tokens'] * OUTPUT_RATE
                ledger['reserved_usd'] -= reserve
                ledger['estimated_usd'] += cost
                entry.update(reserved_usd=0.0, estimated_usd=cost, usage=usage)
        return response
