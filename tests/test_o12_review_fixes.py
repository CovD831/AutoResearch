"""O12 追加复核（成员 A, 2026-09-12）P1-1/P1-2/P1-3/P2-1/P2-2 的判别力测试。

每一条都以「修复前的基线会失败」的方式写：断言的不是「代码长什么样」，而是
「缺陷行为不会发生」。判据型失败（断言落空）计入证据；符号缺失型失败（导入不
到新 API）不计入，故这里尽量只依赖修复前就存在的公开符号。
"""

from __future__ import annotations

import contextlib
import threading

import pytest
from pydantic import SecretStr

from autoresearch.config import Settings
from autoresearch.llm import LLMService, lane_from_settings
from autoresearch.provider_lane import (
    LaneBudgetExceededError,
    LaneBudgetProfile,
    LaneRequest,
    LaneResponseError,
    LaneRunLedger,
    LaneTransport,
    ProviderLaneError,
    Usage,
    build_preset_lane,
    calculate_cost,
    normalize_usage_openai,
    receipt_usage_fields,
)

CUSTOM = Settings(
    llm_provider="workbuddy",
    llm_api_key=SecretStr("sk-test"),
    llm_base_url="https://custom.example.invalid/v1",
    llm_model="deepseek-v4-pro",
)

UNKNOWN_MODEL_SETTINGS = CUSTOM.model_copy(update={"llm_model": "no-such-model-xyz"})


class FakeResponse:
    def __init__(self, data: dict) -> None:
        self.status_code = 200
        self._data = data
        self.text = str(data)

    def json(self) -> dict:
        return self._data


class FakeClient:
    def __init__(self, responses: list) -> None:
        self.responses = list(responses)
        self.calls: list[dict] = []

    def post(self, url, headers=None, json=None):  # noqa: A002
        self.calls.append({"url": url, "headers": headers, "json": json})
        item = self.responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def _payload(text="ok", usage=None):
    body = {
        "id": "chatcmpl-fixture",
        "choices": [{"index": 0, "message": {"role": "assistant", "content": text}}],
    }
    if usage is not None:
        body["usage"] = usage
    return body


def _lane_with_cap(cap: int):
    base = build_preset_lane("deepseek:chat:v1")
    return type(base)(
        **{
            **{
                f.name: getattr(base, f.name)
                for f in base.__dataclass_fields__.values()
                if f.name != "budget_profile"
            },
            "budget_profile": LaneBudgetProfile(max_calls_per_run=cap),
        }
    )


# ---------------------------------------------------------------------------
# P1-1  自定义 provider 路径必须有预算
# ---------------------------------------------------------------------------


def test_custom_provider_lane_has_a_call_cap() -> None:
    """P1-1: 无上限的调用预算不是预算。

    修复前：`lane_from_settings` 走 `LaneBudgetProfile()` → 三档全 None，
    调用次数到 100000 仍 allowed。
    """
    lane = lane_from_settings(CUSTOM)

    assert lane.budget_profile.max_calls_per_run is not None
    assert lane.budget_profile.max_tokens_per_run is not None


def test_custom_provider_lane_matches_the_preset_rule() -> None:
    """P1-1: 两条路径用同一条规则推预算，不是各写一套。"""

    lane = lane_from_settings(CUSTOM)
    preset = build_preset_lane("deepseek:chat:v1")

    assert lane.budget_profile.max_calls_per_run == preset.budget_profile.max_calls_per_run


def test_custom_provider_lane_rejects_past_the_cap() -> None:
    """P1-1 行为面：超过上限时真的拦得住（不是只把字段填上）。"""

    lane = lane_from_settings(CUSTOM)
    cap = lane.budget_profile.max_calls_per_run
    assert cap is not None

    client = FakeClient(
        [FakeResponse(_payload(usage={"prompt_tokens": 1})) for _ in range(cap + 1)]
    )
    ledger = LaneRunLedger()
    transport = LaneTransport(lane, credential="sk-test", client=client, ledger=ledger)

    for _ in range(cap):
        transport.complete(LaneRequest(system="s", user="u"))

    with pytest.raises(LaneBudgetExceededError):
        transport.complete(LaneRequest(system="s", user="u"))
    assert ledger.requests_made == cap


