# L-08 M13 L3 骨架（UI 四面板）

> **层级**：L3 骨架 —— **开工者必须把它补全成完整 L3 后再写代码**
> **上游权威**：R-007 `04-l2-contracts.md` **K14**（`PanelProjection`）
> **原表**：M13-04～07（UI 四面板）
> **base_ref**：`main@8dd8780`（**实测 537 passed / 2 skipped / 0 failed**，本 worktree 自测）
> **排他文件**：`web/`（新建）+ `web_api.py`（如需 BFF 层）

---

## 0. 先澄清一件容易搞错的事（**实测**）

**没有产品级 UI。** 但有一批**容易混淆的 HTML**：

| 文件 | 是什么 | 是 UI 吗 |
|---|---|---|
| `docs/rearchitecture/R005-s1-closure-design/architecture-eli5*.html`（3 个） | **架构说明文档的 HTML 版** | ❌ 不是 |
| `docs/archive/eli5.html` | 归档的架构图 | ❌ 不是 |
| `*/diagram/architecture.svg` | 架构示意图 | ❌ 不是 |

→ **M13-04～07 确实未做。** 但**地基很完整**：

**已有 API 面（22 个端点，可直接给 UI 用）**：`GET /health`、`POST /projects`、`GET /projects/{id}`、
`POST /runs`、`GET /runs/{id}`、`POST /runs/{id}/resume`、`POST /evidence`、
`GET /projects/{id}/evidence`、`POST /evidence/{id}/invalidate`、`POST /papers/{id}/questions`、
`POST /manuscripts/{id}/revisions`、`GET /projects/{id}/work-packages`、`POST /knowledge/pages`、
`POST /knowledge/edges`、`GET /knowledge/search`、`POST /profiles`、`GET /profiles/{user_id}`、
`POST /experiences`、`POST /experiences/{id}/promote`、`POST /projects/{id}/experiences/settle`、
`POST /evolution/proposals`、`POST /evolution/proposals/{id}/review`、`GET /projects/{id}/audit-events`

**已有 CLI**：`autoresearch serve`（本地 FastAPI，`127.0.0.1:8010`，默认不对外）
→ **UI 只需要消费这 22 个端点。**

> ⚠️ **开工第一步必须实测这 22 个端点的真实签名与返回形状**（不要照抄本骨架的清单）。
> 命令：读 `src/autoresearch/api.py` 的路由定义 + 实跑 `autoresearch serve` 逐个 `curl`。

---

## 1. 四面板与原表要求

| 子任务 | 面板 | 依赖端点 |
|---|---|---|
| **M13-04** | 研究项目面板：阶段、Gate、证据覆盖、handoff、任务、阻塞 | `GET /projects/{id}` `GET /runs/{id}` |
| **M13-05** | 证据和审核面板：按 claim/action/run 看 evidence、Gate、审查意见、回退入口 | `GET /projects/{id}/evidence` `GET /projects/{id}/audit-events` |
| **M13-06** | 项目文件夹浏览与导出：论文库/经验库/知识库/稿件/产物/manifest 按 ACL 导出 | 需 **L-09 的 ACL** |
| **M13-07** | 人工审批和打回交互：H3 审批显示范围/风险/证据；确认/拒绝/打回写审计 | `POST /evidence/{id}/invalidate` 等 |

---

## 2. 开工方法：**`ui-skeleton-first`**（**强制，不得跳步**）

> **本项目已验证的方法**：先出「喂真实数据的静态骨架」，再用无头浏览器截图自查，
> **再**写交互。不要先写交互。

```
第 1 步（必须第一个做）：
  跑 autoresearch serve → 用 GET 端点拉真实数据 → 出静态 HTML 骨架
  → 无头浏览器截图 → 人工看信息层级
  价值：先验证「数据长什么样、页面该有什么」，再写交互

第 2 步：补交互（M13-07 的审批流）
第 3 步：导出（M13-06，等 L-09 的 ACL）
```

**判据**：**没有截图的骨架不算完成第 1 步。** 截图是交付物之一。

---

## 3. 必须落地的契约：K14 `PanelProjection`

**字段**：`panel_id`（`project`|`evidence`|`files`|`approval`）/ `sections`（`list[PanelSection]`）/ **`verification_state`（`verified`|`unverified`|`blocked`，每个 section 必须标）**

**`PanelSection`**：`title` / `refs`（引用 ID）/ `verified`（bool）/ `unknown_reason`（`str | None`）

| # | 不变量 | 可校验 |
|---|---|---|
| **K14-1** | **不得展示虚假完成** —— 每个 section 必须带 `verification_state` | ✅ 类型必填 |
| K14-2 | **`refs` 是引用**，面板不复制内容 | ✅ |
| K14-3 | 未验证项必须显式标注（`unverified` + `unknown_reason`） | ✅ |
| K14-4 | **「展示是否真实」** | ❌ **架构意图**（L1 §4.2 **A5**） |

> 🔴 **K14-1 + L1 §4.2 A5「UI 不展示虚假完成」是本包的灵魂。**
> 原表 M13-04 明文要求：**面板不得把未完成写成完成**。
> → 面板上**任何**状态显示都必须能追到一个 `refs` 或一个显式 `unknown_reason`。
> **禁止**用「灰色」「暂无」这类无法区分的 UI 去掩盖 `unverified` 与 `blocked` 的差别。

---

## 4. 技术约束（**老板偏好：零成本、最少外部依赖**）

- **不要引入前端框架。** 建议**原生 HTML + 少量 JS**，或纯服务端渲染。
- 22 个端点的**只读展示不需要 React**。
- **不改后端**：R-007 §2 明文「22 个 API 端点已够用」。若确实需要 BFF，
  新建 `web_api.py`，**不改 `src/autoresearch/` 既有模块**。

---

## 5. 负例（**开工者补全**）

| # | 负例 | 断言什么 |
|---|---|---|
| N-1 | 某 section 数据缺失 | 标 `unverified` + `unknown_reason` 非空（**不是留白**） |
| N-2 | 某 section 处于阻塞 | 标 `blocked`（**与 `unverified` 可区分**） |
| N-3 | 面板 refs | 全部是**引用 ID**，面板内**不含正文副本** |

---

## 6. Deliberate non-goals

- **不改后端**（`src/autoresearch/` 只读消费 API）。
- **不做** M13-06 的 ACL 导出逻辑（等 L-09）。
- **不引入**前端框架 / 构建工具链。

---

## 7. 判别力 / 验收 / 偏离

```bash
# Python 面无回归（本包主要改前端，但不得破坏既有测试）
PYTHONPATH=src python -m pytest -q -o addopts="" -W error    # 基线 537 passed 不得下降
ruff check src tests
node .ai-team/check.mjs --base main
```

**截图自查**：第 1 步的骨架截图必须落盘为交付物（`docs/tasks/M13-ui/tasks/screenshots/`）。
