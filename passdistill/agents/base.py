from __future__ import annotations

import json
import os
import time
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from passdistill.util import ensure_dir, write_json


class AgentBackend(Protocol):
    def complete_json(self, system: str, user: str, *, schema_hint: str, out_dir: Path) -> Any:
        ...


def _load_local_env(path: Path | None = None) -> dict[str, str]:
    env_path = path or (Path.cwd() / ".passdistill.env")
    if not env_path.exists():
        return {}
    values: dict[str, str] = {}
    for raw in env_path.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key:
            values[key] = value
    return values


def _env_value(*names: str) -> str | None:
    local = _load_local_env()
    for name in names:
        if os.environ.get(name):
            return os.environ[name]
        if local.get(name):
            return local[name]
    return None


def extract_json(text: str) -> Any:
    text = strip_markdown_fence(text)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start = min([pos for pos in (text.find("{"), text.find("[")) if pos >= 0], default=-1)
        end = max(text.rfind("}"), text.rfind("]"))
        if start >= 0 and end >= start:
            return json.loads(text[start : end + 1])
        raise


def strip_markdown_fence(text: str) -> str:
    stripped = text.strip()
    if not stripped.startswith("```"):
        return stripped
    lines = stripped.splitlines()
    if lines and lines[0].strip().startswith("```"):
        lines = lines[1:]
    if lines and lines[-1].strip() == "```":
        lines = lines[:-1]
    return "\n".join(lines).strip()


def _extract_first_c_block(text: str) -> str:
    marker = "```c"
    start = text.find(marker)
    if start < 0:
        return ""
    start = text.find("\n", start)
    if start < 0:
        return ""
    end = text.find("```", start + 1)
    return text[start + 1 : end].strip() if end >= 0 else text[start + 1 :].strip()


def _mock_payload(schema_hint: str, user: str = "") -> Any:
    if "source_oracle" in schema_hint:
        source_patch = _extract_first_c_block(user)
        return {
            "directions": [
                {
                    "direction_id": "mock_direction",
                    "summary": "mock no-op teacher direction",
                    "optimization_idea": "preserve the kernel while exercising the Source Oracle schema",
                    "expected_performance_reason": "mock backend does not predict performance",
                    "possible_compiler_mechanisms": ["loop-vectorize"],
                    "source_patch": source_patch,
                }
            ]
        }
    if "direction_distiller" in schema_hint:
        return {
            "direction_id": "mock_direction",
            "optimization_intent": "mock distillation placeholder",
            "teacher_transformations": [],
            "observed_compiler_effects": [],
            "search_guidance": {
                "candidate_passes": ["loop-vectorize"],
                "candidate_parameters": [],
                "ordering_hypotheses": [],
                "prerequisite_transformations": [],
                "alternative_realizations": [],
            },
            "target_description": "mock kernel region",
            "summary": "mock direction for planner testing",
        }
    if "recovery_planner" in schema_hint:
        feedback_mode = '"mode": "feedback"' in user or "feedback" in user.lower()
        if feedback_mode:
            return {
                "round_summary": "mock feedback round refines the promoted parent and keeps one baseline branch",
                "candidates": [
                    {
                        "candidate_id": "C1",
                        "parent_id": "CURRENT_PROMOTED_BEST",
                        "hypothesis": "refine the promoted parent with an extra scalar cleanup pass",
                        "edits": [
                            {
                                "type": "insert_fragment",
                                "target": {"parent_manager": "function", "anchor": "loop-vectorize#1", "position": "after"},
                                "fragment": [{"kind": "pass", "name": "instcombine"}],
                            }
                        ],
                        "opt_options": [],
                    },
                    {
                        "candidate_id": "C2",
                        "parent_id": "SEARCH_BASELINE",
                        "hypothesis": "branch from the baseline with a legal loop transform fragment",
                        "edits": [
                            {
                                "type": "replace_region",
                                "target": {
                                    "parent_manager": "function",
                                    "start_anchor": "loop-distribute#1",
                                    "end_anchor": "loop-vectorize#1",
                                },
                                "replacement": [
                                    {"kind": "pass", "name": "loop-distribute"},
                                    {
                                        "kind": "manager",
                                        "manager": "loop",
                                        "passes": [{"kind": "pass", "name": "loop-interchange"}],
                                    },
                                    {"kind": "pass", "name": "loop-vectorize"},
                                ],
                            }
                        ],
                        "opt_options": [],
                    },
                ],
            }
        return {
            "round_summary": "mock initial planner proposes nested catalog-guided candidates",
            "candidates": [
                {
                    "candidate_id": "C1",
                    "parent_id": "SEARCH_BASELINE",
                    "hypothesis": "test a legal loop interchange before vectorization",
                    "edits": [
                        {
                            "type": "replace_region",
                            "target": {
                                "parent_manager": "function",
                                "start_anchor": "loop-distribute#1",
                                "end_anchor": "loop-vectorize#1",
                            },
                            "replacement": [
                                {"kind": "pass", "name": "loop-distribute"},
                                {
                                    "kind": "manager",
                                    "manager": "loop",
                                    "passes": [{"kind": "pass", "name": "loop-interchange"}],
                                },
                                {
                                    "kind": "manager",
                                    "manager": "loop-mssa",
                                    "passes": [{"kind": "pass", "name": "licm"}],
                                },
                                {"kind": "pass", "name": "loop-vectorize"},
                            ],
                        }
                    ],
                    "opt_options": [],
                }
            ],
        }
    return {}