# ---------------------------------------------------------------------------
# P1-2  usage 缺失 ≠ 零用量
# ---------------------------------------------------------------------------


def test_missing_usage_is_not_reported_as_zero_tokens() -> None:
    """P1-2: provider 不给 usage 时，用量是「不知道」而不是 0。

    修复前：`raw.get("usage") or {}` → 全零 Usage，spent_tokens=0。
    """
    lane = build_preset_lane("deepseek:chat:v1")
    client = FakeClient([FakeResponse(_payload(text="hello"))])
    transport = LaneTransport(lane, credential="k", client=client, ledger=LaneRunLedger())

    result = transport.complete(LaneRequest(system="s", user="u"))

    assert result.usage is None, "缺 usage 必须表达为 None，不能伪造 0"


def test_missing_usage_does_not_accumulate_zero_dollars() -> None:
    """P1-2: 未知消耗不得累加成「零美元已花」。"""

    lane = build_preset_lane("deepseek:chat:v1")
    client = FakeClient([FakeResponse(_payload(text="hello"))])
    ledger = LaneRunLedger()
    LaneTransport(lane, credential="k", client=client, ledger=ledger).complete(
        LaneRequest(system="s", user="u")
    )

    assert ledger.spent_tokens == 0
    assert ledger.spent_usd == 0.0


def test_present_usage_still_accumulates_normally() -> None:
    """P1-2 反向：有 usage 时口径不变（修复没有过度收紧）。"""

    lane = build_preset_lane("deepseek:chat:v1")
    client = FakeClient(
        [FakeResponse(_payload(usage={"prompt_tokens": 100, "completion_tokens": 50}))]
    )
    ledger = LaneRunLedger()
    result = LaneTransport(lane, credential="k", client=client, ledger=ledger).complete(
        LaneRequest(system="s", user="u")
    )

    assert result.usage is not None
    assert result.usage.input_tokens == 100
    assert ledger.spent_tokens == 150
    assert ledger.spent_usd > 0


# ---------------------------------------------------------------------------
# P1-3  预算检查与占位必须原子
# ---------------------------------------------------------------------------


