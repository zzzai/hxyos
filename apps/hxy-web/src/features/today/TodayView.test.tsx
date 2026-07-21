import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { productEventClient } from "../../api/productEvents";
import { TodayView } from "./TodayView";

vi.mock("../../api/productEvents", () => ({
  productEventClient: { track: vi.fn() },
}));

const item = {
  id: "brief-1",
  kind: "progress" as const,
  severity: null,
  statement: "接待区物料今天需要复核",
  why_it_matters: "这是近期发生的重要变化，需要了解上下文。",
  source_record_id: "10000000-0000-0000-0000-000000000002",
  evidence: [
    {
      source_record_id: "10000000-0000-0000-0000-000000000002",
      source_asset_id: null,
      quote: "接待区物料今天需要复核",
      locator: null,
    },
  ],
  captured_at: "2026-07-21T10:00:00Z",
  next_action: {
    type: "open_record" as const,
    label: "查看记录",
    prompt: null,
  },
};

describe("TodayView briefing feedback", () => {
  beforeEach(() => {
    vi.mocked(productEventClient.track).mockReset();
  });

  it("shows success only after feedback is durably accepted", async () => {
    const user = userEvent.setup();
    vi.mocked(productEventClient.track)
      .mockResolvedValueOnce(false)
      .mockResolvedValueOnce(true);
    render(
      <TodayView
        items={[item]}
        status="ready"
        onOpenRecord={vi.fn()}
        onRetry={vi.fn()}
      />,
    );

    const useful = screen.getByRole("button", {
      name: "认为“接待区物料今天需要复核”有帮助",
    });
    await user.click(useful);

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "反馈没有记录，请重试",
    );
    expect(screen.queryByText("已记录")).not.toBeInTheDocument();

    await user.click(useful);

    expect(await screen.findByRole("status")).toHaveTextContent("已记录");
    expect(productEventClient.track).toHaveBeenCalledTimes(2);
    const firstEvent = vi.mocked(productEventClient.track).mock.calls[0]?.[0];
    const retriedEvent = vi.mocked(productEventClient.track).mock.calls[1]?.[0];
    expect(firstEvent?.clientEventId).toBeTruthy();
    expect(retriedEvent?.clientEventId).toBe(firstEvent?.clientEventId);
  });
});
