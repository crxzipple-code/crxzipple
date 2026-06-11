from __future__ import annotations

from crxzipple.modules.orchestration.application.turn_submission import (
    prompt_bootstrap_metadata_for_content,
)
from crxzipple.modules.orchestration.application.prompt_input import (
    RunPromptInputCollector,
)
from crxzipple.modules.orchestration.domain import InboundInstruction, OrchestrationRun


def test_turn_content_does_not_route_or_inject_default_tool_surface() -> None:
    for content in (
        "查看今天昆明的天气",
        "查询今天黄金价格",
        "给我美元与日元的实时汇率",
        "去东航官网查询今天的航班",
        "打开网站并点击登录，填写用户名",
        "总结一下当前项目状态",
    ):
        metadata = prompt_bootstrap_metadata_for_content(content)

        assert metadata == {}


def test_explicit_prompt_bootstrap_policy_is_preserved_without_resident_tools() -> None:
    metadata = prompt_bootstrap_metadata_for_content(
        "查看今天昆明的天气",
        metadata={
            "prompt_bootstrap_policy": {
                "default_tool_schema_ids": ["custom.tool"],
                "default_tool_schema_source": "test",
            },
        },
    )

    assert metadata["prompt_bootstrap_policy"] == {
        "default_tool_schema_ids": ["custom.tool"],
        "default_tool_schema_source": "test",
    }


def test_runtime_task_prompt_bootstrap_policy_is_preserved_without_resident_tools() -> None:
    metadata = prompt_bootstrap_metadata_for_content(
        "hello",
        metadata={
            "runtime_task_policy": {
                "prompt_bootstrap": {
                    "default_tool_schema_group_refs": [
                        {
                            "source_id": "bundled.local_package.browser",
                            "group_key": "observation",
                        },
                    ],
                },
            },
        },
    )

    assert metadata["prompt_bootstrap_policy"] == {
        "default_tool_schema_group_refs": [
            {
                "source_id": "bundled.local_package.browser",
                "group_key": "observation",
            },
        ],
        "default_tool_schema_source": "prompt_bootstrap_policy",
    }


def test_prompt_input_collector_reads_bootstrap_policy_as_flow_hint() -> None:
    run = OrchestrationRun.accept(
        run_id="run-bootstrap-policy",
        inbound_instruction=InboundInstruction(source="unit", content="天气"),
        metadata=prompt_bootstrap_metadata_for_content("查看今天昆明天气"),
    )

    assert RunPromptInputCollector._prompt_flow_hint_payload(run) == {}