def test_ledger_reservation_is_strictly_atomic_under_contention() -> None:
    """P1-3: 高并发下占位总数严格等于 cap，一次都不超发。

    **判别力说明（诚实）**：这条测试在修复前的基线上也会通过 —— 缺陷是
    check 与自增之间的竞态，而那个窗口在 CPython GIL 下窄到无法从外部可靠
    复现（已实测：即使把 ``post`` 用 barrier 拉长也撞不开）。因此它**不计入
    「修复前失败」的判据型证据**，只作为修复后的回归护栏：一旦有人把
    ``reserve_request`` 改回「先查后加」的写法，高压并发会让超发暴露。

    缺陷的确定性复现见 ``test_reserve_request_checks_and_claims_in_one_step``
    与账本 D-O12-15（探针插桩实测基线 ``requests_made=2``）。
    """
    lane = _lane_with_cap(7)

    class InstantClient:
        def post(self, url, headers=None, json=None):  # noqa: A002
            return FakeResponse(_payload(usage={"prompt_tokens": 1}))

    total_threads = 64
    ledger = LaneRunLedger()
    start = threading.Barrier(total_threads)
    granted: list[int] = []
    lock = threading.Lock()

    def worker() -> None:
        transport = LaneTransport(lane, credential="k", client=InstantClient(), ledger=ledger)
        start.wait()
        try:
            transport.complete(LaneRequest(system="s", user="u"))
            with lock:
                granted.append(1)
        except ProviderLaneError:
            pass

    threads = [threading.Thread(target=worker) for _ in range(total_threads)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert ledger.requests_made == 7, f"cap=7 但发出了 {ledger.requests_made} 次"
    assert len(granted) == 7


def test_reserve_request_checks_and_claims_in_one_step() -> None:
    """P1-3: 占位 API 自身必须「判定 + 计数」一步完成，且不超发。

    这是缺陷的确定性判据：旧的写法把 ``check_call_budget`` 与 ``+= 1`` 分成
    两处调用，任何调用方都可以在两者之间插入别的动作。``reserve_request``
    把两步收进一个方法，调用方**没有机会**把它们分开。
    """
    lane = _lane_with_cap(1)
    ledger = LaneRunLedger()

    assert ledger.reserve_request(lane) == 1
    with pytest.raises(LaneBudgetExceededError):
        ledger.reserve_request(lane)
    assert ledger.requests_made == 1, "被拒的占位不得消耗配额"


def test_reserve_request_is_atomic_against_the_old_split_pattern() -> None:
    """P1-3 的等价判据：模拟「先查后加」，两次占位在 cap=1 下必须只成功一次。

    修复前 ``complete()`` 等价于下面这段（check 与 inc 分离）。这里把两者
    都放在显式交错点上执行，使竞态成为确定性事件。
    """
    lane = _lane_with_cap(1)
    ledger = LaneRunLedger()

    checked: list[int] = []
    enter = threading.Barrier(2, timeout=5)

    def split_pattern() -> None:
        # 旧写法：先查（读计数、判定）
        check_budget_only(lane, ledger)
        checked.append(1)
        enter.wait()  # 强制在此处交错，等价于旧实现的竞态窗口
        # 再加
        ledger.requests_made += 1

    threads = [threading.Thread(target=split_pattern) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    # 旧写法在交错下必然超发到 2 —— 这正是缺陷。
    assert ledger.requests_made == 2, "本测试自身前提失效：交错没有生效"

    # 而修复后的写法在同一交错下严格只放行 1 次。
    ledger2 = LaneRunLedger()
    ok = 0
    for _ in range(2):
        try:
            ledger2.reserve_request(lane)
            ok += 1
        except LaneBudgetExceededError:
            pass
    assert ok == 1 and ledger2.requests_made == 1


def check_budget_only(lane, ledger) -> None:
    """旧实现的「只查不占」半步，用于在测试里复建竞态。"""

    from autoresearch.provider_lane import check_call_budget

    check_call_budget(lane, calls_used=ledger.requests_made)


def test_concurrent_dispatch_cannot_exceed_the_call_cap() -> None:
    """P1-3: 上限=1 时两个并发线程只能有一个真正发出请求。

    修复前：check 读计数、下一行才自增，两线程都读到 0、都通过，实际请求数=2。

    竞态窗口在 GIL 下自然发生概率很低，所以这里**显式放大它**：让 client 的
    第一次 ``post`` 阻塞在 barrier 上，把两个线程推进「已通过 check、尚未
    自增」的窗口。若不插桩，这条测试在缺陷代码上也会通过（无判别力）。
    """
    lane = _lane_with_cap(1)
    entered = threading.Barrier(2, timeout=5)

    class RendezvousClient:
        """第一次调用与另一端会合，迫出 check/自增之间的窗口。"""

        def __init__(self) -> None:
            self._first = True
            self._lock = threading.Lock()

        def post(self, url, headers=None, json=None):  # noqa: A002
            with self._lock:
                first = self._first
                self._first = False
            if first:
                with contextlib.suppress(threading.BrokenBarrierError):
                    entered.wait()
            return FakeResponse(_payload(usage={"prompt_tokens": 1}))

    ledger = LaneRunLedger()
    outcomes: list[str] = []

    def worker(idx: int) -> None:
        transport = LaneTransport(
            lane, credential="k", client=RendezvousClient(), ledger=ledger
        )
        try:
            transport.complete(LaneRequest(system="s", user="u"))
            outcomes.append(f"t{idx}:completed")
        except ProviderLaneError:
            outcomes.append(f"t{idx}:rejected")

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert ledger.requests_made == 1, (
        f"并发突破上限：{ledger.requests_made} 次请求，cap=1，outcomes={sorted(outcomes)}"
    )


def test_sequential_dispatch_still_uses_the_full_cap() -> None:
    """P1-3 反向：串行场景 cap 仍然可用满（原子化没有把预算收窄）。"""

    lane = _lane_with_cap(2)
    client = FakeClient([FakeResponse(_payload(usage={"prompt_tokens": 1})) for _ in range(3)])
    ledger = LaneRunLedger()
    transport = LaneTransport(lane, credential="k", client=client, ledger=ledger)

    transport.complete(LaneRequest(system="s", user="u"))
    transport.complete(LaneRequest(system="s", user="u"))
    with pytest.raises(LaneBudgetExceededError):
        transport.complete(LaneRequest(system="s", user="u"))

    assert ledger.requests_made == 2


# ---------------------------------------------------------------------------
# P2-1  未计价 ≠ 零成本
# ---------------------------------------------------------------------------


def test_unknown_model_is_unpriced_not_zero_rated() -> None:
    """P2-1: catalog 无条目的模型是 None，不是零价目表。

    修复前：`ModelCost(input=0.0, output=0.0)` → receipt 里 cost total=0.0。
    """
    lane = lane_from_settings(UNKNOWN_MODEL_SETTINGS)

    assert lane.cost is None
    assert lane.price_source is None


def test_unpriced_call_reports_no_cost_rather_than_zero() -> None:
    """P2-1 行为面：unpriced lane 的 receipt 不能写 $0.00。"""

    lane = lane_from_settings(UNKNOWN_MODEL_SETTINGS)
    client = FakeClient(
        [FakeResponse(_payload(usage={"prompt_tokens": 1500, "completion_tokens": 200}))]
    )
    result = LaneTransport(
        lane, credential="sk-test", client=client, ledger=LaneRunLedger()
    ).complete(LaneRequest(system="s", user="u"))

    assert result.usage is not None and result.usage.input_tokens == 1500
    assert result.usage_cost is None

    fields = receipt_usage_fields(result, price_source=lane.price_source)
    assert fields["cost"] is None, "未计价必须写 None，不能写零值块"
    assert fields["tokens"]["input"] == 1500


def test_receipt_carries_none_tokens_when_usage_is_missing() -> None:
    """P1-2 与 P2-1 的 receipt 面：两个块都能是 None。"""

    lane = build_preset_lane("deepseek:chat:v1")
    client = FakeClient([FakeResponse(_payload(text="hello"))])
    result = LaneTransport(lane, credential="k", client=client, ledger=LaneRunLedger()).complete(
        LaneRequest(system="s", user="u")
    )

    fields = receipt_usage_fields(result)

    assert fields["tokens"] is None
    assert fields["cost"] is None


# ---------------------------------------------------------------------------
# P2-2  content:null 不是完成
# ---------------------------------------------------------------------------


def test_null_content_without_tool_calls_is_rejected() -> None:
    """P2-2: 没有内容也没有 tool_calls 的响应不是完成态。"""

    lane = build_preset_lane("deepseek:chat:v1")
    client = FakeClient([FakeResponse(_payload(text=None))])
    transport = LaneTransport(lane, credential="k", client=client, ledger=LaneRunLedger())

    with pytest.raises(LaneResponseError):
        transport.complete(LaneRequest(system="s", user="u"))


def test_blank_content_is_rejected() -> None:
    """P2-2: 全空白内容同样不是结果。"""

    lane = build_preset_lane("deepseek:chat:v1")
    client = FakeClient([FakeResponse(_payload(text="   \n  "))])
    transport = LaneTransport(lane, credential="k", client=client, ledger=LaneRunLedger())

    with pytest.raises(LaneResponseError):
        transport.complete(LaneRequest(system="s", user="u"))


def test_null_content_with_tool_calls_is_allowed() -> None:
    """P2-2 反向：tool_calls 响应合法地不带 content，不能误拦。"""

    lane = build_preset_lane("deepseek:chat:v1")
    body = _payload(text=None)
    body["choices"][0]["message"]["tool_calls"] = [
        {"id": "call_1", "type": "function", "function": {"name": "f", "arguments": "{}"}}
    ]
    client = FakeClient([FakeResponse(body)])

    result = LaneTransport(lane, credential="k", client=client, ledger=LaneRunLedger()).complete(
        LaneRequest(system="s", user="u")
    )

    assert result.text == ""


def test_normal_content_still_passes() -> None:
    """P2-2 反向：正常文本响应不受校验影响。"""

    lane = build_preset_lane("deepseek:chat:v1")
    client = FakeClient([FakeResponse(_payload(text="a real answer"))])

    result = LaneTransport(lane, credential="k", client=client, ledger=LaneRunLedger()).complete(
        LaneRequest(system="s", user="u")
    )

    assert result.text == "a real answer"


# ---------------------------------------------------------------------------
# 一致性不变量：cost 与 price_source 是同一条事实的两个视图
# ---------------------------------------------------------------------------


def test_lane_identity_refuses_cost_without_price_source() -> None:
    """P2-1 的守护：不许出现「有价目表」和「无来源」并存的半价状态。"""

    from dataclasses import replace

    from autoresearch.provider_lane import ModelCost

    lane = lane_from_settings(UNKNOWN_MODEL_SETTINGS)
    with pytest.raises(ProviderLaneError):
        replace(lane, cost=ModelCost(input=1.0, output=1.0))


# ---------------------------------------------------------------------------
# 边界：响应形状与账本可复制性（owner 对抗性自查发现）
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "content",
    ["", "   \n ", None, False, 0, [{"type": "text", "text": "hi"}]],
    ids=["empty", "blank", "none", "false", "zero", "multimodal-list"],
)
def test_content_shapes_are_all_rejected_without_tool_calls(content) -> None:
    """任何非「非空字符串」的 content，在没有 tool_calls 时都不是完成。"""

    lane = build_preset_lane("deepseek:chat:v1")
    client = FakeClient([FakeResponse(_payload(text=content))])
    transport = LaneTransport(lane, credential="k", client=client, ledger=LaneRunLedger())

    with pytest.raises(LaneResponseError):
        transport.complete(LaneRequest(system="s", user="u"))


def test_ledger_survives_deepcopy_despite_holding_a_lock() -> None:
    """账本持锁也必须可复制。

    owner 自查发现：`_lock` 是实例属性，`copy.deepcopy` 会走进它并以
    `cannot pickle '_thread.lock' object` 失败 —— 报错既不提 ledger 也不提原因。
    当前无调用方 deepcopy，但这是留给未来的地雷。
    """
    import copy

    ledger = LaneRunLedger()
    ledger.requests_made = 5
    ledger.spent_usd = 1.5

    clone = copy.deepcopy(ledger)

    assert clone.requests_made == 5
    assert clone.spent_usd == 1.5
    assert clone._lock is not ledger._lock, "副本必须换一把新锁，否则独立 run 会互相串行"
    clone.reserve_request(build_preset_lane("deepseek:chat:v1"))
    assert ledger.requests_made == 5, "副本写入不得影响原件"


def test_llm_service_passes_usage_through_as_none_when_absent() -> None:
    """P1-2 的 facade 面：`LLMResult.raw['usage']` 不能是空 dict。

    空 dict 读起来像「报了 usage 但内容为空」，与「没报」是两回事。
    """

    class StubTransport:
        @staticmethod
        def complete(_request):
            from autoresearch.provider_lane import LaneResult

            return LaneResult(
                text="hi",
                lane_id="deepseek:chat:v1",
                model="deepseek-v4-flash",
                usage=None,
                usage_cost=None,
                raw={"id": "x", "usage": None},
            )

    service = LLMService(
        Settings(
            llm_provider="deepseek",
            llm_api_key=SecretStr("sk-test"),
            llm_base_url="https://api.deepseek.com",
            llm_model="deepseek-v4-flash",
        )
    )
    service._transport = StubTransport()  # type: ignore[assignment]

    result = service.complete(system="s", user="u")

    assert result is not None
    assert result.raw["usage"] is None
    assert result.raw["tokens"] is None
    assert result.raw["cost"] is None


def test_usage_normalisation_still_works_for_valid_input() -> None:
    """回归：normalize_usage_openai 的既有语义未被本次修复改动。"""

    usage = normalize_usage_openai({"prompt_tokens": 100, "completion_tokens": 20})
    assert usage == Usage(input_tokens=100, output_tokens=20)
    cost = build_preset_lane("deepseek:chat:v1").cost
    assert cost is not None
    assert calculate_cost(usage, cost).total > 0
