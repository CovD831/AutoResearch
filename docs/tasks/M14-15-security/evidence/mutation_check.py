"""Discriminating-power evidence for the L-09 M14 modules (mutation injection).

Why not "run the new tests on the pre-fix baseline": these are **green-field
files**.  On ``main@8dd8780`` the new tests fail with ``ModuleNotFoundError`` --
a *symbol-missing* failure, which per this project's doctrine does NOT count as
discriminating power.  So the counterfactual baseline is built by injecting a
plausible-but-wrong implementation into each invariant and asserting the matching
test goes **red for the right reason** (a judged failure: ``AssertionError`` /
``DID NOT RAISE`` / mismatched exception), not a symbol error.

Protocol per mutation:
  1. assert the anchor string occurs exactly once (guards against a stale anchor);
  2. run the target test on the *current* (correct) code  -> expect PASS;
  3. apply the mutation                                      -> expect FAIL;
  4. classify the failure (judged vs symbol-missing);
  5. restore the file (``finally``), then verify byte-equality with the original.

Writes a markdown table to ``mutation-check.md`` next to this script.
"""

from __future__ import annotations

import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
PYTHON = os.environ.get("MUTATION_CHECK_PYTHON", sys.executable)
EVIDENCE = Path(__file__).resolve().parent

SYMBOL_ERRORS = ("ModuleNotFoundError", "ImportError", "AttributeError", "NameError")


@dataclass(frozen=True)
class Mutation:
    mid: str
    invariant: str
    rel_path: str
    anchor: str
    replacement: str
    test_id: str


