import { describe, expect, it } from "vitest";

import { describeRunFailure, summarizeRunEventDetail } from "@/lib/runErrors";

import { buildRun } from "../support/factories";

describe("runErrors", () => {
  it("adds recovery guidance for vision capability failures", () => {
    const message = describeRunFailure(
      buildRun({
        status: "failed",
        stage: "failed",
        error: {
          message:
            "LLM profile 'openai_codex.gpt-5.4' does not support vision input.",
          code: "engine_failed",
          details: {},
        },
        metadata: {
          requested_llm_id: "openai_codex.gpt-5.4",
        },
      }),
    );

    expect(message).toContain(
      "LLM profile 'openai_codex.gpt-5.4' does not support vision input.",
    );
    expect(message).toContain(
      "Switch openai_codex.gpt-5.4 to Auto or another vision-capable model.",
    );
    expect(message).toContain("earlier image attachment");
  });

  it("uses failure text ahead of output text in timeline event details", () => {
    const detail = summarizeRunEventDetail(
      buildRun({
        status: "failed",
        stage: "failed",
        error: {
          message: "Provider request failed because the model does not support vision input.",
          code: "engine_failed",
          details: {},
        },
      }),
      "ignored output",
    );

    expect(detail).toContain("does not support vision input");
    expect(detail).not.toContain("ignored output");
  });
});
