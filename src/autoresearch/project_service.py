from __future__ import annotations

import json
import shutil
from datetime import date
from pathlib import Path

import yaml

from autoresearch.contracts import ProjectCreate, new_id
from autoresearch.storage import RecordStore


class ProjectService:
    RUNTIME_BEGIN = "<!-- AUTORESEARCH:RUNTIME:BEGIN -->"
    RUNTIME_END = "<!-- AUTORESEARCH:RUNTIME:END -->"

    def __init__(self, projects_dir: Path, template_dir: Path, store: RecordStore):
        self.projects_dir = projects_dir.resolve()
        self.template_dir = template_dir.resolve()
        self.store = store
        self.projects_dir.mkdir(parents=True, exist_ok=True)

    def project_path(self, project_id: str) -> Path:
        target = (self.projects_dir / project_id).resolve()
        if not target.is_relative_to(self.projects_dir):
            raise ValueError("project path escaped projects directory")
        return target

    def create(self, request: ProjectCreate, *, owner: str = "user") -> Path:
        target = self.project_path(request.project_id)
        if target.exists():
            raise FileExistsError(f"project already exists: {target}")
        if not self.template_dir.is_dir():
            raise FileNotFoundError(f"project template missing: {self.template_dir}")

        shutil.copytree(self.template_dir, target)
        manifest_path = target / "PROJECT_MANIFEST.yaml"
        manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
        manifest.update(
            {
                "project_id": request.project_id,
                "slug": request.project_id,
                "title": request.title,
                "owner": owner,
                "status": "active",
                "created_at": date.today().isoformat(),
                "langgraph_thread_id": f"{request.project_id}:{new_id('thread')}",
                "database_project_ref": request.project_id,
                "object_store_prefix": f"projects/{request.project_id}",
            }
        )
        manifest["notes"] = [
            "项目由 AutoResearch 从受控模板实例化。",
            "不得在本文件保存 API key、账号令牌或完整敏感个人信息。",
        ]
        manifest_path.write_text(
            yaml.safe_dump(manifest, allow_unicode=True, sort_keys=False),
            encoding="utf-8",
        )

        idea_path = target / "00_intake" / "IDEA.md"
        idea_path.write_text(
            f"# 原始 Idea\n\n{request.idea or '待用户填写并确认。'}\n",
            encoding="utf-8",
        )
        overview_path = target / ".project-to-act" / "PROJECT_OVERVIEW.md"
        overview = overview_path.read_text(encoding="utf-8")
        overview = overview.replace("论文项目总览（模板）", f"论文项目总览：{request.title}")
        overview = overview.replace("待实例化论文项目", request.title)
        overview = overview.replace("PAPER-TEMPLATE", request.project_id)
        overview = overview.replace("模板\n", "G0 输入确认\n")
        overview = overview.replace("未实例化，禁止运行", "已实例化，等待 G0 输入确认")
        overview = overview.replace(
            "这是待复制的论文项目治理模板，不是已经启动的真实项目。复制后必须替换所有占位信息并重新验证。",
            "本目录是已实例化论文项目；研究结论仍必须由证据和门禁确认。",
        )
        overview_path.write_text(overview, encoding="utf-8")

        record = {
            "project_id": request.project_id,
            "title": request.title,
            "idea": request.idea,
            "path": str(target),
            "status": "active",
        }
        self.store.put(
            "project",
            request.project_id,
            record,
            project_id=request.project_id,
            partition="projects",
        )
        self.store.append_event(
            "project.created", record, project_id=request.project_id, actor=owner
        )
        return target

    def get(self, project_id: str) -> dict | None:
        return self.store.get("project", project_id)

    def sync_run_projection(self, run_record: dict) -> None:
        project_id = run_record["project_id"]
        project_dir = self.project_path(project_id)
        if not project_dir.is_dir():
            raise FileNotFoundError(project_dir)
        state = run_record["state"]

        manifest_path = project_dir / "PROJECT_MANIFEST.yaml"
        manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
        manifest["langgraph_thread_id"] = run_record["run_id"]
        manifest["status"] = state.get("lifecycle_state", run_record["status"])
        manifest_path.write_text(
            yaml.safe_dump(manifest, allow_unicode=True, sort_keys=False),
            encoding="utf-8",
        )

        run_index = project_dir / "state" / "RUN_INDEX.jsonl"
        run_index.parent.mkdir(parents=True, exist_ok=True)
        projection = {
            "run_id": run_record["run_id"],
            "status": run_record["status"],
            "lifecycle_state": state.get("lifecycle_state"),
            "paper_count": len(state.get("paper_ids", [])),
            "reading_card_count": len(state.get("reading_card_ids", [])),
            "manuscript_id": state.get("manuscript_id"),
            "gate_decision_ids": state.get("gate_decision_ids", []),
            "blockers": state.get("blockers", []),
            "interrupts": [
                {"type": item.get("type"), "risk_level": item.get("risk_level")}
                for item in run_record.get("interrupts", [])
            ],
            "updated_at": state.get("updated_at"),
        }
        with run_index.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(projection, ensure_ascii=False, default=str) + "\n")

        progress_path = project_dir / ".project-to-act" / "PROJECT_PROGRESS.md"
        progress = progress_path.read_text(encoding="utf-8")
        runtime_section = "\n".join(
            [
                self.RUNTIME_BEGIN,
                "## AutoResearch 运行投影",
                "",
                f"- 当前 run：{run_record['run_id']}",
                f"- 运行状态：{run_record['status']}",
                f"- 生命周期：{state.get('lifecycle_state')}",
                f"- 论文/阅读卡：{len(state.get('paper_ids', []))}/"
                f"{len(state.get('reading_card_ids', []))}",
                f"- 稿件：{state.get('manuscript_id') or '无'}",
                f"- 阻塞：{'；'.join(state.get('blockers', [])) or '无'}",
                "- 详细索引：state/RUN_INDEX.jsonl",
                self.RUNTIME_END,
            ]
        )
        if self.RUNTIME_BEGIN in progress and self.RUNTIME_END in progress:
            before = progress.split(self.RUNTIME_BEGIN, 1)[0].rstrip()
            after = progress.split(self.RUNTIME_END, 1)[1].lstrip()
            progress = f"{before}\n\n{runtime_section}\n\n{after}"
        else:
            progress = progress.rstrip() + "\n\n" + runtime_section + "\n"
        progress_path.write_text(progress, encoding="utf-8")