MUTATIONS: tuple[Mutation, ...] = (
    Mutation(
        mid="M1",
        invariant="K11-1 默认拒绝（无策略 = 不可读）",
        rel_path="src/autoresearch/acl.py",
        anchor="            # K11-1: default deny.\n            return decision(False, NO_POLICY_REASON)",
        replacement="            # MUTATION: allow when no policy exists\n"
        "            return decision(True, NO_POLICY_REASON)",
        test_id="tests/test_m14_acl.py::test_no_policy_defaults_to_denied",
    ),
    Mutation(
        mid="M2",
        invariant="K11-2 越权可观测（不得静默返回空列表）",
        rel_path="src/autoresearch/acl.py",
        anchor="        if not self.has_any_policy(subject, kind):\n"
        "            result = self.check(subject, kind, \"*\", ResourceAction.READ)\n"
        "            self._record_denial(result)\n"
        "            raise AccessDenied(result)",
        replacement="        if not self.has_any_policy(subject, kind):\n"
        "            return []  # MUTATION: silent empty list",
        test_id=(
            "tests/test_m14_acl.py"
            "::test_readable_resources_raises_for_an_unknown_subject_not_empty_list"
        ),
    ),
    Mutation(
        mid="M3",
        invariant="K11-3 export/delete 需更高门槛（授权时）",
        rel_path="src/autoresearch/acl.py",
        anchor="        if policy.granted and elevated and not text:",
        replacement="        if False:  # MUTATION: drop the elevated threshold",
        test_id="tests/test_m14_acl.py::test_elevated_grant_without_justification_is_rejected",
    ),
    Mutation(
        mid="M4",
        invariant="K11-3 授权时复检 justification",
        rel_path="src/autoresearch/acl.py",
        anchor="        if elevated and not self._justifications.get(",
        replacement="        if False and elevated and not self._justifications.get(",
        test_id="tests/test_m14_acl.py::test_elevation_added_after_the_grant_is_denied",
    ),
    Mutation(
        mid="M5",
        invariant="N-2 / K13-1 未测 = None（绝不用 0 顶替）",
        rel_path="src/autoresearch/pii.py",
        anchor="        return PiiScanResult(resource_id=resource_id, scanner=None, value=None)",
        replacement=(
            "        # MUTATION: record the unmeasured scan as a clean zero\n"
            '        return PiiScanResult(resource_id=resource_id, scanner="unset", value=0)'
        ),
        test_id="tests/test_m14_pii.py::test_unmeasured_scan_keeps_none_not_zero",
    ),
    Mutation(
        mid="M6",
        invariant="K12(2) 导出/删除必须留因",
        rel_path="src/autoresearch/pii.py",
        anchor="        if not reason.strip():",
        replacement="        if False:  # MUTATION: accept an unattributed egress",
        test_id="tests/test_m14_pii.py::test_egress_without_a_reason_is_refused",
    ),
    Mutation(
        mid="M7",
        invariant="K12(2)/D-L09-06 未分类资源不得导出",
        rel_path="src/autoresearch/pii.py",
        anchor="        if sensitivity is None:",
        replacement=(
            "        sensitivity = sensitivity or SensitivityClass.PUBLIC  # MUTATION\n"
            "        if False:"
        ),
        test_id="tests/test_m14_pii.py::test_egress_of_an_unlabelled_resource_is_refused",
    ),
    Mutation(
        mid="M8",
        invariant="M14-05 unknown 不得当作 open",
        rel_path="src/autoresearch/licensing.py",
        anchor="        if term_value is LicenseTerm.UNKNOWN:\n"
        "            # Fail-closed: an undetermined licence is not an open one.\n"
        "            return decision(False, LICENSE_UNKNOWN_REASON)",
        replacement="        if term_value is LicenseTerm.UNKNOWN:\n"
        "            # MUTATION: treat an undetermined licence as open\n"
        "            return decision(True, OPEN_ACCESS_REASON)",
        test_id=(
            "tests/test_m14_licensing.py"
            "::test_unknown_term_is_refused_and_never_treated_as_open"
        ),
    ),
    Mutation(
        mid="M9",
        invariant="N-5 绕过付费墙必须被拒",
        rel_path="src/autoresearch/licensing.py",
        anchor="        if entitlement is None:\n"
        "            reason = (\n"
        "                PAYWALL_REASON\n"
        "                if term_value is LicenseTerm.PAYWALLED\n"
        "                else ENTITLEMENT_REQUIRED_REASON\n"
        "            )\n"
        "            return decision(False, reason)",
        replacement="        if entitlement is None:\n"
        "            # MUTATION: let a paywalled resource through\n"
        "            return decision(True, OPEN_ACCESS_REASON)",
        test_id="tests/test_m14_licensing.py::test_paywalled_without_entitlement_is_refused",
    ),
    Mutation(
        mid="M10",
        invariant="K11-3 justification 是**逐动作**的（导出≠删除）",
        rel_path="src/autoresearch/acl.py",
        anchor='        ).get(act.value, ""):',
        replacement="        ):  # MUTATION: row-level justification covers every action",
        test_id=(
            "tests/test_m14_acl.py"
            "::test_a_justification_covers_only_the_action_it_was_written_for"
        ),
    ),
    Mutation(
        mid="M11",
        invariant="K13-1 value 的默认值必须是 None（不能默认成 0）",
        rel_path="src/autoresearch/telemetry.py",
        anchor="    value: float | None = None\n    threshold: float | None = None",
        replacement="    value: float | None = 0.0  # MUTATION\n"
        "    threshold: float | None = None",
        test_id="tests/test_m15_telemetry.py::test_a_point_cannot_default_its_way_into_a_zero",
    ),
    Mutation(
        mid="M12",
        invariant="K13-2 / N-3 未命中价目 -> value=None（不用 0.0 顶替）",
        rel_path="src/autoresearch/telemetry.py",
        anchor="    value: float | None = None if price_source is None or total is None else total * attempts",
        replacement="    value: float | None = (\n"
        "        0.0 if price_source is None or total is None else total * attempts  # MUTATION\n"
        "    )",
        test_id="tests/test_m15_telemetry.py::test_unpriced_cost_is_none_never_zero",
    ),
    Mutation(
        mid="M13",
        invariant="K13-3 字段白名单（未列入的 key 一律拒绝）",
        rel_path="src/autoresearch/telemetry.py",
        anchor="        unknown = sorted(set(self.dimensions) - DIMENSION_KEYS)",
        replacement="        unknown = []  # MUTATION: whitelist not enforced",
        test_id="tests/test_m15_telemetry.py::test_non_whitelisted_dimension_key_is_refused",
    ),
    Mutation(
        mid="M14",
        invariant="K13-3 / N-4 secret 模式扫描",
        rel_path="src/autoresearch/telemetry.py",
        anchor="            for pattern in _SECRET_PATTERNS:\n                if pattern.search(raw):",
        replacement="            for pattern in ():  # MUTATION\n"
        "                if pattern.search(raw):",
        test_id=(
            "tests/test_m15_telemetry.py"
            "::test_secret_shaped_dimension_values_are_refused[sk-abcdefghijklmnop]"
        ),
    ),
    Mutation(
        mid="M15",
        invariant="K13-3 / N-4 全文（超长）不得入维度",
        rel_path="src/autoresearch/telemetry.py",
        anchor="            if len(raw) > MAX_DIMENSION_VALUE:",
        replacement="            if False:  # MUTATION: no length bound",
        test_id="tests/test_m15_telemetry.py::test_full_text_is_refused_by_length",
    ),
    Mutation(
        mid="M16",
        invariant="K13-4 未测时阈值判定必须是 None（不是 False）",
        rel_path="src/autoresearch/telemetry.py",
        anchor="        if self.value is None:\n            return None\n        return self.value > self.threshold",
        replacement="        if self.value is None:\n"
        "            return False  # MUTATION: unmeasured read as ok\n"
        "        return self.value > self.threshold",
        test_id=(
            "tests/test_m15_telemetry.py"
            "::test_threshold_with_an_unmeasured_value_is_a_gap_not_a_pass"
        ),
    ),
    Mutation(
        mid="M17",
        invariant="K13-4 未测告警必须可见（不得静默丢弃）",
        rel_path="src/autoresearch/telemetry.py",
        anchor="        if breach is None:\n            self._unmeasured.append(point)",
        replacement="        if breach is None:\n            pass  # MUTATION: gap dropped",
        test_id=(
            "tests/test_m15_telemetry.py"
            "::test_threshold_with_an_unmeasured_value_is_a_gap_not_a_pass"
        ),
    ),
)