@dataclass
class MockBackend:
    def complete_json(self, system: str, user: str, *, schema_hint: str, out_dir: Path) -> Any:
        ensure_dir(out_dir)
        (out_dir / "system_prompt.txt").write_text(system)
        (out_dir / "user_prompt.txt").write_text(user)
        payload = _mock_payload(schema_hint, user)
        raw = json.dumps(payload, indent=2)
        (out_dir / "raw_response.txt").write_text(raw)
        write_json(out_dir / "parsed_response.json", payload)
        write_json(out_dir / "response.json", payload)
        return payload


@dataclass
class OpenAICompatBackend:
    model: str
    base_url: str | None = None
    api_key: str | None = None
    retries: int = 5
    request_timeout_sec: int = 900

    def complete_json(self, system: str, user: str, *, schema_hint: str, out_dir: Path) -> Any:
        api_key = self.api_key or _env_value("PASSDISTILL_OPENAI_API_KEY", "OPENAI_API_KEY")
        base_url = self.base_url or _env_value("PASSDISTILL_OPENAI_BASE_URL", "OPENAI_BASE_URL") or "https://api.openai.com/v1"
        if not api_key:
            raise RuntimeError("missing PASSDISTILL_OPENAI_API_KEY or OPENAI_API_KEY in environment or .passdistill.env")
        ensure_dir(out_dir)
        (out_dir / "system_prompt.txt").write_text(system)
        (out_dir / "user_prompt.txt").write_text(user)
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": 0.2,
        }
        last_error: Exception | None = None
        repair_mode = False
        for attempt in range(self.retries + 1):
            content: str | None = None
            request = urllib.request.Request(
                base_url.rstrip("/") + "/chat/completions",
                data=json.dumps(payload).encode(),
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                method="POST",
            )
            try:
                with urllib.request.urlopen(request, timeout=self.request_timeout_sec) as response:
                    raw = response.read().decode()
                data = json.loads(raw)
                content = data["choices"][0]["message"]["content"]
                if repair_mode:
                    (out_dir / f"repair_response_{attempt}.txt").write_text(content)
                else:
                    (out_dir / "raw_response.txt").write_text(content)
                parsed = extract_json(content)
                write_json(out_dir / "parsed_response.json", parsed)
                write_json(out_dir / "response.json", parsed)
                return parsed
            except Exception as exc:  # JSON retry is intentionally small and visible on disk.
                last_error = exc
                (out_dir / f"error_{attempt}.txt").write_text(str(exc))
                if attempt < self.retries:
                    time.sleep(min(2**attempt, 30))
                    # A transport failure produced no response to repair. Retrying the
                    # original payload avoids turning a connection problem into a new
                    # generation request with a misleading JSON-repair conversation.
                    if content is not None:
                        repair_prompt = (
                            "previous response is not valid JSON; return the same information using exactly "
                            "the required schema, no markdown, no prose"
                        )
                        (out_dir / f"repair_prompt_{attempt + 1}.txt").write_text(repair_prompt)
                        payload = {
                            "model": self.model,
                            "messages": [
                                {"role": "system", "content": system},
                                {"role": "user", "content": user},
                                {"role": "assistant", "content": content},
                                {"role": "user", "content": repair_prompt},
                            ],
                            "temperature": 0.0,
                        }
                        repair_mode = True
        raise RuntimeError(f"LLM JSON completion failed: {last_error}")


def make_backend(name: str, model: str | None) -> AgentBackend:
    if name == "mock":
        return MockBackend()
    if name in {"openai", "openai-compatible", "http"}:
        return OpenAICompatBackend(model=model or os.environ.get("PASSDISTILL_MODEL", "gpt-5"))
    raise ValueError(f"unknown LLM backend: {name}")