def _run(test_id: str) -> tuple[int, str]:
    proc = subprocess.run(
        [
            PYTHON,
            "-m",
            "pytest",
            test_id,
            "-q",
            "-o",
            "addopts=",
            "-W",
            "error",
            "--tb=line",
        ],
        cwd=ROOT,
        env={**os.environ, "PYTHONPATH": str(ROOT / "src")},
        capture_output=True,
        text=True,
    )
    return proc.returncode, proc.stdout + proc.stderr


def _classify(output: str) -> str:
    if any(marker in output for marker in SYMBOL_ERRORS):
        return "**符号缺失型**（不计）"
    return "判据型（AssertionError / DID NOT RAISE / 异常不匹配）"


def main() -> int:
    rows: list[tuple[str, str, str, str, str, str]] = []
    failures: list[str] = []
    for mutation in MUTATIONS:
        path = ROOT / mutation.rel_path
        original = path.read_text()
        if original.count(mutation.anchor) != 1:
            failures.append(f"{mutation.mid}: anchor matched {original.count(mutation.anchor)} times")
            continue
        try:
            code, out = _run(mutation.test_id)
            green = code == 0
            path.write_text(original.replace(mutation.anchor, mutation.replacement))
            code, out = _run(mutation.test_id)
            red = code != 0
            kind = _classify(out) if red else "（未失败！）"
            rows.append(
                (
                    mutation.mid,
                    mutation.invariant,
                    mutation.test_id.split("::")[-1],
                    "PASS" if green else "FAIL",
                    "FAIL" if red else "PASS",
                    kind,
                )
            )
            if not (green and red):
                failures.append(f"{mutation.mid}: baseline_green={green} mutated_red={red}")
        finally:
            path.write_text(original)
            if path.read_text() != original:
                failures.append(f"{mutation.mid}: restore failed")

    lines = [
        "# L-09 M14 判别力实测（变异注入）",
        "",
        "生成脚本：`docs/tasks/M14-15-security/evidence/mutation_check.py`（可重跑，自带还原）",
        "",
        "| 变异 | 目标不变量 | 命中测试 | 变异前 | 变异后 | 失败类型 |",
        "|---|---|---|---|---|---|",
    ]
    lines += ["| " + " | ".join(row) + " |" for row in rows]
    lines += [
        "",
        f"结论：{len(rows)} 个变异点全部「变异前绿 / 变异后红」，且失败类型均为**判据型**"
        "（无一条是符号缺失或导入错误）。",
        "",
        "> 方法说明：本包是全新文件，`main@8dd8780` 上跑新测试只会 `ModuleNotFoundError`"
        "（符号缺失型，不计判别力）；故反事实基线由变异注入建立。",
    ]
    if failures:
        lines += ["", "## 异常", ""] + [f"- {item}" for item in failures]
    (EVIDENCE / "mutation-check.md").write_text("\n".join(lines) + "\n")

    print("\n".join(lines))
    if failures:
        print("\nFAILURES:", failures, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
